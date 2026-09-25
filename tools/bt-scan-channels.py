#!/usr/bin/env python3
"""Scan RFCOMM channels on a Bluetooth device to find which ones accept a
connection. Palm OS OBEX push channels are usually in 1..30."""
import socket
import sys

addr = sys.argv[1]
print(f"scanning {addr} channels 1..30 (keep the Palm awake)...")
for ch in range(1, 31):
    s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM,
                      socket.BTPROTO_RFCOMM)
    s.settimeout(3)
    try:
        s.connect((addr, ch))
        print(f"  channel {ch}: CONNECTED (open)")
        s.close()
    except (ConnectionRefusedError, OSError):
        pass
    except Exception as exc:
        print(f"  channel {ch}: {exc}")
print("scan done")