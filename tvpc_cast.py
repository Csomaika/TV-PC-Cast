"""TV-PC Cast: local, PIN-protected Windows screen-to-TV streaming."""
from __future__ import annotations

import io
import json
import logging
import secrets
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

APP_NAME = "TV-PC Cast"
VERSION = "0.2.0"
DEFAULT_PORT = 8765
FRAME_SIZES = {
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
    "4K": (3840, 2160),
}


class CaptureWorker:
    """Capture/encode once per frame, irrespective of the number of viewers."""

    def __init__(self, monitor=1, fps=10, max_width=1920, jpeg_quality=70, max_height=None):
        self.monitor = monitor
        self.fps = fps
        self.max_width = max_width
        self.max_height = max_height if max_height is not None else max_width * 9 // 16
        self.jpeg_quality = jpeg_quality
        self.condition = threading.Condition()
        self._jpeg_lock = threading.Lock()
        self._jpeg_sequence = -1
        self.frame = None
        self.image = None
        self.sequence = 0
        self.error = None
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="Capture", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        with self.condition:
            self.condition.notify_all()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)

    def frame_after(self, sequence, timeout=3):
        current, image = self.snapshot_after(sequence, timeout)
        if image is None:
            return current, None
        with self._jpeg_lock:
            if self._jpeg_sequence < current:
                stream = io.BytesIO()
                image.save(stream, "JPEG", quality=self.jpeg_quality)
                self.frame = stream.getvalue()
                self._jpeg_sequence = current
            return self._jpeg_sequence, self.frame

    def snapshot_after(self, sequence, timeout=3):
        with self.condition:
            self.condition.wait_for(
                lambda: ((self.image is not None and self.sequence != sequence)
                         or self.error is not None or self._stop.is_set()),
                timeout=timeout,
            )
            return self.sequence, self.image

    def _run(self):
        try:
            import mss
            from PIL import Image

            with mss.mss() as capture:
                if not 0 <= self.monitor < len(capture.monitors):
                    raise ValueError("A kiválasztott monitor nem található.")
                bounds = capture.monitors[self.monitor]
                while not self._stop.is_set():
                    started = time.monotonic()
                    shot = capture.grab(bounds)
                    frame = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                    frame.thumbnail((self.max_width, self.max_height), Image.Resampling.BILINEAR)
                    with self.condition:
                        self.image = frame
                        self.sequence += 1
                        self.condition.notify_all()
                    self._stop.wait(max(0, 1 / self.fps - (time.monotonic() - started)))
        except Exception as exc:
            with self.condition:
                self.error = str(exc)
                self.condition.notify_all()


class CastService:
    """HTTP server with a fresh, limited-use PIN and random viewer tokens."""

    def __init__(self, capture=None, port=DEFAULT_PORT, host="0.0.0.0"):
        self.capture = capture if capture is not None else CaptureWorker()
        self.host = host
        self.port = port
        self.pin = f"{secrets.randbelow(900000) + 100000:06d}"
        self.sessions = {}
        self.viewers = {}
        self.failures = {}
        self.lock = threading.RLock()
        self.running = False
        self.httpd = None
        self._thread = None
        self.rtc = None

    def start(self):
        if self.running:
            return
        self.httpd = ThreadingHTTPServer((self.host, self.port), make_handler(self))
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.running = True
        try:
            self.capture.start()
            self._thread = threading.Thread(
                target=self.httpd.serve_forever, name="Cast HTTP", daemon=True
            )
            self._thread.start()
        except Exception:
            self.running = False
            self.httpd.server_close()
            self.capture.stop()
            raise

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        self.capture.stop()
        with self.lock:
            self.sessions.clear()
            self.viewers.clear()
            self.failures.clear()
            rtc = self.rtc
            self.rtc = None
        if rtc is not None:
            rtc.stop()
        if self._thread:
            self._thread.join(timeout=3)

    def pair(self, pin, address):
        now = time.monotonic()
        with self.lock:
            attempts = [t for t in self.failures.get(address, []) if now - t < 120]
            if len(attempts) >= 5:
                self.failures[address] = attempts
                return None, 429
            if (not isinstance(pin, str) or not pin.isascii()
                    or not secrets.compare_digest(pin, self.pin)):
                attempts.append(now)
                self.failures[address] = attempts
                return None, 403
            self.failures.pop(address, None)
            self.sessions = {k: v for k, v in self.sessions.items() if v > now}
            if len(self.sessions) >= 16:
                self.sessions.pop(next(iter(self.sessions)))
            self.viewers = {k: v for k, v in self.viewers.items() if k in self.sessions}
            token = secrets.token_urlsafe(32)
            self.sessions[token] = now + 12 * 3600
            return token, 200

    def authorized(self, token):
        if not token:
            return False
        with self.lock:
            expiry = self.sessions.get(token)
            return self.running and expiry is not None and expiry > time.monotonic()

    def record_view(self, token):
        with self.lock:
            if self.authorized(token):
                self.viewers[token] = time.monotonic()

    def viewer_count(self):
        with self.lock:
            cutoff = time.monotonic() - 5
            count = sum(seen > cutoff for seen in self.viewers.values())
            rtc = self.rtc
        return count + (rtc.viewer_count() if rtc is not None else 0)

    def rtc_answer(self, token, sdp, client_ip):
        with self.lock:
            if not self.authorized(token):
                raise PermissionError("PIN szükséges.")
            if self.rtc is None:
                from rtc_stream import RtcPublisher

                self.rtc = RtcPublisher(self.capture)
            publisher = self.rtc
        return publisher.answer(sdp, "offer", client_ip=client_ip)


def asset_path(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "web" / name


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        timeout = 8

        def log_message(self, format, *args):
            # Do not write to a console that does not exist in windowed builds.
            pass

        def headers_common(self):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")

        def respond(self, status, body, content_type="application/json; charset=utf-8"):
            self.send_response(status)
            self.headers_common()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                return False
            return True

        def json_response(self, status, data):
            self.respond(status, json.dumps(data).encode("utf-8"))

        def do_GET(self):
            location = urlsplit(self.path)
            if location.path == "/":
                try:
                    html = asset_path("index.html").read_bytes()
                except OSError:
                    self.json_response(500, {"error": "A TV oldal nem található."})
                    return
                self.respond(200, html, "text/html; charset=utf-8")
                return
            if location.path == "/health":
                self.json_response(200, {"app": APP_NAME, "running": service.running})
                return
            if location.path not in ("/frame", "/stream"):
                self.json_response(404, {"error": "Nincs ilyen oldal."})
                return
            token = parse_qs(location.query).get("token", [""])[0]
            if not service.authorized(token):
                self.json_response(401, {"error": "PIN szükséges."})
                return
            if location.path == "/frame":
                _, frame = service.capture.frame_after(-1, timeout=3)
                if frame is None:
                    self.json_response(503, {"error": "A kép még nem elérhető."})
                elif self.respond(200, frame, "image/jpeg"):
                    service.record_view(token)
                return
            self.send_response(200)
            self.headers_common()
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=tvframe")
            self.send_header("Connection", "close")
            self.end_headers()
            last = 0
            try:
                while service.running and service.authorized(token):
                    seq, frame = service.capture.frame_after(last, timeout=5)
                    if frame is None or seq == last:
                        if service.capture.error:
                            break
                        continue
                    last = seq
                    header = (
                        b"--tvframe\r\nContent-Type: image/jpeg\r\nContent-Length: "
                        + str(len(frame)).encode("ascii")
                        + b"\r\n\r\n"
                    )
                    self.wfile.write(header)
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                    service.record_view(token)
            except OSError:
                pass

        def do_POST(self):
            path = urlsplit(self.path).path
            limits = {"/api/pair": 1024, "/api/rtc/offer": 65536}
            if path not in limits:
                self.json_response(404, {"error": "Nincs ilyen API."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > limits[path]:
                    self.close_connection = True
                    self.json_response(413, {"error": "Hibás kérés."})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Not an object")
            except (ValueError, OSError):
                self.close_connection = True
                self.json_response(400, {"error": "Érvénytelen kérés."})
                return
            if path == "/api/rtc/offer":
                self.rtc_offer(payload)
                return
            token, code = service.pair(payload.get("pin"), self.client_address[0])
            if code == 200:
                self.json_response(200, {"token": token})
            elif code == 429:
                self.json_response(429, {"error": "Túl sok próbálkozás. Várj 2 percet."})
            else:
                self.json_response(403, {"error": "Hibás PIN. Ellenőrizd a PC-n."})

        def rtc_offer(self, payload):
            token = payload.get("token")
            if not isinstance(token, str) or not service.authorized(token):
                self.json_response(401, {"error": "PIN szükséges."})
                return
            sdp = payload.get("sdp")
            if payload.get("type") != "offer" or not isinstance(sdp, str) or not sdp.startswith("v=0\r\n"):
                self.json_response(400, {"error": "Érvénytelen WebRTC ajánlat."})
                return
            try:
                answer = service.rtc_answer(token, sdp, self.client_address[0])
            except PermissionError:
                self.json_response(401, {"error": "PIN szükséges."})
            except (ImportError, OSError, RuntimeError, ValueError):
                logging.exception("WebRTC negotiation failed")
                self.json_response(503, {"error": "A PC nem tudta elindítani a WebRTC közvetítést."})
            else:
                self.json_response(200, answer)

    return Handler


def local_addresses():
    """Best-effort IPv4 list; do not send network packets to public hosts."""
    result = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("192.0.2.1", 9))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                result.append(ip)
        finally:
            sock.close()
    except OSError:
        pass
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = item[4][0]
            if ip not in result and not ip.startswith(("127.", "169.254.")):
                result.append(ip)
    except OSError:
        pass
    return result or ["127.0.0.1"]


def main():
    from desktop import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
