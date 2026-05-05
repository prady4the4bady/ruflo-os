#!/bin/bash
# Build Ruflo OS Bootable ISO
set -e

echo "=== Building Ruflo OS ISO ==="

# 1. Install prerequisites
apt-get update && apt-get install -y \
    live-build \
    xorriso \
    grub-pc \
    squashfs-tools

# 2. Create live-build config
lb config \
    --distribution bookworm \
    --architecture amd64 \
    --binary-images iso-hybrid \
    --bootloader grub-pc \
    --package-lists none \
    --linux-flavours ruflo \
    --linux-packages linux-image-ruflo

# 3. Copy package lists
mkdir -p config/package-lists
cat > config/package-lists/ruflo.list.chroot <<EOF
linux-image-ruflo
ruflo-nemoclaw
ruflo-agent
ruflo-shell
ruflo-api
ollama
python3
xwayland
wlroots
EOF

# 4. Copy preseed.cfg
cp installer/iso-builder/preseed.cfg config/

# 5. Build ISO
lb build

# 6. Move ISO to output
mkdir -p /output
mv live-image-amd64.hybrid.iso /output/ruflo-os-$(date +%Y%m%d).iso

echo "=== ISO Build Complete: /output/ruflo-os-*.iso ==="