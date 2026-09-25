# palm-obex-push

Install `.prc` apps on a Palm OS device over Bluetooth, straight from a Linux
box — no Windows, no HotSync cable, no Palm Desktop.

This repo is a small set of **dependency-free** tools for pushing already-built
`.prc` files to a Palm. It was developed against a **PalmOne Tungsten E2**
(Palm OS 5.4 Garnet) but should work with any Palm that does OBEX Object Push
over Bluetooth.

## What's in here

| File | Purpose |
| --- | --- |
| `tools/palm-push.py` | OBEX Object Push client (pure Python stdlib, no deps). Sends a `.prc` to the Palm over Bluetooth RFCOMM. |
| `tools/palm-pair.sh` | Pairs + trusts the Palm via `bluetoothctl` (the Palm uses legacy PIN pairing). |
| `tools/bt-scan-channels.py` | Scans RFCOMM channels 1–30 to find which one accepts a connection. |

## Prerequisites

- Linux with BlueZ: `bluetoothctl` (and optionally `sdptool`).
- A Bluetooth adapter (`hci0`).
- Python 3 (standard library only — no `pip install` needed).
- A Palm OS device with Bluetooth (tested on the Tungsten E2 / Garnet 5.4).

## Usage

On the Palm, before you start:

1. **Prefs → General → Beam Receive → On** (must not be Off, or beamed files
   are silently ignored).
2. **Bluetooth app → On** and set **Discoverable**; keep the screen on while
   pushing (the radio sleeps when idle).

Then on the Linux box:

```sh
# find the Palm's address
bluetoothctl scan on

# pair (legacy PIN pairing — default pin 0000, enter the same on the Palm)
tools/palm-pair.sh <BD_ADDR> [pin]

# confirm it's paired
bluetoothctl info <BD_ADDR>    # look for "Paired: yes"

# push the .prc (script retries 3x — wake the Palm if it sleeps)
tools/palm-push.py <BD_ADDR> app.prc
```

On the Palm, tap **Accept/Receive** when prompted, then install the app. A
`.prc` over Bluetooth is the normal IR-style "beam" method and does **not**
require a HotSync.

## Tungsten E2 quirks (learned the hard way)

- The E2's SDP is unreachable from a modern Linux host; `palm-push.py` scans
  RFCOMM channels 1–30 instead. The E2 accepts pushes on **channel 1**, even
  though its SDP advertises 10 — ignore that.
- OBEX success responses carry the code in the opcode byte (`0xA0`), not the
  payload.
- The Palm replies to a non-final (chunked) PUT with **Continue** (`0x90`,
  which is `0x10` after the final bit is masked). Files larger than ~4 KB are
  sent chunked.
- After a successful transfer the E2 shows "Disconnecting…" and never replies
  to the OBEX DISCONNECT — the script treats that as non-fatal. The `.prc` is
  already installed; if "Disconnecting" sticks, soft-reset the Palm.

## Building `.prc` files (not included here)

These tools only **install** apps — they do **not** compile them. To build a
`.prc` from source you need a Palm OS toolchain, which is **not** part of this
repo. Download these two third-party projects and place them alongside these
tools:

```text
~/palm/
├── tools/               # this repo (palm-push.py, palm-pair.sh, bt-scan-channels.py)
├── palm-toolchain/      # git clone https://github.com/palmsnipe/palm-toolchain
└── palm-os-sdk/         # git clone https://github.com/jichu4n/palm-os-sdk
```

Then build the toolchain (its docs live in `palm-toolchain/README.md`):

```sh
cd palm-toolchain
PALM_SDK_SOURCE="$HOME/palm/palm-os-sdk/sdk-5r4" make setup
make check
```

`make setup` copies the SDK into `.toolchain/prefix/palmdev/sdk`. The SDK
directory is user-supplied and never modified.

## License

MIT. The third-party toolchain projects referenced above keep their own
licenses — see their repos.
