#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Ruflo OS Shell — KDE Plasma 6 Theme Installer
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLASMA_DIR="${HOME}/.local/share/plasma"
THEME_DIR="${HOME}/.local/share/plasma/look-and-feel/com.ruflo.os"
AURORAE_DIR="${HOME}/.local/share/aurorae/themes/RufloOS"
COLOR_DIR="${HOME}/.local/share/color-schemes"
KVANTUM_DIR="${HOME}/.config/Kvantum/RufloOS"
ICON_DIR="${HOME}/.local/share/icons"
WALL_DIR="${HOME}/.local/share/wallpapers/RufloOS"

echo "╔══════════════════════════════════════════════╗"
echo "║     Ruflo OS Shell — Theme Installer         ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Install Plasma Global Theme ──────────────────────────────
echo "→ Installing Plasma look-and-feel theme..."
mkdir -p "${THEME_DIR}/contents/defaults"
mkdir -p "${THEME_DIR}/contents/layouts"
mkdir -p "${THEME_DIR}/contents/previews"

cp "${SCRIPT_DIR}/plasma-theme/metadata.json" "${THEME_DIR}/"
cp "${SCRIPT_DIR}/plasma-theme/defaults" "${THEME_DIR}/contents/defaults/" 2>/dev/null || true
echo "  ✓ Plasma theme installed"

# ── Install Dock Panel ───────────────────────────────────────
echo "→ Configuring dock panel..."
PANEL_DIR="${HOME}/.config"
if [ -f "${SCRIPT_DIR}/dock/panel-config.js" ]; then
    mkdir -p "${PANEL_DIR}"
    cp "${SCRIPT_DIR}/dock/panel-config.js" "${PANEL_DIR}/ruflo-dock.js"
    echo "  ✓ Dock panel configured"
fi

# ── Install KRunner Plugin ───────────────────────────────────
echo "→ Installing Spotlight launcher plugin..."
KRUNNER_DIR="${HOME}/.local/share/krunner/dbusplugins"
mkdir -p "${KRUNNER_DIR}"
if [ -f "${SCRIPT_DIR}/launcher/ruflo-launcher.desktop" ]; then
    cp "${SCRIPT_DIR}/launcher/ruflo-launcher.desktop" "${KRUNNER_DIR}/"
    echo "  ✓ KRunner plugin installed"
fi

# ── Install Wallpapers ───────────────────────────────────────
echo "→ Installing wallpapers..."
mkdir -p "${WALL_DIR}/contents/images"
if [ -d "${SCRIPT_DIR}/branding/wallpapers" ]; then
    cp -r "${SCRIPT_DIR}/branding/wallpapers/"* "${WALL_DIR}/contents/images/" 2>/dev/null || true
fi
cat > "${WALL_DIR}/metadata.json" << 'EOF'
{
    "KPlugin": {
        "Id": "com.ruflo.os.wallpaper",
        "Name": "Ruflo OS",
        "Description": "Default wallpaper for Ruflo OS"
    }
}
EOF
echo "  ✓ Wallpapers installed"

# ── Apply Plasma Settings ────────────────────────────────────
echo "→ Applying Plasma settings..."
if command -v kwriteconfig6 &>/dev/null; then
    # Window decorations
    kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key theme "Breeze"
    kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key ButtonsOnLeft ""
    kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key ButtonsOnRight "IAX"

    # Desktop effects (macOS-like)
    kwriteconfig6 --file kwinrc --group Plugins --key magiclampEnabled true
    kwriteconfig6 --file kwinrc --group Plugins --key slideEnabled true
    kwriteconfig6 --file kwinrc --group Plugins --key blurEnabled true

    # Overview effect (Mission Control)
    kwriteconfig6 --file kwinrc --group Plugins --key overviewEnabled true
    kwriteconfig6 --file kwinrc --group Effect-overview --key BorderActivate 9

    # Global menu
    kwriteconfig6 --file kwinrc --group Windows --key BorderlessMaximizedWindows true

    echo "  ✓ Plasma settings applied"
else
    echo "  ⚠ kwriteconfig6 not found — settings will need manual application"
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     Installation complete!                   ║"
echo "║     Log out and back in to apply changes.    ║"
echo "╚══════════════════════════════════════════════╝"
