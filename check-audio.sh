#!/bin/bash
echo "Audio Device Check"
echo "=================="
echo
echo "1. Sound Cards:"
cat /proc/asound/cards 2>/dev/null || echo "No cards file"
echo
echo "2. Recording Devices:"
arecord -l 2>/dev/null || echo "No recording devices"
echo
echo "3. Device Permissions:"
ls -la /dev/snd/ 2>/dev/null || echo "No /dev/snd directory"
echo
echo "4. Current User Groups:"
groups
echo
echo "5. USB Devices:"
lsusb | grep -i audio || echo "No USB audio devices detected"
