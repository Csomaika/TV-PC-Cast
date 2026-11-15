"""Discover devices that answer standard SSDP discovery on a selected Windows LAN."""

from __future__ import annotations

import ctypes
import io
import math
import re
import socket
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from http.client import HTTPException, HTTPResponse
from ipaddress import IPv4Address, IPv4Network
from urllib.parse import urlsplit
from xml.etree import ElementTree


_MULTICAST_ADDRESS = ("239.255.255.250", 1900)
_SEARCH_TARGETS = ("ssdp:all", "urn:schemas-upnp-org:device:MediaRenderer:1")
_PRIVATE_NETWORKS = tuple(map(IPv4Network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")))
_IP_TABLE_ROW = struct.Struct("=4sI4sIIHH")
_MAX_DEVICES = 64
_MAX_DESCRIPTOR = 96 * 1024
_RENDERER_TYPES = {"mediarenderer", "renderingcontrol"}
_TYPE_URN = re.compile(r"urn:[a-z0-9.-]+:(?:device|service):([a-z0-9_.-]{1,64}):[0-9]+", re.I)
_CAST_SERVER = re.compile(r"(?:^|[\s,;(])Chromecast/[0-9]", re.I)


@dataclass(frozen=True)
class LanDevice:
    ip: str
    name: str
    model: str
    kind: str
    services: tuple[str, ...]


@dataclass
class _Announcements:
    services: set[str] = field(default_factory=set)
    endpoints: set[tuple[int, str]] = field(default_factory=set)
    google_cast: bool = False


def _is_private(address):
    return any(address in network for network in _PRIVATE_NETWORKS)


def _local_network(address):
    """Look up the selected interface's IPv4 mask using the Windows IP Helper API."""
    if sys.platform != "win32":
        raise OSError("A helyi eszközkeresés Windowson érhető el.")
    get_table = ctypes.WinDLL("iphlpapi").GetIpAddrTable
    get_table.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.c_int32)
    get_table.restype = ctypes.c_uint32
    size = ctypes.c_uint32()
    result = get_table(None, ctypes.byref(size), False)
    if result != 122:  # ERROR_INSUFFICIENT_BUFFER reports the required table size.
        raise ctypes.WinError(result)
    for _ in range(2):
        table = ctypes.create_string_buffer(size.value)
        result = get_table(table, ctypes.byref(size), False)
        if result != 122:
            break
    if result:
        raise ctypes.WinError(result)
    count = struct.unpack_from("=I", table)[0]
    for remote, _, mask, *_ in _IP_TABLE_ROW.iter_unpack(table.raw[4:4 + count * _IP_TABLE_ROW.size]):
        if IPv4Address(remote) == address:
            return IPv4Network((address, str(IPv4Address(mask))), strict=False)
    raise OSError("A kiválasztott IPv4-cím már nem érhető el a gépen.")


def _target_name(urn):
    match = _TYPE_URN.fullmatch(urn)
    return match.group(1) if match else ""


def _renderer(services):
    return any(service.casefold() in _RENDERER_TYPES for service in services)


def _response_headers(packet):
    if len(packet) > 8192:
        return {}
    lines = packet.decode("latin-1").splitlines()
    if not lines or not re.fullmatch(r"HTTP/1\.[01] +200(?: .*|)", lines[0], re.I):
        return {}
    headers = {}
    for line in lines[1:]:
        name, separator, value = line.partition(":")
        if not line:
            break
        if separator:
            headers.setdefault(name.strip().casefold(), value.strip())
    return headers


def _descriptor_endpoint(location, source_ip):
    if not location or len(location) > 1024 or any(not 32 < ord(ch) < 127 for ch in location):
        return None
    try:
        url = urlsplit(location)
        port = 80 if url.port is None else url.port
    except ValueError:
        return None
    if (url.scheme != "http" or url.hostname != source_ip or "@" in url.netloc
            or url.fragment or not port or url.path.startswith("//")):
        return None
    target = url.path or "/"
    if url.query:
        target += "?" + url.query
    return port, target


def _collect_responses(local_ip, network, deadline):
    announcements: dict[str, _Announcements] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as udp:
        udp.bind((local_ip, 0))
        udp.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip))
        udp.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        for target in _SEARCH_TARGETS:
            request = (
                'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\n'
                f"MX: 1\r\nST: {target}\r\n\r\n"
            )
            udp.sendto(request.encode("ascii"), _MULTICAST_ADDRESS)
        while (remaining := deadline - time.monotonic()) > 0:
            udp.settimeout(remaining)
            try:
                packet, (source_ip, _) = udp.recvfrom(65535)
            except TimeoutError:
                break
            peer = IPv4Address(source_ip)
            if peer not in network or not _is_private(peer) or source_ip == local_ip:
                continue
            if source_ip not in announcements and len(announcements) >= _MAX_DEVICES:
                continue
            headers = _response_headers(packet)
            if "st" not in headers:
                continue
            item = announcements.setdefault(source_ip, _Announcements())
            service = _target_name(headers["st"])
            if service and len(item.services) < 32:
                item.services.add(service)
            if _CAST_SERVER.search(headers.get("server", "")):
                item.google_cast = True
            endpoint = _descriptor_endpoint(headers.get("location", ""), source_ip)
            if endpoint and len(item.endpoints) < 4:
                item.endpoints.add(endpoint)
    return announcements


class _BoundedReader(io.RawIOBase):
    """Give the HTTP parser one time and byte budget across all socket reads."""

    def __init__(self, connection, deadline):
        self.connection = connection
        self.deadline = deadline
        self.remaining = _MAX_DESCRIPTOR + 16384

    def readable(self):
        return True

    def readinto(self, buffer):
        if self.remaining == 0:
            raise ValueError("UPnP descriptor response exceeded the byte limit.")
        timeout = self.deadline - time.monotonic()
        if timeout <= 0:
            raise TimeoutError("UPnP descriptor response timed out.")
        self.connection.settimeout(timeout)
        count = self.connection.recv_into(buffer, min(len(buffer), self.remaining))
        self.remaining -= count
        return count

    def makefile(self, *_args):
        return io.BufferedReader(self)


def _read_descriptor(local_ip, peer_ip, endpoint, deadline):
    port, target = endpoint
    timeout = min(0.65, deadline - time.monotonic())
    if timeout <= 0:
        return b""
    request = (
        f"GET {target} HTTP/1.1\r\nHost: {peer_ip}:{port}\r\n"
        "Connection: close\r\nAccept-Encoding: identity\r\n\r\n"
    ).encode("ascii")
    end = time.monotonic() + timeout
    with socket.create_connection((peer_ip, port), timeout=timeout, source_address=(local_ip, 0)) as connection:
        timeout = end - time.monotonic()
        if timeout <= 0:
            return b""
        connection.settimeout(timeout)
        connection.sendall(request)
        with HTTPResponse(_BoundedReader(connection, end)) as response:
            response.begin()
            if response.status != 200 or (response.length is not None and response.length > _MAX_DESCRIPTOR):
                return b""
            content = response.read(_MAX_DESCRIPTOR + 1)
            return content if len(content) <= _MAX_DESCRIPTOR else b""


def _label(text):
    return "".join(ch for ch in " ".join((text or "").split()) if ch.isprintable())[:120]


def _descriptor_details(content):
    if not content or b"<!DOCTYPE" in content.replace(b"\x00", b"").upper():
        return "", "", set()
    try:
        root = ElementTree.fromstring(content)
    except (ElementTree.ParseError, LookupError):
        return "", "", set()
    default = "", "", set()
    for device in root.findall(".//{*}device"):
        service_types = [_target_name(device.findtext("{*}deviceType", ""))]
        service_types.extend(
            _target_name(service.text or "")
            for service in device.findall("{*}serviceList/{*}service/{*}serviceType")
        )
        types = {value for value in service_types if value}
        name = _label(device.findtext("{*}friendlyName"))
        model = _label(device.findtext("{*}modelName"))
        number = _label(device.findtext("{*}modelNumber"))
        if number and number.casefold() not in model.casefold():
            model = " ".join(part for part in (model, number) if part)
        if _renderer(types):
            return name, model, types
        if not any(default):
            default = name, model, types
    return default


def _read_device(local_ip, ip, announcement, deadline):
    name = model = ""
    services = set(announcement.services)
    for endpoint in sorted(announcement.endpoints):
        try:
            details = _descriptor_details(_read_descriptor(local_ip, ip, endpoint, deadline))
        except (OSError, ValueError, HTTPException):
            continue
        other_name, other_model, other_services = details
        name = name or other_name
        model = model or other_model
        services.update(other_services)
        if _renderer(other_services) or (name and model):
            break
    kind = "google_cast" if announcement.google_cast else "renderer" if _renderer(services) else "upnp"
    return LanDevice(ip, name, model, kind, tuple(sorted(services, key=str.casefold)))


def discover_devices(local_ip: str, timeout: float = 3.0) -> list[LanDevice]:
    """List responding UPnP devices and Cast announcements on one private IPv4 subnet."""
    address = IPv4Address(local_ip)
    if not _is_private(address):
        raise ValueError("Az eszközkereséshez válassz privát helyi IPv4-címet.")
    if not math.isfinite(timeout) or timeout <= 0 or timeout > 15:
        raise ValueError("A keresési időnek 0 és 15 másodperc között kell lennie.")
    network = _local_network(address)
    started = time.monotonic()
    announcements = _collect_responses(local_ip, network, started + timeout * 0.58)
    if not announcements:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(announcements))) as pool:
        pending = [pool.submit(_read_device, local_ip, ip, details, started + timeout)
                   for ip, details in announcements.items()]
        devices = [future.result() for future in pending]
    return sorted(devices, key=lambda item: (item.kind == "upnp", IPv4Address(item.ip)))
