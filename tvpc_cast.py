"""TV-PC Cast: local, PIN-protected Windows screen-to-TV streaming."""
from __future__ import annotations

import io
import json
import secrets
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

APP_NAME = "TV-PC Cast"
VERSION = "0.1.0"
DEFAULT_PORT = 8765


class CaptureWorker:
    """Capture/encode once per frame, irrespective of the number of viewers."""

    def __init__(self, monitor=1, fps=10, max_width=1920, jpeg_quality=70):
        self.monitor = monitor
        self.fps = fps
        self.max_width = max_width
        self.jpeg_quality = jpeg_quality
        self.condition = threading.Condition()
        self.frame = None
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
        with self.condition:
            self.condition.wait_for(
                lambda: ((self.frame is not None and self.sequence != sequence)
                         or self.error is not None or self._stop.is_set()),
                timeout=timeout,
            )
            return self.sequence, self.frame

    def _run(self):
        try:
            import mss
            from PIL import Image

            with mss.mss() as capture:
                if self.monitor < 1 or self.monitor >= len(capture.monitors):
                    raise ValueError("A kiválasztott monitor nem található.")
                bounds = capture.monitors[self.monitor]
                while not self._stop.is_set():
                    started = time.monotonic()
                    shot = capture.grab(bounds)
                    frame = Image.frombytes("RGB", shot.size, shot.rgb)
                    if frame.width > self.max_width:
                        height = max(1, round(frame.height * self.max_width / frame.width))
                        frame = frame.resize((self.max_width, height), Image.Resampling.BILINEAR)
                    stream = io.BytesIO()
                    frame.save(stream, "JPEG", quality=self.jpeg_quality)
                    with self.condition:
                        self.frame = stream.getvalue()
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
        self.failures = {}
        self.lock = threading.RLock()
        self.running = False
        self.httpd = None
        self._thread = None

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
        if self._thread:
            self._thread.join(timeout=3)

    def pair(self, pin, address):
        now = time.monotonic()
        with self.lock:
            attempts = [t for t in self.failures.get(address, []) if now - t < 120]
            if len(attempts) >= 5:
                self.failures[address] = attempts
                return None, 429
            if not isinstance(pin, str) or not secrets.compare_digest(pin, self.pin):
                attempts.append(now)
                self.failures[address] = attempts
                return None, 403
            self.failures.pop(address, None)
            self.sessions = {k: v for k, v in self.sessions.items() if v > now}
            if len(self.sessions) >= 16:
                self.sessions.pop(next(iter(self.sessions)))
            token = secrets.token_urlsafe(32)
            self.sessions[token] = now + 12 * 3600
            return token, 200

    def authorized(self, token):
        if not token:
            return False
        with self.lock:
            expiry = self.sessions.get(token)
            return self.running and expiry is not None and expiry > time.monotonic()


def asset_path(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "web" / name


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

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
            except (OSError, ConnectionError):
                pass

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
                else:
                    self.respond(200, frame, "image/jpeg")
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
            except (OSError, ConnectionError):
                pass

        def do_POST(self):
            if urlsplit(self.path).path != "/api/pair":
                self.json_response(404, {"error": "Nincs ilyen API."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 1024:
                    self.json_response(413, {"error": "Hibás kérés."})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Not an object")
                pin = payload.get("pin")
            except (ValueError, UnicodeError, json.JSONDecodeError):
                self.json_response(400, {"error": "Érvénytelen PIN formátum."})
                return
            token, code = service.pair(pin, self.client_address[0])
            if code == 200:
                self.json_response(200, {"token": token})
            elif code == 429:
                self.json_response(429, {"error": "Túl sok próbálkozás. Várj 2 percet."})
            else:
                self.json_response(403, {"error": "Hibás PIN. Ellenőrizd a PC-n."})

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
    import tkinter as tk
    from tkinter import messagebox, ttk

    class DesktopApp:
        def __init__(self):
            self.root = tk.Tk()
            self.root.title("TV-PC Cast | Windows → Hisense")
            self.root.geometry("610x555")
            self.root.minsize(540, 520)
            self.root.configure(bg="#101826")
            self.service = None
            self.addresses = local_addresses()

            style = ttk.Style()
            style.theme_use("clam")
            style.configure("TCombobox", padding=6)
            style.configure("Accent.TButton", font=("Segoe UI", 11, "bold"), padding=10)
            style.configure("TButton", padding=8)

            def text(parent, value, size=11, color="#dae5f4", bold=False):
                return tk.Label(
                    parent, text=value, bg="#101826", fg=color,
                    font=("Segoe UI", size, "bold" if bold else "normal"),
                    justify="left", anchor="w"
                )

            shell = tk.Frame(self.root, bg="#101826", padx=28, pady=22)
            shell.pack(fill="both", expand=True)

            text(shell, "▣  TV-PC CAST", 23, "#89dcff", True).pack(anchor="w")
            text(shell, "Windows képernyő → Hisense VIDAA TV", 11, "#91a5bc").pack(anchor="w", pady=(1, 22))

            text(shell, "KIVETÍTENDŐ MONITOR", 10, "#aabed2", True).pack(anchor="w")
            self.monitors = []
            try:
                import mss
                with mss.mss() as capture:
                    self.monitors = [
                        f"{i}. monitor  ·  {m['width']} × {m['height']}"
                        for i, m in enumerate(capture.monitors[1:], start=1)
                    ]
            except Exception as exc:
                self.monitors = ["Nem található monitor"]
                messagebox.showwarning("Képernyő", f"A monitorlista nem elérhető:\n{exc}")

            self.monitor = ttk.Combobox(shell, state="readonly", values=self.monitors, width=44)
            self.monitor.current(0)
            self.monitor.pack(fill="x", pady=(5, 14))

            options = tk.Frame(shell, bg="#101826")
            options.pack(fill="x")
            left = tk.Frame(options, bg="#101826")
            right = tk.Frame(options, bg="#101826")
            left.pack(side="left", fill="x", expand=True, padx=(0, 9))
            right.pack(side="left", fill="x", expand=True, padx=(9, 0))
            text(left, "KÉPMINŐSÉG", 10, "#aabed2", True).pack(anchor="w")
            self.quality = ttk.Combobox(left, state="readonly", values=[
                "720p", "1080p", "1440p"
            ])
            self.quality.set("1080p")
            self.quality.pack(fill="x", pady=(5, 0))
            text(right, "KÉPKOCKA / MP", 10, "#aabed2", True).pack(anchor="w")
            self.fps = ttk.Combobox(right, state="readonly", values=["6", "10", "15"])
            self.fps.set("10")
            self.fps.pack(fill="x", pady=(5, 0))

            text(shell, "PC HÁLÓZATI CÍME", 10, "#aabed2", True).pack(anchor="w", pady=(16, 0))
            self.address = ttk.Combobox(shell, state="readonly", values=self.addresses)
            self.address.set(self.addresses[0])
            self.address.pack(fill="x", pady=(5, 18))

            self.start_btn = ttk.Button(
                shell, text="▶  Kivetítés indítása", style="Accent.TButton", command=self.toggle
            )
            self.start_btn.pack(fill="x")

            section = tk.Frame(shell, bg="#1a283c", padx=17, pady=15)
            section.pack(fill="x", pady=(16, 0))
            self.status = tk.Label(
                section, text="●  Készen áll", bg="#1a283c", fg="#8bcfaf",
                font=("Segoe UI", 12, "bold"), anchor="w"
            )
            self.status.pack(fill="x")
            self.url = tk.Label(
                section, text="A TV címe indítás után jelenik meg.",
                bg="#1a283c", fg="#d9edff", font=("Consolas", 13, "bold"), anchor="w"
            )
            self.url.pack(fill="x", pady=(9, 0))
            self.pin_label = tk.Label(
                section, text="PIN: –", bg="#1a283c", fg="#89dcff",
                font=("Consolas", 19, "bold"), anchor="w"
            )
            self.pin_label.pack(fill="x", pady=(8, 0))

            self.copy_btn = ttk.Button(section, text="Cím másolása", command=self.copy_url)
            self.copy_btn.pack(anchor="w", pady=(9, 0))
            self.copy_btn.state(["disabled"])
            text(shell,
                 "TV: Browser / Böngésző → írd be a címet → add meg a PIN-t.",
                 10, "#9fb1c5").pack(anchor="w", pady=(19, 4))
            text(shell,
                 "Csak helyi hálózaton • Hang nélkül • Hisense VIDAA kompatibilitási mód",
                 9, "#8799ac").pack(anchor="w")
            self.root.protocol("WM_DELETE_WINDOW", self.close)
            self.root.after(500, self.check_capture)

        def copy_url(self):
            if self.service and self.service.running:
                self.root.clipboard_clear()
                self.root.clipboard_append(self.url["text"])
                self.root.update()

        def toggle(self):
            if self.service and self.service.running:
                self.stop()
                return
            if not self.monitors or self.monitors[0] == "Nem található monitor":
                messagebox.showerror("TV-PC Cast", "Nincs elérhető monitor.")
                return
            width = {"720p": 1280, "1080p": 1920, "1440p": 2560}[self.quality.get()]
            capture = CaptureWorker(
                monitor=self.monitor.current() + 1,
                fps=int(self.fps.get()), max_width=width
            )
            service = CastService(capture=capture)
            try:
                service.start()
            except OSError as exc:
                messagebox.showerror(
                    "Hálózati hiba",
                    f"A TCP/{DEFAULT_PORT} port nem nyitható meg:\n{exc}"
                )
                return
            self.service = service
            self.status.config(text="●  Közvetítés aktív", fg="#8bcfaf")
            self.url.config(text=f"http://{self.address.get()}:{service.port}")
            self.pin_label.config(text=f"PIN: {service.pin}")
            self.start_btn.config(text="■  Kivetítés leállítása")
            self.copy_btn.state(["!disabled"])
            for control in (self.monitor, self.quality, self.fps, self.address):
                control.configure(state="disabled")

        def stop(self):
            if self.service:
                self.service.stop()
                self.service = None
            self.status.config(text="●  Készen áll", fg="#8bcfaf")
            self.url.config(text="A TV címe indítás után jelenik meg.")
            self.pin_label.config(text="PIN: –")
            self.start_btn.config(text="▶  Kivetítés indítása")
            self.copy_btn.state(["disabled"])
            for control in (self.monitor, self.quality, self.fps, self.address):
                control.configure(state="readonly")

        def check_capture(self):
            if self.service and self.service.capture.error:
                error = self.service.capture.error
                self.stop()
                messagebox.showerror("Képernyőhiba", error)
            self.root.after(500, self.check_capture)

        def close(self):
            self.stop()
            self.root.destroy()

        def run(self):
            self.root.mainloop()

    DesktopApp().run()


if __name__ == "__main__":
    main()
