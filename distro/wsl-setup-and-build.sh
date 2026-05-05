#!/bin/bash
# setup-and-build.sh - Sets up WSL and builds Ruflo OS ISO
# Run this script inside WSL Ubuntu

set -e

echo "╔════════════════════════════════════════════╗"
echo "║     Ruflo OS — WSL Build Setup              ║"
echo "╚════════════════════════════════════════════╝"

# Update package lists
echo "→ Updating package lists..."
sudo apt update

# Install prerequisites
echo "→ Installing prerequisites..."
sudo apt install -y live-build git wget curl

# Create working directory
WORK_DIR="$HOME/ruflo-build"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

# Copy ruflo-os from Windows filesystem
# Note: Change this path if your ruflo-os is in a different location
WINDOWS_PATH="/mnt/c/Users/prady/Desktop/Claude/OS/ruflo-os"
echo "→ Copying ruflo-os from Windows filesystem..."
if [ -d "$WINDOWS_PATH" ]; then
    cp -r "$WINDOWS_PATH" ./ruflo-os
    echo "✓ Source copied to $WORK_DIR/ruflo-os"
else
    echo "✗ Source not found at $WINDOWS_PATH"
    echo "  Please update WINDOWS_PATH in this script to the correct location."
    exit 1
fi

# Make build script executable
chmod +x "$WORK_DIR/ruflo-os/distro/live-build/build-iso.sh"

# Run the build
echo ""
echo "╔════════════════════════════════════════════╗"
echo "║     Starting ISO Build...                   ║"
echo "║     (This will take 30-60 minutes)         ║"
echo "╚════════════════════════════════════════════╝"
echo ""

cd "$WORK_DIR/ruflo-os/distro/live-build"
sudo bash build-iso.sh

# Check if ISO was created
if [ -f "$WORK_DIR/ruflo-os/ruflo-os-0.1.0-amd64.iso" ]; then
    echo ""
    echo "╔════════════════════════════════════════════╗"
    echo "║     ✓ ISO Build Complete!                   ║"
    echo "╚════════════════════════════════════════════╝"
    echo ""
    ls -lh "$WORK_DIR/ruflo-os/ruflo-os-0.1.0-amd64.iso"
    echo ""
    echo "→ Copying ISO to Windows Desktop..."
    cp "$WORK_DIR/ruflo-os/ruflo-os-0.1.0-amd64.iso" /mnt/c/Users/prady/Desktop/
    echo "✓ ISO copied to: C:\\Users\\prady\\Desktop\\ruflo-os-0.1.0-amd64.iso"
else
    echo "✗ Build failed. Check the output above for errors."
    exit 1
fi
