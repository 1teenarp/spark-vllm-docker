#!/bin/bash

# Usage: sudo ./configure_ib.sh [1|2]
NODE_ID=$1

if [[ -z "$NODE_ID" || ! "$NODE_ID" =~ ^[12]$ ]]; then
    echo "Usage: sudo $0 [1|2]"
    exit 1
fi

# 1. Improved extraction logic:
# We find the line containing 'enp1' and '(Up)'
# Then we use 'awk' to print the field immediately following the '==>' marker
INTERFACE=$(ibdev2netdev | grep "enp1" | grep "(Up)" | awk -F '==> ' '{print $2}' | awk '{print $1}')

if [[ -z "$INTERFACE" ]]; then
    echo "Error: Could not find an active 'enp1' interface."
    echo "Check output of ibdev2netdev manually."
    exit 1
fi

echo "Found active interface: $INTERFACE"

# 2. Assign IP based on Node ID
if [ "$NODE_ID" == "1" ]; then
    IP="192.168.100.10/24"
else
    IP="192.168.100.11/24"
fi

# 3. Apply Configuration
echo "Configuring $INTERFACE with IP $IP..."

# Clear existing and set new
sudo ip addr flush dev "$INTERFACE"
sudo ip addr add "$IP" dev "$INTERFACE"
sudo ip link set "$INTERFACE" up

echo "--- Verification ---"
ip addr show "$INTERFACE"
