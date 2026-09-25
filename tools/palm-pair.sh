#!/usr/bin/env bash
# Pair + trust a Palm OS device (e.g. Tungsten E2) over Bluetooth so OBEX
# pushes are accepted.
#
# Usage: palm-pair.sh <device-bdaddr> [pin]
#
# The Tungsten E2 uses LEGACY pairing (PIN code), so an agent must be active
# in the same bluetoothctl session as `pair`. Enter the SAME pin on the Palm
# when it asks. Default pin is 0000.
#
# On the Palm: Bluetooth app -> enable Bluetooth -> "Discoverable" (and
# "Visible to all") before running. Accept the pairing prompt and enter the pin.

set -euo pipefail

ADDR="${1:?usage: palm-pair.sh <device-bdaddr> [pin]}"
PIN="${2:-0000}"

bluetoothctl power on >/dev/null

echo "-> Make the Palm discoverable, then pairing with pin '$PIN'"
echo "   (enter '$PIN' on the Palm too if it asks)"

# agent + default-agent + pair + pin must all share one bluetoothctl session,
# otherwise the agent is unregistered before pairing starts.
printf 'agent on\ndefault-agent\npair %s\n%s\ntrust %s\nquit\n' \
    "$ADDR" "$PIN" "$ADDR" | bluetoothctl

echo
echo "-> Verify with:  bluetoothctl info $ADDR   (look for 'Paired: yes')"
echo "-> Then push:    palm-push.py $ADDR <file.prc>"