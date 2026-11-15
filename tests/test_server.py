"""Integration tests for PIN auth, HTTP frame delivery and lockout."""
import http.client
import io
import json
from types import SimpleNamespace

from PIL import Image
import pytest

from tvpc_cast import CaptureWorker, CastService


JPEG = b"\xff\xd8\xff\xd9"


class DummyCapture:
    def __init__(self):
        self.error = None
        self.stopped = False

    def start(self):
        self.stopped = False

    def stop(self):
        self.stopped = True

    def frame_after(self, sequence, timeout=3):
        return 1, JPEG


@pytest.fixture
def service():
    server = CastService(capture=DummyCapture(), host="127.0.0.1", port=0)
    server.start()
    yield server
    server.stop()


def request(server, method, path, payload=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    data = json.dumps(payload).encode() if payload is not None else None
    conn.request(
        method, path, body=data,
        headers={"Content-Type": "application/json"} if data else {}
    )
    result = conn.getresponse()
    body = result.read()
    headers = dict(result.getheaders())
    status = result.status
    conn.close()
    return status, headers, body


def test_page_and_health(service):
    status, headers, body = request(service, "GET", "/")
    assert status == 200
    assert b"TV-PC Cast" in body
    assert service.pin.encode() not in body
    status, _, body = request(service, "GET", "/health")
    assert status == 200
    assert json.loads(body)["running"] is True


def test_pin_protects_frame(service):
    assert request(service, "GET", "/frame")[0] == 401
    assert request(service, "POST", "/api/pair", {"pin": "0000000"})[0] == 403
    status, _, body = request(service, "POST", "/api/pair", {"pin": service.pin})
    assert status == 200
    token = json.loads(body)["token"]
    assert len(token) > 30
    assert request(service, "GET", "/frame?token=bad")[0] == 401
    status, headers, body = request(service, "GET", "/frame?token=" + token)
    assert status == 200
    assert headers["Content-Type"] == "image/jpeg"
    assert body == JPEG


def test_stream_is_multipart(service):
    status, _, body = request(service, "POST", "/api/pair", {"pin": service.pin})
    token = json.loads(body)["token"]
    conn = http.client.HTTPConnection("127.0.0.1", service.port, timeout=5)
    conn.request("GET", "/stream?token=" + token)
    response = conn.getresponse()
    assert response.status == 200
    assert response.getheader("Content-Type").startswith("multipart/x-mixed-replace")
    assert b"--tvframe" in response.read(9)
    conn.close()


def test_rate_limit_and_invalid_requests(service):
    assert request(service, "POST", "/api/pair", {"pin": []})[0] == 403
    assert request(service, "POST", "/api/pair", {"pin": "123"})[0] == 403
    assert request(service, "POST", "/api/pair", {"pin": "aaa"})[0] == 403
    assert request(service, "POST", "/api/pair", {"pin": None})[0] == 403
    assert request(service, "POST", "/api/pair", {"pin": {}})[0] == 403
    assert request(service, "POST", "/api/pair", {"pin": service.pin})[0] == 429
    assert request(service, "POST", "/api/pair", [1, 2, 3])[0] == 400


def test_missing_route(service):
    assert request(service, "GET", "/not-here")[0] == 404


def test_non_ascii_pin_returns_an_http_error(service):
    assert request(service, "POST", "/api/pair", {"pin": "１２３４５６"})[0] == 403
    assert request(service, "POST", "/api/pair", {"pin": service.pin})[0] == 200


def test_webrtc_offer_requires_pin_and_valid_sdp(service, monkeypatch):
    def answer(token, sdp, client_ip):
        assert service.authorized(token)
        assert sdp == "v=0\r\nexample"
        assert client_ip == "127.0.0.1"
        return {"type": "answer", "sdp": "v=0\r\nanswer", "audio_available": True}

    monkeypatch.setattr(service, "rtc_answer", answer)
    route = "/api/rtc/offer"
    offer = {"type": "offer", "sdp": "v=0\r\nexample"}
    assert request(service, "POST", route, offer)[0] == 401
    _, _, pairing = request(service, "POST", "/api/pair", {"pin": service.pin})
    offer["token"] = json.loads(pairing)["token"]
    assert request(service, "POST", route, {**offer, "sdp": "bad"})[0] == 400
    status, _, response = request(service, "POST", route, offer)
    assert status == 200
    assert json.loads(response)["audio_available"] is True


def test_capture_all_monitors_preserves_aspect_ratio_and_limits_height(monkeypatch):
    desktop = {"width": 300, "height": 600, "left": -100, "top": 0}
    primary = {"width": 200, "height": 600, "left": 0, "top": 0}

    class FakeScreen:
        monitors = [desktop, primary]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def grab(self, bounds):
            assert bounds == desktop
            size = bounds["width"], bounds["height"]
            return SimpleNamespace(size=size, bgra=bytes(size[0] * size[1] * 4))

    monkeypatch.setattr("mss.mss", FakeScreen)
    worker = CaptureWorker(monitor=0, max_width=100, max_height=150)
    worker.start()
    try:
        _, data = worker.frame_after(-1)
        assert data is not None, worker.error
        with Image.open(io.BytesIO(data)) as image:
            assert image.size == (75, 150)
        _, snapshot = worker.snapshot_after(-1)
        assert snapshot.size == (75, 150)
    finally:
        worker.stop()
