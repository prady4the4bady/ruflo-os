#!/bin/bash
# Simplified Ruflo OS ISO Build Script
set -euo pipefail

echo "=== Ruflo OS ISO Builder (Simplified) ==="

BUILD_DIR="/tmp/ruflo-os-build"
ISO_NAME="ruflo-os-0.1.0-amd64.iso"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Clean
sudo rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"
cd "${BUILD_DIR}"

# Copy source
cp -r "${SOURCE_DIR}" /tmp/ruflo-os 2>/dev/null || true

# Set mirror environment
export LB_MIRROR_BOOTSTRAP="http://deb.debian.org/debian"
export LB_MIRROR_BINARY="http://deb.debian.org/debian"
export LB_CACHE="none"
export LB_APT_INDICES="none"

# Configure live-build
lb config \
    --distribution bookworm \
    --architectures amd64 \
    --binary-images iso-hybrid \
    --bootappend-live "boot=live components username=ruflo" \
    --debian-installer live \
    --iso-application "Ruflo OS" \
    --iso-volume "RUFLO_OS" \
    --linux-packages "linux-image-amd64" \
    --mode debian \
    --system live \
    --apt-recommends false \
    --security false \
    --apt-indices false

# Copy package lists
mkdir -p config/package-lists
cp "${SOURCE_DIR}/distro/packages/base.list" config/package-lists/base.list.chroot
cp "${SOURCE_DIR}/distro/packages/desktop.list" config/package-lists/desktop.list.chroot
cp "${SOURCE_DIR}/distro/packages/ai-runtime.list" config/package-lists/ai-runtime.list.chroot

# Copy hooks
mkdir -p config/hooks/normal
cat > config/hooks/normal/0100-ruflo-setup.hook.chroot << 'HOOK'
#!/bin/bash
set -e
useradd --system --home-dir /opt/ruflo --shell /usr/sbin/nologin ruflo || true
mkdir -p /opt/ruflo /var/lib/ruflo /etc/ruflo
chown -R ruflo:ruflo /opt/ruflo /var/lib/ruflo
python3 -m venv /opt/ruflo/venv
HOOK
chmod +x config/hooks/normal/0100-ruflo-setup.hook.chroot

# Copy systemd units
mkdir -p config/includes.chroot/etc/systemd/system
cp "${SOURCE_DIR}/distro/systemd/"*.service config/includes.chroot/etc/systemd/system/ 2>/dev/null || true

# Build
echo "→ Building ISO (this may take 30-60 minutes)..."
sudo lb build 2>&1 | tee build.log

# Copy output
if [ -f live-image-amd64.hybrid.iso ]; then
    cp live-image-amd64.hybrid.iso "${SOURCE_DIR}/${ISO_NAME}"
    echo "✓ ISO built: ${ISO_NAME}"
    ls -lh "${SOURCE_DIR}/${ISO_NAME}"
else
    echo "✗ Build failed. Check build.log"
    exit 1
fi
