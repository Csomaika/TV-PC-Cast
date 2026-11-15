import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from ipaddress import IPv4Network

import pytest

import lan_discovery as lan


@pytest.mark.parametrize(
    "location",
    [
        "http://192.168.1.91/descriptor.xml",
        "http://localhost/descriptor.xml",
        "http://domain.example/descriptor.xml",
        "http://169.254.169.254/descriptor.xml",
        "https://192.168.1.90/descriptor.xml",
        "http://user@192.168.1.90/descriptor.xml",
        "http://192.168.1.90:0/descriptor.xml",
        "http://192.168.1.90:99999/descriptor.xml",
        "http://192.168.1.90//domain.example/descriptor.xml",
        "http://192.168.1.90/descriptor.xml#fragment",
        "http://192.168.1.90/descriptor.xml\r\nX-Test: added",
    ],
)
def test_descriptor_location_must_target_literal_responding_ip(location):
    assert lan._descriptor_endpoint(location, "192.168.1.90") is None


def test_same_peer_descriptor_endpoint_preserves_query():
    assert lan._descriptor_endpoint("http://192.168.1.90:8080/desc.xml?type=tv", "192.168.1.90") == (
        8080, "/desc.xml?type=tv",
    )


def test_discovery_rejects_public_addresses_before_opening_socket(monkeypatch):
    def unexpected_lookup(*_args):
        raise AssertionError("Interface lookup should not run for a non-LAN address")

    monkeypatch.setattr(lan, "_local_network", unexpected_lookup)
    for address in ("127.0.0.1", "8.8.8.8", "192.0.2.1", "::1"):
        with pytest.raises(ValueError):
            lan.discover_devices(address)


def response(st, location=None, server=None):
    headers = ["HTTP/1.1 200 OK", f"sT: {st}"]
    if location:
        headers.append(f"Location: {location}")
    if server:
        headers.append(f"SERVER: {server}")
    return ("\r\n".join(headers) + "\r\n\r\n").encode("ascii")


def test_ssdp_uses_selected_subnet_and_distinguishes_cast_from_dial(monkeypatch):
    dial = "urn:dial-multiscreen-org:service:dial:1"
    renderer = "urn:schemas-upnp-org:device:MediaRenderer:1"
    pending = IteratingSocket([
        (response(dial, "http://192.168.1.90/desc.xml", "Linux UPnP/1.0 Chromecast/1.6.18"), "192.168.1.90"),
        (response(dial, "http://192.168.1.90/falsely-advertised-cross-host.xml"), "192.168.1.91"),
        (response(renderer, "http://192.168.1.92/desc.xml"), "192.168.1.92"),
        (response("urn:schemas-upnp-org:service:AVTransport:1"), "192.168.1.91"),
        (response(renderer), "192.168.2.90"),
        (response(renderer), "192.168.1.110"),
        (b"NOTIFY * HTTP/1.1\r\nST: unexpected\r\n\r\n", "192.168.1.93"),
    ])
    monkeypatch.setattr(lan, "_local_network", lambda _address: IPv4Network("192.168.1.0/24"))
    monkeypatch.setattr(lan.socket, "socket", lambda *_args: pending)
    descriptor_reads = []

    def read_fake_descriptor(source, peer, endpoint, _deadline):
        descriptor_reads.append((source, peer, endpoint))
        return b""

    monkeypatch.setattr(lan, "_read_descriptor", read_fake_descriptor)

    assert lan.discover_devices("192.168.1.110") == [
        lan.LanDevice("192.168.1.90", "", "", "google_cast", ("dial",)),
        lan.LanDevice("192.168.1.92", "", "", "renderer", ("MediaRenderer",)),
        lan.LanDevice("192.168.1.91", "", "", "upnp", ("AVTransport", "dial")),
    ]
    assert pending.bound == ("192.168.1.110", 0)
    assert (socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1) in pending.options
    assert all(target == ("239.255.255.250", 1900) for _, target in pending.requests)
    assert b"ST: ssdp:all\r\n" in pending.requests[0][0]
    assert sorted(descriptor_reads) == [
        ("192.168.1.110", "192.168.1.90", (80, "/desc.xml")),
        ("192.168.1.110", "192.168.1.92", (80, "/desc.xml")),
    ]


class IteratingSocket:
    def __init__(self, packets):
        self.packets = iter(packets)
        self.options = []
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def bind(self, args):
        self.bound = args

    def setsockopt(self, *args):
        self.options.append(args)

    def settimeout(self, timeout):
        assert 0 < timeout < 3

    def sendto(self, data, destination):
        self.requests.append((data, destination))

    def recvfrom(self, _size):
        try:
            packet, ip = next(self.packets)
        except StopIteration:
            raise TimeoutError from None
        return packet, (ip, 1900)


def test_device_description_prefers_embedded_media_renderer():
    description = """<root xmlns="urn:schemas-upnp-org:device-1-0">
      <device>
        <deviceType>urn:schemas-upnp-org:device:Basic:1</deviceType>
        <friendlyName>Shared appliance</friendlyName>
        <deviceList><device>
          <deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
          <friendlyName>  Nappali TV </friendlyName>
          <modelName>Hisense</modelName>
          <modelNumber>65E8S</modelNumber>
          <serviceList><service>
            <serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType>
          </service></serviceList>
        </device></deviceList>
      </device>
    </root>""".encode("utf-8")

    assert lan._descriptor_details(description) == ("Nappali TV", "Hisense 65E8S", {"MediaRenderer", "RenderingControl"})


def test_descriptor_rejects_entity_declarations_and_malformed_xml():
    with_entity = '<!DOCTYPE root [<!ENTITY name "Example TV">]><root><device><friendlyName>&name;</friendlyName></device></root>'
    for content in (with_entity.encode("utf-8"), with_entity.encode("utf-16"), b"<root><device>"):
        assert lan._descriptor_details(content) == ("", "", set())


def test_descriptor_http_does_not_follow_redirects_and_caps_content_length():
    requested = []

    class TestHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            requested.append(self.path)
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/descriptor")
                self.send_header("Content-Length", "0")
            else:
                self.send_response(200)
                length = lan._MAX_DESCRIPTOR + 1 if self.path == "/oversized" else 4
                self.send_header("Content-Length", str(length))
            self.end_headers()
            if self.path == "/descriptor":
                self.wfile.write(b"<x/>")

    with HTTPServer(("127.0.0.1", 0), TestHandler) as server:
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        worker.start()
        try:
            port = server.server_address[1]
            assert lan._read_descriptor("127.0.0.1", "127.0.0.1", (port, "/redirect"), time.monotonic() + 1) == b""
            assert lan._read_descriptor("127.0.0.1", "127.0.0.1", (port, "/oversized"), time.monotonic() + 1) == b""
            assert lan._read_descriptor("127.0.0.1", "127.0.0.1", (port, "/descriptor"), time.monotonic() + 1) == b"<x/>"
        finally:
            server.shutdown()
            worker.join(timeout=1)

    assert requested == ["/redirect", "/oversized", "/descriptor"]
