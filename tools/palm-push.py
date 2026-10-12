#!/usr/bin/env python3
"""Minimal OBEX Object Push client for sending .prc (and other) files to a
Palm OS device over Bluetooth RFCOMM. No third-party dependencies.

Usage:
    palm-push.py <bdaddr> <file> [channel]

The OBEX Object Push channel is auto-discovered via `sdptool` when available,
otherwise defaults to RFCOMM channel 10.

Works with the Tungsten E2 / Garnet devices: put the device in Bluetooth
"Discoverable" mode and accept the incoming file on the Palm.
"""

import os
import re
import socket
import subprocess
import time
import sys

MAX_PACKET = 4096
DEFAULT_CHANNEL = 10


def discover_push_channel(addr: str) -> int | None:
    try:
        out = subprocess.run(
            ["sdptool", "browse", addr], capture_output=True, text=True, timeout=20
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    # Split the dump into individual service records and look at the one whose
    # name matches OBEX Object Push; grab its RFCOMM channel.
    for record in re.split(r"(?=Service Name:)", out):
        if "obex object push" in record.lower():
            chan = re.search(r"Channel:\s*(\d+)", record)
            if chan:
                return int(chan.group(1))
    return None


def find_open_channel(addr: str, max_channel: int = 30) -> int | None:
    """Quick scan to find the first RFCOMM channel that accepts a connection.
    Used when SDP is unreachable (common with Palm devices whose radio sleeps).
    """
    for ch in range(1, max_channel + 1):
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM,
                          socket.BTPROTO_RFCOMM)
        s.settimeout(2)
        try:
            s.connect((addr, ch))
            s.close()
            return ch
        except OSError:
            s.close()
            continue
    return None


def unicode_header(tag: int, value: str) -> bytes:
    data = value.encode("utf-16-be") + b"\x00\x00"
    length = 3 + len(data)
    return bytes([tag]) + length.to_bytes(2, "big") + data


def body_header(tag: int, data: bytes) -> bytes:
    length = 3 + len(data)
    return bytes([tag]) + length.to_bytes(2, "big") + data


def packet(opcode: int, headers: bytes) -> bytes:
    length = 3 + len(headers)
    if length > 0xFFFF:
        raise ValueError("packet too large")
    return bytes([opcode]) + length.to_bytes(2, "big") + headers


def recv_packet(sock: socket.socket):
    first = sock.recv(1)
    if not first:
        raise EOFError("connection closed by peer")
    length = int.from_bytes(sock.recv(2), "big")
    payload = b""
    while len(payload) < length - 3:
        chunk = sock.recv(length - 3 - len(payload))
        if not chunk:
            raise EOFError("connection closed mid-packet")
        payload += chunk
    return first[0], payload


def expect_response(sock: socket.socket, what: str) -> int:
    op, payload = recv_packet(sock)
    # OBEX responses encode the response code in the low 7 bits of the first
    # byte (bit 7 = final). Success = 0x20, Continue = 0x10 (0x90 before the
    # final bit is masked off). Some stacks put the code in the payload
    # instead; handle both.
    code = op & 0x7F
    if code != 0x20:
        code = payload[0] & 0x7F if payload else code
    if code in (0x20, 0x10):
        return code
    raise RuntimeError(f"{what} failed: response 0x{op:02x} (code 0x{code:02x})")


def put(sock: socket.socket, name: str, data: bytes) -> None:
    # CONNECT with a Target header for OBEX Object Push (UUID 0x1105); some
    # Palm OS builds ignore a CONNECT that does not name the service.
    target = bytes([0x46, 0x00, 0x05, 0x05, 0x11])
    connect_pkt = (
        bytes([0x80])
        + (7 + len(target)).to_bytes(2, "big")
        + bytes([0x10, 0x00])
        + MAX_PACKET.to_bytes(2, "big")
        + target
    )
    sock.sendall(connect_pkt)
    expect_response(sock, "CONNECT")

    name_hdr = unicode_header(0x01, name)
    budget = MAX_PACKET - 3

    if len(name_hdr) + 3 + len(data) <= budget:
        sock.sendall(packet(0x82, name_hdr + body_header(0x49, data)))
        expect_response(sock, "PUT")
    else:
        # Chunked PUT: non-final packets carry body with header 0x48, the
        # final packet carries the remainder with header 0x49.
        remain = data
        first = True
        while remain:
            capacity = budget - len(name_hdr) - 3 if first else budget - 3
            chunk, remain = remain[:capacity], remain[capacity:]
            final = not remain
            body_tag = 0x49 if final else 0x48
            hdrs = name_hdr + body_header(body_tag, chunk) if first else body_header(body_tag, chunk)
            opcode = 0x82 if final else 0x02
            sock.sendall(packet(opcode, hdrs))
            expect_response(sock, "PUT")
            first = False

    # The E2 accepts the PUT, then commonly hangs instead of replying to
    # OBEX DISCONNECT. Do not hold the Bluetooth link open for the transfer
    # socket's full 120-second I/O timeout.
    sock.settimeout(3)
    sock.sendall(bytes([0x81, 0x03, 0x00, 0x00]))
    try:
        expect_response(sock, "DISCONNECT")
    except (TimeoutError, OSError, EOFError):
        pass  # the Palm often closes without replying once the file is in


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    addr = sys.argv[1]
    path = sys.argv[2]
    channel = int(sys.argv[3]) if len(sys.argv) > 3 else None
    if not os.path.isfile(path):
        print(f"file not found: {path}")
        return 1

    if channel is None:
        channel = discover_push_channel(addr)
        if channel is None:
            print("SDP unreachable; scanning RFCOMM channels 1..30...", file=sys.stderr)
            channel = find_open_channel(addr)
        channel = channel or DEFAULT_CHANNEL
        print(f"OBEX Object Push channel: {channel}")

    data = open(path, "rb").read()
    name = os.path.basename(path)

    attempts = 3
    sock = None
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            print(
                f"-> retry {attempt}/{attempts}: wake the Palm and keep its Bluetooth on...",
                file=sys.stderr,
            )
            time.sleep(5)
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM,
                             socket.BTPROTO_RFCOMM)
        sock.settimeout(120)
        try:
            sock.connect((addr, channel))
            break
        except (ConnectionRefusedError, OSError) as exc:
            sock.close()
            sock = None
            last_exc = exc
    else:
        print(
            f"connection to {addr} channel {channel} failed: {last_exc}",
            file=sys.stderr,
        )
        print("hints:", file=sys.stderr)
        print("  - check pairing: bluetoothctl info <addr>  -> 'Paired: yes'", file=sys.stderr)
        print("  - on the Palm: Bluetooth app open and ON; screen on (radio sleeps when idle)", file=sys.stderr)
        print("    Bluetooth app -> Options -> 'Allow wakeup' helps here", file=sys.stderr)
        print("  - on the Palm: Prefs -> General -> Beam Receive -> On  (must not be Off)", file=sys.stderr)
        return 1

    try:
        print(f"sending {name} ({len(data)} bytes) -> {addr}", flush=True)
        print("-> WATCH THE PALM: tap Accept/Receive when it prompts", file=sys.stderr, flush=True)
        put(sock, name, data)
        print("OK: file accepted")
        return 0
    finally:
        sock.close()


if __name__ == "__main__":
    sys.exit(main())
