const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const html = fs.readFileSync(path.join(__dirname, "../web/index.html"), "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function openViewer({ webRtc = false } = {}) {
  const requests = [];
  const images = [];
  const peers = [];
  const timers = new Map();
  const elements = new Map();
  let timerId = 0;
  let focused;

  function element(id) {
    const attributes = {};
    return {
      hidden: ["viewer", "rtc-video", "rtc-audio"].includes(id),
      value: "",
      textContent: "",
      setAttribute(name, value) { attributes[name] = value; },
      getAttribute(name) { return attributes[name]; },
      removeAttribute(name) { delete this[name]; },
      appendChild(child) { this.displayedImage = child; },
      replaceChild(child, oldChild) {
        assert.equal(this.displayedImage, oldChild);
        this.displayedImage = child;
      },
      removeChild(child) {
        assert.equal(this.displayedImage, child);
        this.displayedImage = undefined;
      },
      focus() { focused = id; },
    };
  }

  function get(id) {
    if (!elements.has(id)) elements.set(id, element(id));
    return elements.get(id);
  }

  function Image() {
    const image = element();
    image.naturalWidth = 0;
    images.push(image);
    return image;
  }

  function XMLHttpRequest() {
    requests.push(this);
    this.open = (method, url) => {
      this.method = method;
      this.url = url;
    };
    this.setRequestHeader = () => {};
    this.send = (body) => { this.body = JSON.parse(body); };
    this.abort = () => { this.aborted = true; };
    this.respond = (status, body) => {
      this.readyState = 4;
      this.responseText = JSON.stringify(body);
      this.status = status;
      this.onreadystatechange();
    };
  }

  class Peer {
    constructor(config) {
      this.config = config;
      this.transceivers = [];
      this.iceGatheringState = "new";
      peers.push(this);
    }
    addTransceiver(kind, { direction }) { this.transceivers.push([kind, direction]); }
    createOffer() { return Promise.resolve({ type: "offer", sdp: "partial" }); }
    setLocalDescription(offer) {
      this.localDescription = offer;
      this.iceGatheringState = "gathering";
      return Promise.resolve();
    }
    completeIce() {
      this.localDescription = { type: "offer", sdp: "full sdp" };
      this.iceGatheringState = "complete";
      this.onicegatheringstatechange();
    }
    setRemoteDescription(answer) {
      this.answer = answer;
      return Promise.resolve();
    }
    close() { this.closed = true; }
  }

  class Stream {
    tracks = [];
    addTrack(track) { this.tracks.push(track); }
    getAudioTracks() { return this.tracks.filter(({ kind }) => kind === "audio"); }
  }

  const video = get("rtc-video");
  video.srcObject = null;
  video.paused = true;
  video.pause = () => { video.paused = true; };
  video.play = () => {
    video.paused = false;
    return Promise.resolve();
  };

  vm.runInNewContext(script, {
    document: { getElementById: get, addEventListener() {} },
    Image,
    XMLHttpRequest,
    window: {
      RTCPeerConnection: webRtc ? Peer : undefined,
      MediaStream: Stream,
      setTimeout(callback, delay) {
        timers.set(++timerId, { callback, delay });
        return timerId;
      },
      clearTimeout(id) { timers.delete(id); },
    },
  });

  return {
    get,
    images,
    peers,
    requests,
    timers,
    get focused() { return focused; },
    submit(pin) {
      get("pin").value = pin;
      let prevented = false;
      get("pair-form").onsubmit({ preventDefault() { prevented = true; } });
      assert.equal(prevented, true);
    },
    pair() {
      this.submit("012345");
      requests[0].respond(200, { token: "test=token" });
    },
    runNextTimer(expectedDelay) {
      const next = timers.entries().next().value;
      assert.ok(next, "a timer should be pending");
      const [id, { callback, delay }] = next;
      assert.equal(delay, expectedDelay);
      timers.delete(id);
      callback();
    },
  };
}

test("requires six digits and disables duplicate pairing while the PC is responding", () => {
  const viewer = openViewer();
  viewer.submit("12345");
  assert.equal(viewer.requests.length, 0);
  assert.match(viewer.get("error").textContent, /hat számjegyet/);
  assert.equal(viewer.focused, "pin");

  viewer.submit("012345");
  viewer.submit("012345");
  assert.equal(viewer.requests.length, 1);
  assert.equal(viewer.requests[0].method, "POST");
  assert.equal(viewer.requests[0].url, "/api/pair");
  assert.deepEqual(viewer.requests[0].body, { pin: "012345" });

  viewer.requests[0].respond(403, { error: "Hibás PIN." });
  assert.equal(viewer.get("connect").disabled, false);
  assert.equal(viewer.get("error").textContent, "Hibás PIN.");
});

function flushPromises() {
  return new Promise((resolve) => setImmediate(resolve));
}

test("a TV browser without receiver playback continues using MJPEG", () => {
  const viewer = openViewer();
  viewer.pair();
  viewer.get("rtc").onclick();
  assert.match(viewer.get("rtc-notice").textContent, /nem támogatja/);
  assert.equal(viewer.requests.length, 1);
  assert.equal(viewer.get("picture").displayedImage, viewer.images[0]);
});

test("waits for complete ICE, starts A/V muted, and releases it when switching to JPEG", async () => {
  const viewer = openViewer({ webRtc: true });
  viewer.pair();
  viewer.get("rtc").onclick();
  await flushPromises();
  const peer = viewer.peers[0];
  assert.deepEqual(peer.transceivers, [["video", "recvonly"], ["audio", "recvonly"]]);
  assert.equal(peer.config.iceServers.length, 0);
  assert.equal(viewer.requests.length, 1);
  peer.completeIce();
  peer.onicegatheringstatechange();
  assert.equal(viewer.requests.length, 2);
  const offer = viewer.requests[1];
  assert.equal(offer.method, "POST");
  assert.equal(offer.url, "/api/rtc/offer");
  assert.deepEqual(offer.body, { type: "offer", sdp: "full sdp", token: "test=token" });
  offer.respond(200, { type: "answer", sdp: "server sdp" });
  assert.equal(peer.answer.sdp, "server sdp");
  assert.equal(viewer.get("picture").displayedImage, viewer.images[0]);

  const video = viewer.get("rtc-video");
  peer.ontrack({ track: { kind: "video" } });
  peer.ontrack({ track: { kind: "audio" } });
  video.videoWidth = 1920;
  video.onplaying();
  assert.equal(video.srcObject.tracks.length, 2);
  assert.equal(video.muted, true);
  assert.equal(viewer.get("picture").hidden, true);
  assert.match(viewer.get("mode").textContent, /WebRTC · Hang némítva/);
  viewer.get("rtc-audio").onclick();
  await flushPromises();
  assert.equal(video.muted, false);
  assert.match(viewer.get("mode").textContent, /Hang bekapcsolva/);
  viewer.get("compat").onclick();
  assert.equal(peer.closed, true);
  assert.equal(video.srcObject, null);
  assert.equal(video.hidden, true);
  assert.equal(viewer.get("picture").hidden, false);
  assert.match(viewer.images[1].src, /^\/frame\?/);
});

test("a signaling error leaves MJPEG running with the server's explanation", async () => {
  const viewer = openViewer({ webRtc: true });
  viewer.pair();
  viewer.get("rtc").onclick();
  await flushPromises();
  const peer = viewer.peers[0];
  peer.completeIce();
  viewer.requests[1].respond(503, { error: "A PC hangrögzítése nem elérhető." });
  assert.equal(peer.closed, true);
  assert.match(viewer.get("rtc-notice").textContent, /hangrögzítése nem elérhető/);
  assert.equal(viewer.get("picture").displayedImage, viewer.images[0]);
  assert.equal(viewer.get("rtc").getAttribute("aria-pressed"), "false");
});

test("negotiation is bounded and disconnect aborts a queued offer", async () => {
  const viewer = openViewer({ webRtc: true });
  viewer.pair();
  viewer.images[0].onload();
  viewer.get("rtc").onclick();
  await flushPromises();
  viewer.runNextTimer(25000);
  assert.equal(viewer.peers[0].closed, true);
  assert.match(viewer.get("rtc-notice").textContent, /nem indult el időben/);

  viewer.get("rtc").onclick();
  await flushPromises();
  viewer.peers[1].completeIce();
  const offer = viewer.requests[1];
  viewer.get("disconnect").onclick();
  assert.equal(offer.aborted, true);
  offer.respond(200, { type: "answer", sdp: "late response" });
  assert.equal(viewer.peers[1].answer, undefined);
  assert.equal(viewer.get("rtc-notice").textContent, "");
});

test("a stalled pairing request can be retried", () => {
  const viewer = openViewer();
  viewer.submit("012345");
  viewer.runNextTimer(6000);
  assert.equal(viewer.requests[0].aborted, true);
  assert.equal(viewer.get("connect").disabled, false);
  assert.match(viewer.get("error").textContent, /nem válaszol/);
});

test("keeps MJPEG when the first frame is visible without a load event", () => {
  const viewer = openViewer();
  viewer.pair();
  assert.equal(viewer.focused, "show-controls");
  assert.equal(viewer.get("pin").value, "");
  assert.equal(viewer.images[0].src, "/stream?token=test%3Dtoken");
  viewer.images[0].naturalWidth = 1920;
  viewer.runNextTimer(4000);
  assert.match(viewer.get("mode").textContent, /Élő kép · MJPEG/);
  assert.equal(viewer.images.length, 1);
});

test("switches to JPEG automatically when opening the MJPEG stream stalls", () => {
  const viewer = openViewer();
  viewer.pair();
  viewer.runNextTimer(4000);
  assert.equal(viewer.images[0].src, undefined);
  assert.equal(viewer.images[1].src, "/frame?token=test%3Dtoken&n=1");
  assert.equal(viewer.get("compat").getAttribute("aria-pressed"), "true");
});

test("JPEG retries preserve the last successful frame and cancel the request on disconnect", () => {
  const viewer = openViewer();
  viewer.pair();
  viewer.images[0].onerror();
  const first = viewer.images[1];
  first.onload();
  assert.equal(viewer.get("picture").displayedImage, first);
  assert.match(viewer.get("mode").textContent, /Élő kép · JPEG/);

  viewer.get("show-controls").onclick();
  assert.equal(viewer.get("controls").hidden, true);
  viewer.runNextTimer(33);
  viewer.runNextTimer(5000);
  assert.equal(viewer.get("picture").displayedImage, first);
  assert.match(viewer.get("mode").textContent, /nem elérhető/);
  assert.equal(viewer.get("controls").hidden, false);
  viewer.runNextTimer(1500);

  viewer.get("disconnect").onclick();
  assert.equal(viewer.get("viewer").hidden, true);
  assert.equal(viewer.get("pairing").hidden, false);
  assert.equal(viewer.get("picture").displayedImage, undefined);
  assert.equal(viewer.images[3].src, undefined);
  assert.equal(viewer.timers.size, 0);
  assert.equal(viewer.focused, "pin");
});
