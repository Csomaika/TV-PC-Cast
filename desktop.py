"""Hungarian Windows interface and packaged application smoke test."""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import queue
import threading
import tkinter as tk
from http.client import HTTPConnection
from pathlib import Path
from tkinter import messagebox, ttk

from tvpc_cast import APP_NAME, DEFAULT_PORT, FRAME_SIZES, VERSION, CaptureWorker, CastService, local_addresses
from windows_cast import open_cast_panel, open_project_panel


class DesktopApp:
    def __init__(self, *, loopback=False):
        self.service = None
        self.loopback = loopback
        self.port = 0 if self.loopback else DEFAULT_PORT
        self.addresses = ["127.0.0.1"] if self.loopback else local_addresses()
        self.capture_error = None
        self.monitors = self.read_monitors()

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.minsize(600, 540)
        self.root.configure(background="#101923")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.report_callback_exception = self.callback_error

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background="#101923")
        style.configure("TLabel", background="#101923", foreground="#e7eff6", font=("Segoe UI", 11))
        style.configure("Heading.TLabel", foreground="#f5faff", font=("Segoe UI", 23, "bold"))
        style.configure("Section.TLabel", foreground="#f5faff", font=("Segoe UI", 14, "bold"))
        style.configure("Hint.TLabel", foreground="#bac9d6")
        style.configure("Status.TLabel", foreground="#94ded1", font=("Segoe UI", 11, "bold"))
        style.configure("Address.TLabel", foreground="#94ded1", font=("Consolas", 13, "bold"))
        style.configure("TButton", padding=(13, 8), font=("Segoe UI", 10))
        style.configure("Primary.TButton", background="#94ded1", foreground="#102623", font=("Segoe UI", 10, "bold"))
        style.map("Primary.TButton", background=[("active", "#b3eee4")])
        style.configure("TCombobox", padding=5)
        style.configure("TNotebook", background="#101923", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 9), font=("Segoe UI", 11))
        style.map("TNotebook.Tab", background=[("selected", "#d9e9ef")])

        shell = ttk.Frame(self.root, padding=(24, 20))
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text=APP_NAME, style="Heading.TLabel").pack(anchor="w", pady=(0, 14))
        self.tabs = ttk.Notebook(shell)
        self.tabs.pack(fill="both", expand=True)
        self.make_browser_tab()
        self.make_network_tab()
        self.make_wireless_tab()
        self.root.after(500, self.check_capture)

    def read_monitors(self):
        try:
            import mss

            with mss.mss() as capture:
                displays = capture.monitors
                if len(displays) < 2:
                    raise RuntimeError("A Windows nem ad elérhető monitort.")
                return [
                    f"{name} · {bounds['width']} × {bounds['height']}"
                    for name, bounds in zip(
                        ["Összes monitor"] + [f"{i}. monitor" for i in range(1, len(displays))],
                        displays,
                    )
                ]
        except Exception as exc:
            self.capture_error = str(exc)
            return []

    def make_wireless_tab(self):
        tab = ttk.Frame(self.tabs, padding=(18, 20))
        self.tabs.add(tab, text="Vezeték nélküli kijelző")
        ttk.Label(tab, text="Képtükrözés és rendszerhang", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            tab, text="A TV-n válaszd a Képernyőmegosztás (Screen Sharing) bemenetet. "
            "Ezután a Windows listájában válaszd ki a televíziót.",
            style="Hint.TLabel", wraplength=490, justify="left",
        ).pack(anchor="w", pady=(8, 18))
        ttk.Button(
            tab, text="TV keresése / leválasztása  ·  Win + K", style="Primary.TButton",
            command=lambda: self.open_wireless(open_cast_panel, "Win + K"),
        ).pack(anchor="w")
        actions = ttk.Frame(tab)
        actions.pack(anchor="w", pady=(10, 0))
        ttk.Button(actions, text="Kivetítés módja  ·  Win + P",
                   command=lambda: self.open_wireless(open_project_panel, "Win + P")).pack(side="left")
        ttk.Button(actions, text="Hangbeállítások", command=self.open_sound).pack(side="left", padx=(8, 0))
        self.wireless_status = ttk.Label(
            tab, text="A Windows paneljén látható a kapcsolat állapota.",
            style="Status.TLabel", wraplength=490,
        )
        self.wireless_status.pack(anchor="w", pady=(24, 8))
        ttk.Label(
            tab, text="Tükrözéshez a Kivetítés panelen válaszd a Megkettőzés lehetőséget. "
            "Ha a hang a PC-n marad, a Hangbeállításokban válaszd a TV-t kimenetként.",
            style="Hint.TLabel", wraplength=490, justify="left",
        ).pack(anchor="w")

    def make_browser_tab(self):
        self.browser_tab = ttk.Frame(self.tabs, padding=(18, 16))
        tab = self.browser_tab
        self.tabs.add(tab, text="Közvetlen böngészős mód")
        ttk.Label(
            tab, text="A TV böngészőjében nyisd meg az alábbi címet, add meg a PIN-kódot, "
            "majd válaszd a Kép és hang lehetőséget.",
            style="Hint.TLabel", wraplength=490, justify="left",
        ).pack(anchor="w", pady=(0, 12))
        self.monitor = self.combo(tab, "Képernyő", self.monitors or ["Nincs elérhető monitor"],
                                  1 if self.monitors else 0)
        options = ttk.Frame(tab)
        options.pack(fill="x", pady=(8, 0))
        left = ttk.Frame(options)
        right = ttk.Frame(options)
        left.pack(side="left", fill="x", expand=True, padx=(0, 5))
        right.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.quality = self.combo(left, "Legnagyobb képméret", list(FRAME_SIZES), 1)
        self.fps = self.combo(right, "Képkocka / mp", ["6", "10", "15", "24", "30"], 3)
        address_row = ttk.Frame(tab)
        address_row.pack(fill="x", pady=(8, 0))
        self.address = self.combo(address_row, "PC hálózati címe", self.addresses)
        self.address.configure(postcommand=lambda: self.refresh_addresses(self.address))
        self.start_btn = ttk.Button(tab, text="Közvetítés indítása", style="Primary.TButton", command=self.toggle)
        self.start_btn.pack(anchor="w", pady=(12, 8))
        self.status = ttk.Label(tab, text="Készen áll", style="Status.TLabel", wraplength=490)
        self.status.pack(anchor="w")
        address_line = ttk.Frame(tab)
        address_line.pack(fill="x", pady=(6, 0))
        self.url = ttk.Label(address_line, text="TV-cím: –", style="Address.TLabel")
        self.url.pack(side="left")
        self.copy_btn = ttk.Button(address_line, text="Cím másolása", command=self.copy_url, state="disabled")
        self.copy_btn.pack(side="right")
        self.pin_label = ttk.Label(tab, text="PIN: –", style="Address.TLabel")
        self.pin_label.pack(anchor="w")
        if self.capture_error:
            self.status.config(text=f"Képernyőhiba: {self.capture_error}")
            self.start_btn.state(["disabled"])

    def make_network_tab(self):
        self.network_tab = ttk.Frame(self.tabs, padding=(18, 16))
        tab = self.network_tab
        self.tabs.add(tab, text="Hálózati eszközök")
        ttk.Label(
            tab, text="A helyi hálózaton válaszoló eszközök (UPnP/SSDP). A Miracast kijelzők a Win + K panelen jelennek meg.",
            style="Hint.TLabel", wraplength=490, justify="left",
        ).pack(anchor="w", pady=(0, 10))
        self.scan_address = self.combo(tab, "PC hálózati címe", self.addresses)
        self.scan_address.configure(postcommand=lambda: self.refresh_addresses(self.scan_address))
        self.scan_button = ttk.Button(tab, text="Eszközök keresése", style="Primary.TButton", command=self.scan_network)
        self.scan_button.pack(anchor="w", pady=(8, 10))
        self.scan_status = ttk.Label(tab, text="", style="Status.TLabel", wraplength=490)
        self.scan_status.pack(anchor="w", pady=(0, 6))
        listing = ttk.Frame(tab)
        listing.pack(fill="both", expand=True)
        self.device_table = ttk.Treeview(listing, columns=("name", "ip", "type"), show="headings", height=5)
        scrollbar = ttk.Scrollbar(listing, orient="vertical", command=self.device_table.yview)
        self.device_table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.device_table.pack(side="left", fill="both", expand=True)
        for field, title, width in (("name", "Eszköz", 210), ("ip", "IP-cím", 104), ("type", "Típus", 130)):
            self.device_table.heading(field, text=title)
            self.device_table.column(field, width=width, minwidth=68)
        self.device_details = ttk.Label(tab, style="Hint.TLabel", wraplength=490, justify="left")
        self.device_details.pack(anchor="w", pady=(10, 0))
        self.lan_devices = {}
        self.device_table.bind("<<TreeviewSelect>>", self.show_device)
        self.tabs.bind("<<NotebookTabChanged>>", self.scan_on_first_open)
        self.scanned = False

    def scan_on_first_open(self, _event):
        if not self.scanned and self.tabs.select() == str(self.network_tab):
            self.scanned = True
            self.scan_network()

    def refresh_addresses(self, field):
        if self.loopback:
            return
        selected = field.get()
        addresses = local_addresses()
        field.configure(values=addresses)
        field.set(selected if selected in addresses else addresses[0])

    def scan_network(self):
        self.refresh_addresses(self.scan_address)
        address = self.scan_address.get()
        if address.startswith("127."):
            self.scan_status.config(text="Nincs használható helyi IPv4-cím.")
            return
        for row in self.device_table.get_children():
            self.device_table.delete(row)
        self.device_details.config(text="")
        self.lan_devices.clear()
        self.scan_button.state(["disabled"])
        self.scan_address.state(["disabled"])
        self.scan_status.config(text=f"Eszközök keresése a hálózaton ({address})…")
        result = queue.SimpleQueue()

        def discover():
            try:
                from lan_discovery import discover_devices

                result.put((discover_devices(address), None))
            except Exception as exc:
                result.put(([], str(exc)))

        threading.Thread(target=discover, name="LAN discovery", daemon=True).start()
        self.root.after(100, self.finish_scan, result)

    def finish_scan(self, result):
        try:
            devices, error = result.get_nowait()
        except queue.Empty:
            self.root.after(100, self.finish_scan, result)
            return
        self.scan_button.state(["!disabled"])
        self.scan_address.state(["!disabled"])
        if error:
            self.scan_status.config(text=f"A keresés sikertelen: {error}")
            return
        kinds = {"renderer": "Médialejátszó (DLNA)", "google_cast": "Google Cast", "upnp": "UPnP-eszköz"}
        for device in devices:
            row = self.device_table.insert("", "end", values=(device.name, device.ip, kinds.get(device.kind, device.kind)))
            self.lan_devices[row] = device
        self.scan_status.config(text=f"Válaszoló eszközök száma: {len(devices)}" if devices else "Nem érkezett válasz a keresésre.")

    def show_device(self, _event):
        selection = self.device_table.selection()
        if not selection:
            return
        device = self.lan_devices.get(selection[0])
        if device is None:
            return
        detail = f"{device.name} · {device.model}" if device.model else device.name
        if device.kind == "google_cast":
            detail += "\nChrome → Átküldés → Források → Képernyő átküldése."
        elif device.kind == "renderer":
            detail += "\nA készülék médiaszolgáltatást jelez a hálózaton."
        self.device_details.config(text=detail)

    def combo(self, parent, label, values, selected=0):
        field = ttk.Combobox(parent, state="readonly", values=values, width=15)
        ttk.Label(parent, text=label).pack(anchor="w")
        field.current(selected)
        field.pack(fill="x", pady=(3, 0))
        return field

    def open_wireless(self, action, shortcut):
        try:
            action()
        except OSError:
            self.wireless_status.config(text=f"A panel megnyitásához nyomd meg: {shortcut}.")
        else:
            self.wireless_status.config(text="A Windows paneljén látható a kapcsolat állapota.")

    def open_sound(self):
        try:
            os.startfile("ms-settings:sound")
        except OSError:
            self.wireless_status.config(text="A Gépházban nyisd meg a Rendszer → Hang oldalt.")

    def copy_url(self):
        if self.service and self.service.running:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.url["text"])

    def toggle(self):
        if self.service:
            self.stop()
            return
        self.refresh_addresses(self.address)
        if not self.loopback and self.address.get().startswith("127."):
            self.status.config(text="Nincs használható helyi IPv4-cím. Csatlakozz a TV helyi hálózatához.")
            return
        try:
            self.start()
        except OSError as exc:
            self.status.config(text=f"A TCP/{self.port} port nem nyitható meg: {exc}")

    def start(self):
        width, height = FRAME_SIZES[self.quality.get()]
        capture = CaptureWorker(
            monitor=self.monitor.current(), fps=int(self.fps.get()), max_width=width, max_height=height,
        )
        service = CastService(capture=capture, host=self.address.get(), port=self.port)
        service.start()
        self.service = service
        self.url.config(text=f"http://{service.host}:{service.port}")
        self.pin_label.config(text=f"PIN: {service.pin}")
        self.start_btn.config(text="Közvetítés leállítása")
        self.copy_btn.state(["!disabled"])
        for control in (self.monitor, self.quality, self.fps, self.address):
            control.configure(state="disabled")
        self.status.config(text="Közvetítés aktív. Várakozás a nézőre…")

    def stop(self):
        if self.service:
            self.service.stop()
            self.service = None
        self.status.config(text="Készen áll")
        self.url.config(text="TV-cím: –")
        self.pin_label.config(text="PIN: –")
        self.start_btn.config(text="Közvetítés indítása")
        self.copy_btn.state(["disabled"])
        for control in (self.monitor, self.quality, self.fps, self.address):
            control.configure(state="readonly")

    def check_capture(self):
        if self.service:
            error = self.service.capture.error
            if error:
                self.stop()
                self.status.config(text=f"Képernyőhiba: {error}")
            else:
                count = self.service.viewer_count()
                text = f"Közvetítés aktív · {count} néző" if count else "Közvetítés aktív. Várakozás a nézőre…"
                self.status.config(text=text)
        self.root.after(500, self.check_capture)

    def callback_error(self, exc_type, exc, traceback):
        logging.error("GUI callback failed", exc_info=(exc_type, exc, traceback))
        messagebox.showerror(APP_NAME, f"Váratlan hiba: {exc}", parent=self.root)

    def close(self):
        self.stop()
        self.root.destroy()


def smoke_test(app):
    import pyaudiowpatch
    from av import Codec
    from PIL import Image

    Codec("libx264", "w")
    Codec("libopus", "w")
    if not hasattr(pyaudiowpatch.PyAudio, "get_default_wasapi_loopback"):
        raise RuntimeError("The Windows loopback audio module is missing from the application bundle.")
    app.tabs.select(app.browser_tab)
    app.root.update_idletasks()
    if not app.root.winfo_viewable() or not app.start_btn.winfo_viewable():
        raise RuntimeError("The graphical application did not create a visible window.")
    if app.capture_error:
        raise RuntimeError(app.capture_error)
    app.start_btn.invoke()
    if app.service is None:
        raise RuntimeError(app.status.cget("text"))
    capture = app.service.capture
    if capture.frame_after(-1, timeout=5)[1] is None:
        raise RuntimeError(capture.error or "MSS did not produce a desktop image.")
    conn = HTTPConnection(app.service.host, app.service.port, timeout=5)
    try:
        def request(method, route, status, body=None):
            conn.request(method, route, body)
            response = conn.getresponse()
            data = response.read()
            if response.status != status:
                raise RuntimeError(f"{route} returned HTTP {response.status}; expected {status}.")
            return data

        if b"<title>TV-PC Cast" not in request("GET", "/", 200):
            raise RuntimeError("The television page is missing from the application bundle.")
        request("GET", "/frame", 401)
        token = json.loads(request("POST", "/api/pair", 200, json.dumps({"pin": app.service.pin})))["token"]
        data = request("GET", "/frame?token=" + token, 200)
        with Image.open(io.BytesIO(data), formats=("JPEG",)) as image:
            image.load()
            image_size = image.size
    finally:
        conn.close()
    app.start_btn.invoke()
    if app.service is not None:
        raise RuntimeError("The GUI could not stop the local HTTP service.")
    return {"ok": True, "gui": True, "capture": True, "rtc_codecs": True, "version": VERSION,
            "image_size": image_size}


def run():
    parser = argparse.ArgumentParser(prog=APP_NAME)
    parser.add_argument("--smoke-test", type=Path, metavar="JSON_FILE", help="run a visible Windows startup test")
    args = parser.parse_args()
    log_path = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME / "startup.log"
    try:
        if not args.smoke_test:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            logging.basicConfig(handlers=[logging.FileHandler(log_path, encoding="utf-8", delay=True)], level=logging.WARNING,
                                format="%(asctime)s %(levelname)s %(message)s")
        app = DesktopApp(loopback=args.smoke_test is not None)
        if not args.smoke_test:
            app.root.mainloop()
            return 0

        result = {}

        def check():
            try:
                result.update(smoke_test(app))
            except Exception as exc:
                result.update(ok=False, error=str(exc))
            finally:
                app.close()

        app.root.after(250, check)
        app.root.mainloop()
        args.smoke_test.write_text(json.dumps(result), encoding="utf-8")
        return 0 if result.get("ok") else 1
    except Exception as exc:
        if args.smoke_test:
            args.smoke_test.write_text(json.dumps({"ok": False, "error": str(exc)}), encoding="utf-8")
        else:
            logging.exception("Application startup failed")
            messagebox.showerror(APP_NAME, f"Az alkalmazás nem indult el.\n{exc}\n\nNapló: {log_path}")
        return 1
