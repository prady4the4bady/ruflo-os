#!/bin/bash
set -e
echo "=== RufloOS Development Environment Setup ==="

# System dependencies
sudo apt-get update && sudo apt-get install -y \
  build-essential git cmake ninja-build python3-pip python3-venv \
  nodejs npm libwlroots-dev libwayland-dev xwayland \
  ydotool xdotool tesseract-ocr libtesseract-dev \
  wmctrl at-spi2-core libatspi2.0-dev \
  llvm clang bpftool libbpf-dev linux-headers-$(uname -r) \
  docker.io docker-compose-plugin \
  cargo rustc

# Python environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Node environment
npm install

# Build kernel modules
cd kernel/modules/ai_bridge && make && cd ../../..
cd kernel/modules/ruflo_input && make && cd ../../..

# Load kernel modules (requires sudo)
sudo insmod kernel/modules/ai_bridge/ai_bridge.ko
sudo insmod kernel/modules/ruflo_input/ruflo_input.ko

# Pull default models (async)
python3 -m model_hub.puller --defaults &

echo "=== Setup Complete. Run ./scripts/run-ruflo.sh to start ==="