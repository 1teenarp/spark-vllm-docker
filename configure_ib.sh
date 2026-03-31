#!/bin/bash

# Usage: sudo ./configure_ib.sh [1|2]
# Pass '1' for Node 1 (192.168.100.10)
# Pass '2' for Node 2 (192.168.100.11)

NODE_ID=$1

if [[ -z "$NODE_ID" ]]; then
    echo "Error: Please specify node ID (1 or 2)."
    echo "Usage: sudo $0 [1|2]"
    exit 1
fi

# 1. Identify the correct 'enp1' interface that is 'Up'
# This grep logic excludes 'enP2p' and grabs the interface name from the 4th column
INTERFACE=$(ibdev2netdev | grep "enp1" | grep "(Up)" | awk '{print $4}')

if [[ -z "$INTERFACE" ]]; then
    echo "Error: No active 'enp1' interface found in 'Up' state."
    exit 1
fi

echo "Found active interface: $INTERFACE"

# 2. Assign IP based on Node ID
if [ "$NODE_ID" == "1" ]; then
    IP="192.168.100.10/24"
elif [ "$NODE_ID" == "2" ]; then
    IP="192.168.100.11/24"
else
    echo "Invalid Node ID. Use 1 or 2."
    exit 1
fi

# 3. Apply Configuration
echo "Configuring $INTERFACE with IP $IP..."

# Flush existing IPs to prevent "multiple IP" conflicts on the same subnet
sudo ip addr flush dev "$INTERFACE"
sudo ip addr add "$IP" dev "$INTERFACE"
sudo ip link set "$INTERFACE" up

echo "--- Verification ---"
ip addr show "$INTERFACE"
