"""WebRTC sender for the local, PIN-authenticated television viewer."""
from __future__ import annotations

import asyncio
import concurrent.futures
import io
import ipaddress
import logging
import threading
import time
from fractions import Fraction

from aiortc import MediaStreamTrack, RTCConfiguration, RTCPeerConnection, RTCRtpSender, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from aiortc.mediastreams import MediaStreamError
from av import AudioFrame, VideoFrame
from PIL import Image

_MAX_PEERS = 3
_VIDEO_CLOCK = Fraction(1, 90_000)
_AUDIO_PERIOD = 0.02


def _lan_offer(sdp, client_ip):
    """Restrict UDP candidate destinations to the LAN connection that sent the offer."""
    lines = []
    media = []
    candidate_count = 0
    address = ipaddress.ip_address(client_ip) if client_ip else None
    for raw_line in sdp.splitlines():
        line = raw_line.rstrip()
        if line.startswith('m='):
            media.append(line[2:].split(' ', 1)[0])
        elif line.startswith(('a=sendrecv', 'a=sendonly')):
            raise ValueError('A TV-lejátszó csak fogadó ajánlatot küldhet.')
        elif line.startswith('a=candidate:') and address is not None:
            fields = line.split()
            if (candidate_count >= 24 or len(fields) < 8 or fields[1] != '1'
                    or fields[2].lower() != 'udp' or fields[6:8] != ['typ', 'host']):
                continue
            try:
                candidate_address = ipaddress.ip_address(fields[4])
            except ValueError:
                if not fields[4].lower().endswith('.local'):
                    continue
                candidate_address = address
            if candidate_address != address:
                continue
            fields[4] = str(address)
            line = ' '.join(fields[:8])
            candidate_count += 1
        lines.append(line)
    if media.count('video') != 1 or set(media) - {'video', 'audio'} or media.count('audio') > 1:
        raise ValueError('A WebRTC-ajánlatnak egy kép- és legfeljebb egy hangsávot kell tartalmaznia.')
    return '\r\n'.join(lines) + '\r\n', 'audio' in media


class _ScreenTrack(MediaStreamTrack):
    kind = 'video'

    def __init__(self, capture):
        super().__init__()
        self._read = getattr(capture, 'snapshot_after', capture.frame_after)
        self._capture = capture
        self._sequence = -1
        self._origin = time.monotonic()
        self._previous_pts = -1

    async def recv(self):
        while self.readyState == 'live':
            sequence, snapshot = await asyncio.to_thread(self._read, self._sequence, 0.5)
            if self._capture.error:
                break
            if snapshot is None or sequence == self._sequence:
                await asyncio.sleep(0.01)
                continue
            self._sequence = sequence
            if isinstance(snapshot, bytes):
                with Image.open(io.BytesIO(snapshot)) as image:
                    frame = VideoFrame.from_image(image)
            else:
                frame = VideoFrame.from_image(snapshot)
            # The subsampled H.264 pixel format requires even dimensions.
            width, height = frame.width & ~1, frame.height & ~1
            frame = frame.reformat(width=width, height=height, format='yuv420p')
            frame.pts = max(self._previous_pts + 1, int((time.monotonic() - self._origin) * 90_000))
            frame.time_base = _VIDEO_CLOCK
            self._previous_pts = frame.pts
            return frame
        raise MediaStreamError


class _WindowsAudioTrack(MediaStreamTrack):
    kind = 'audio'

    def __init__(self):
        super().__init__()
        self.rate = 48_000
        self.channels = 2
        self.available = False
        self._capture = None
        self._stream = None
        self._data = bytearray()
        self._data_lock = threading.Lock()
        self._device_lock = threading.Lock()
        self._deadline = None
        self._pts = 0

    def open(self):
        with self._device_lock:
            try:
                import pyaudiowpatch as wasapi

                self._capture = wasapi.PyAudio()
                device = self._capture.get_default_wasapi_loopback()
                self.rate = int(device['defaultSampleRate'])
                self.channels = max(1, min(2, device['maxInputChannels']))
                self._stream = self._capture.open(
                    format=wasapi.paInt16,
                    channels=self.channels,
                    rate=self.rate,
                    input=True,
                    input_device_index=device['index'],
                    frames_per_buffer=self.rate // 50,
                    stream_callback=lambda data, *_: self._receive(data, wasapi.paContinue),
                )
                self.available = True
            except Exception as exc:
                logging.warning('WASAPI loopback endpoint unavailable: %s', exc)
                self._close_device()

    def _receive(self, data, continue_code):
        if data:
            with self._data_lock:
                self._data.extend(data)
                excess = len(self._data) - self._packet_bytes * 4
                if excess > 0:
                    del self._data[:excess]
        return None, continue_code

    @property
    def _packet_bytes(self):
        return (self.rate // 50) * self.channels * 2

    def _close_device(self):
        stream, self._stream = self._stream, None
        capture, self._capture = self._capture, None
        try:
            if stream is not None:
                stream.close()
        finally:
            if capture is not None:
                capture.terminate()

    def close(self):
        with self._device_lock:
            self._close_device()

    async def recv(self):
        if self.readyState != 'live':
            raise MediaStreamError
        now = time.monotonic()
        samples = self.rate // 50
        if self._deadline is None:
            self._deadline = now
        if now > self._deadline + 0.08:
            late = int((now - self._deadline) / _AUDIO_PERIOD)
            self._pts += late * samples
            self._deadline += late * _AUDIO_PERIOD
        await asyncio.sleep(max(0, self._deadline - now))
        self._deadline += _AUDIO_PERIOD

        with self._data_lock:
            chunk = bytes(self._data[:self._packet_bytes])
            del self._data[:self._packet_bytes]
        frame = AudioFrame(format='s16', layout='mono' if self.channels == 1 else 'stereo', samples=samples)
        frame.planes[0].update(chunk.ljust(self._packet_bytes, b'\x00'))
        frame.sample_rate = self.rate
        frame.pts = self._pts
        frame.time_base = Fraction(1, self.rate)
        self._pts += samples
        return frame


class RtcPublisher:
    """Own the asyncio thread and peer connections used by the HTTP cast service."""

    def __init__(self, capture):
        self._capture = capture
        self._loop = asyncio.new_event_loop()
        self._lock = threading.Lock()
        self._negotiations = asyncio.Lock()
        self._peers = {}
        self._closing = set()
        self._audio = None
        self._relay = MediaRelay()
        self._connected = 0
        self._stopped = False
        self._thread = threading.Thread(target=self._run, name='Cast WebRTC', daemon=True)
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.run_until_complete(self._loop.shutdown_default_executor(timeout=3))
            self._loop.close()

    def answer(self, sdp, offer_type, *, client_ip=None):
        if offer_type != 'offer' or not isinstance(sdp, str) or len(sdp) > 64_000:
            raise ValueError('Érvénytelen WebRTC-ajánlat.')
        sdp, has_audio = _lan_offer(sdp, client_ip)
        with self._lock:
            if self._stopped:
                raise RuntimeError('A közvetítés leállt.')
            task = asyncio.run_coroutine_threadsafe(self._answer(sdp, has_audio), self._loop)
        try:
            return task.result(timeout=12)
        except concurrent.futures.TimeoutError as exc:
            task.cancel()
            raise RuntimeError('A WebRTC-kapcsolat beállítása túllépte az időkorlátot.') from exc

    async def _answer(self, sdp, has_audio):
        async with self._negotiations:
            if len(self._peers) >= _MAX_PEERS:
                raise RuntimeError('Egyszerre legfeljebb három WebRTC-néző csatlakozhat.')
            peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
            expiry = self._loop.call_later(20, self._expire, peer)
            self._peers[peer] = expiry

            @peer.on('connectionstatechange')
            async def on_state_change():
                if peer.connectionState == 'connected':
                    expiry.cancel()
                elif peer.connectionState in ('failed', 'closed'):
                    await self._close_peer(peer)
                self._connected = sum(pc.connectionState == 'connected' for pc in self._peers)

            try:
                video = peer.addTransceiver(_ScreenTrack(self._capture), direction='sendonly')
                codecs = RTCRtpSender.getCapabilities('video').codecs
                video.setCodecPreferences(sorted(codecs, key=lambda codec: codec.mimeType.lower() != 'video/h264'))
                audio = peer.addTransceiver('audio', direction='sendonly') if has_audio else None
                await peer.setRemoteDescription(RTCSessionDescription(sdp=sdp, type='offer'))
                if audio is not None:
                    if self._audio is None:
                        self._audio = _WindowsAudioTrack()
                        await asyncio.to_thread(self._audio.open)
                    audio.sender.replaceTrack(self._relay.subscribe(self._audio, buffered=False))
                await peer.setLocalDescription(await peer.createAnswer())
                return {
                    'sdp': peer.localDescription.sdp,
                    'type': peer.localDescription.type,
                    'audio_available': audio is not None and self._audio.available,
                }
            except (Exception, asyncio.CancelledError):
                await self._close_peer(peer)
                raise

    def _expire(self, peer):
        if peer.connectionState != 'connected':
            self._loop.create_task(self._close_peer(peer))

    async def _close_peer(self, peer):
        expiry = self._peers.pop(peer, None)
        if expiry is None:
            return
        expiry.cancel()
        self._connected = sum(pc.connectionState == 'connected' for pc in self._peers)
        task = asyncio.current_task()
        self._closing.add(task)
        try:
            await peer.close()
            if not self._peers and self._audio is not None:
                audio = self._audio
                self._audio = None
                audio.stop()
                await asyncio.to_thread(audio.close)
        finally:
            self._closing.discard(task)

    def viewer_count(self):
        return self._connected

    def stop(self):
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            task = asyncio.run_coroutine_threadsafe(self._close(), self._loop)
        try:
            task.result(timeout=5)
        except concurrent.futures.TimeoutError:
            task.cancel()
            logging.warning('Timed out while closing WebRTC peers')
        except Exception:
            logging.exception('Failed to close a WebRTC resource')
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)

    async def _close(self):
        async with self._negotiations:
            await asyncio.gather(*(self._close_peer(peer) for peer in tuple(self._peers)))
            await asyncio.gather(*tuple(self._closing), return_exceptions=True)
