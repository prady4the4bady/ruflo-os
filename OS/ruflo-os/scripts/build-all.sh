#!/bin/bash
set -e
echo "=== Building Ruflo OS Full Stack ==="

# Build kernel modules
echo "Building kernel modules..."
cd kernel/modules/ai_bridge && make && cd ../../..
cd kernel/modules/ruflo_input && make && cd ../../..

# Build Ruflo compositor
echo "Building Ruflo Shell compositor..."
cd ruflo-shell/compositor && meson setup build && cd build && ninja && cd ../../../..

# Build Python packages
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Build Docker images
echo "Building Docker images..."
docker compose -f docker/docker-compose.yml build

echo "=== Build Complete ==="