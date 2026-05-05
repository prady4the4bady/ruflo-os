#!/bin/bash
# ─────────────────────────────────────────────────────
# Ruflo OS — ISO Build Script (Debian live-build)
# ─────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/tmp/ruflo-os-build"
ISO_NAME="ruflo-os-0.1.0-amd64.iso"
SOURCE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"  # ruflo-os root

echo "╔════════════════════════════════════════════╗"
echo "║     Ruflo OS — ISO Builder                   ║"
echo "╚════════════════════════════════════════════╝"

# ── Clean previous build ─────────────────────────────
if [ -d "${BUILD_DIR}" ]; then
    echo "→ Cleaning previous build..."
    sudo rm -rf "${BUILD_DIR}"
fi
mkdir -p "${BUILD_DIR}"
cd "${BUILD_DIR}"

# ── Copy source tree into build dir (for chroot access) ─────
echo "→ Copying Ruflo OS source..."
cp -r "${SOURCE_DIR}" /tmp/ruflo-os 2>/dev/null || echo "Warning: Could not copy source tree"

# ── Configure live-build ─────────────────────────────────────
echo "→ Configuring live-build..."
lb config \
    --distribution bookworm \
    --archive-areas "main contrib non-free non-free-firmware" \
    --architectures amd64 \
    --binary-images iso-hybrid \
    --bootappend-live "boot=live components username=ruflo" \
    --debian-installer live \
    --debian-installer-gui true \
    --iso-application "Ruflo OS" \
    --iso-publisher "Ruflo OS Contributors" \
    --iso-volume "RUFLO_OS" \
    --linux-flavours amd64 \
    --linux-packages "linux-image linux-headers" \
    --mode debian \
    --system live \
    --apt-recommends true \
    --security false

# ── Add security repository (bookworm-security) ────────────
mkdir -p config/archives
echo "deb http://security.debian.org/debian-security bookworm-security main contrib non-free non-free-firmware" > config/archives/security.list.chroot
cp config/archives/security.list.chroot config/archives/security.list.bootstrap

# ── Copy package lists ───────────────────────────────
echo "→ Installing package lists..."
mkdir -p config/package-lists
cp "${SCRIPT_DIR}/../packages/base.list" config/package-lists/base.list.chroot
cp "${SCRIPT_DIR}/../packages/desktop.list" config/package-lists/desktop.list.chroot
cp "${SCRIPT_DIR}/../packages/ai-runtime.list" config/package-lists/ai-runtime.list.chroot

# ── Copy hooks ───────────────────────────────────────
echo "→ Installing build hooks..."
mkdir -p config/hooks/normal

# Hook 1: Base setup
cat > config/hooks/normal/0100-ruflo-setup.hook.chroot << 'HOOK'
#!/bin/bash
set -e
# Create ruflo system user
useradd --system --home-dir /opt/ruflo --shell /usr/sbin/nologin ruflo || true
mkdir -p /opt/ruflo /var/lib/ruflo /etc/ruflo
chown -R ruflo:ruflo /opt/ruflo /var/lib/ruflo

# Create Python venv for services
python3 -m venv /opt/ruflo/venv
HOOK
chmod +x config/hooks/normal/0100-ruflo-setup.hook.chroot

# Hook 2: Install NemOS (if source available)
if [ -f "${SCRIPT_DIR}/hooks/0200-ruflo-install.hook.chroot" ]; then
    cp "${SCRIPT_DIR}/hooks/0200-ruflo-install.hook.chroot" config/hooks/normal/
    chmod +x config/hooks/normal/0200-ruflo-install.hook.chroot
fi

# ── Copy systemd units ──────────────────────────────
echo "→ Installing systemd services..."
mkdir -p config/includes.chroot/etc/systemd/system
cp "${SCRIPT_DIR}/../systemd/"*.service config/includes.chroot/etc/systemd/system/

# ── Copy branding ────────────────────────────────────
echo "→ Installing branding..."
mkdir -p config/includes.chroot/etc/skel/.local/share/wallpapers
# Copy Calamares branding
mkdir -p config/includes.chroot/etc/calamares
cp -r "${SCRIPT_DIR}/../calamares/"* config/includes.chroot/etc/calamares/ 2>/dev/null || true

# ── Build ISO ────────────────────────────────────────
echo "→ Building ISO (this will take a while)..."
sudo lb build 2>&1 | tee build.log

# ── Copy output ──────────────────────────────────────
if [ -f live-image-amd64.hybrid.iso ]; then
    cp live-image-amd64.hybrid.iso "${SCRIPT_DIR}/../${ISO_NAME}"
    echo ""
    echo "╔════════════════════════════════════════════╗"
    echo "║     ✓ ISO built: ${ISO_NAME}     ║"
    echo "╚════════════════════════════════════════════╝"
    ls -lh "${SCRIPT_DIR}/../${ISO_NAME}"
else
    echo "✗ Build failed. Check build.log for details."
    exit 1
fi
