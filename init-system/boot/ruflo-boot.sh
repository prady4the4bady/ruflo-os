#!/bin/bash
# Ruflo OS Boot Sequence Script
set -e

echo "=== Ruflo OS Boot Sequence ==="

# 1. Mount essential filesystems
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts
mount -t devpts devpts /dev/pts
mkdir -p /run
mount -t tmpfs tmpfs /run

# 2. Start kernel modules
modprobe ai_bridge
modprobe ruflo_input
echo "Kernel modules loaded"

# 3. Start nemoclaw.service
echo "Starting Nemoclaw..."
systemctl start nemoclaw.service
sleep 2

# 4. Start ruflo-agent.service
echo "Starting Ruflo Agent..."
systemctl start ruflo-agent.service
sleep 2

# 5. Start hermes.service
echo "Starting Hermes..."
systemctl start hermes.service
sleep 1

# 6. Start ruflo-shell.service
echo "Starting Ruflo Shell..."
systemctl start ruflo-shell.service
sleep 1

# 7. Start ruflo-api.service
echo "Starting Ruflo API..."
systemctl start ruflo-api.service

echo "=== Ruflo OS Boot Complete (target: < 8s on NVMe) ==="
echo "System ready for user tasks"