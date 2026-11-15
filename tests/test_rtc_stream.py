import asyncio
import time

import pytest
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from PIL import Image

from rtc_stream import RtcPublisher, _WindowsAudioTrack, _lan_offer


def test_offered_lan_candidates_are_limited_to_http_client():
    offer = '\r\n'.join((
        'm=video 9 UDP/TLS/RTP/SAVPF 97',
        'a=recvonly',
        'a=candidate:1 1 UDP 100 tv.local 50100 typ host',
        'a=candidate:2 1 UDP 100 192.168.1.15 50101 typ host',
        'a=candidate:3 1 UDP 100 192.168.1.2 50102 typ host',
        'a=candidate:4 1 UDP 100 192.168.1.2 50103 typ relay',
        'a=candidate:5 1 TCP 100 192.168.1.2 50104 typ host tcptype active',
    ))
    filtered, has_audio = _lan_offer(offer, '192.168.1.2')
    assert not has_audio
    assert '192.168.1.2 50100 typ host' in filtered
    assert '192.168.1.2 50102 typ host' in filtered
    assert '50101' not in filtered and '50103' not in filtered and '50104' not in filtered


@pytest.mark.parametrize('line', ['m=application 9 UDP/DTLS/SCTP webrtc-datachannel', 'a=sendrecv'])
def test_offer_rejects_unexpected_media(line):
    with pytest.raises(ValueError):
        _lan_offer('m=video 9 UDP/TLS/RTP/SAVPF 97\r\n' + line, '192.168.1.2')


def test_web_rtc_decodes_video_and_audio_and_closes(monkeypatch):
    class Capture:
        error = None
        frame = Image.new('RGB', (320, 180), 'purple')

        def frame_after(self, sequence, timeout):
            time.sleep(0.025)
            return sequence + 1, self.frame

    # CI need not have a Windows audio output. Exercise the same RTP track with silence.
    monkeypatch.setattr(_WindowsAudioTrack, 'open', lambda self: None)

    async def receive():
        publisher = RtcPublisher(Capture())
        viewer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        tracks = {}

        @viewer.on('track')
        def on_track(track):
            tracks[track.kind] = track

        try:
            viewer.addTransceiver('video', direction='recvonly')
            viewer.addTransceiver('audio', direction='recvonly')
            await viewer.setLocalDescription(await viewer.createOffer())
            offer = viewer.localDescription.sdp
            client_ip = next(line.split()[4] for line in offer.splitlines() if line.startswith('a=candidate:'))
            answer = await asyncio.to_thread(publisher.answer, offer, 'offer', client_ip=client_ip)
            assert answer['audio_available'] is False
            assert answer['sdp'].index('H264/90000') < answer['sdp'].index('VP8/90000')
            await viewer.setRemoteDescription(RTCSessionDescription(sdp=answer['sdp'], type='answer'))
            video, audio = await asyncio.wait_for(
                asyncio.gather(tracks['video'].recv(), tracks['audio'].recv()), timeout=10,
            )
            assert (video.width, video.height) == (320, 180)
            assert audio.sample_rate == 48_000
            assert publisher.viewer_count() == 1
        finally:
            await viewer.close()
            await asyncio.to_thread(publisher.stop)
        assert publisher.viewer_count() == 0

    asyncio.run(receive())
