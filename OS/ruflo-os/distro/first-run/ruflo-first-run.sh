#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Ruflo OS — First Run Setup Wizard
# ─────────────────────────────────────────────────────────────
# Runs once after first login. Configures:
# 1. AI model preferences (local vs cloud)
# 2. API key setup (optional)
# 3. Default model download
# 4. Shell theme application
# 5. Accessibility tier detection
# ─────────────────────────────────────────────────────────────
set -euo pipefail

MARKER_FILE="${HOME}/.config/ruflo/first-run-completed"
CONFIG_DIR="${HOME}/.config/ruflo"

# Skip if already completed
if [ -f "${MARKER_FILE}" ]; then
    exit 0
fi

mkdir -p "${CONFIG_DIR}"

echo "╔══════════════════════════════════════════════╗"
echo "║     Welcome to Ruflo OS!                     ║"
echo "║     Let's set up your AI assistant.           ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Step 1: Model preference ────────────────────────────────
echo "Step 1: AI Model Configuration"
echo "────────────────────────────────"
echo "1) Local only (Ollama — private, no cloud)"
echo "2) Hybrid (local preferred, cloud fallback)"
echo "3) Cloud first (fastest, requires API keys)"
echo ""
read -rp "Choose mode [1/2/3] (default: 2): " MODE
MODE="${MODE:-2}"

case "${MODE}" in
    1) PREFER_LOCAL=true; DEFAULT_PROVIDER=ollama ;;
    3) PREFER_LOCAL=false; DEFAULT_PROVIDER=anthropic ;;
    *) PREFER_LOCAL=true; DEFAULT_PROVIDER=ollama ;;
esac

cat > "${CONFIG_DIR}/preferences.env" << EOF
PREFER_LOCAL=${PREFER_LOCAL}
DEFAULT_PROVIDER=${DEFAULT_PROVIDER}
EOF

# ── Step 2: Ollama setup ─────────────────────────────────────
if command -v ollama &>/dev/null; then
    echo ""
    echo "Step 2: Local Model Setup"
    echo "────────────────────────────────"
    read -rp "Download default model (llama3.2:3b, ~2GB)? [Y/n]: " DL
    DL="${DL:-Y}"
    if [[ "${DL}" =~ ^[Yy] ]]; then
        echo "Downloading... (this may take several minutes)"
        ollama pull llama3.2:3b || echo "⚠ Download failed. You can try later: ollama pull llama3.2:3b"
    fi
fi

# ── Step 3: Shell theme ──────────────────────────────────────
echo ""
echo "Step 3: Applying Ruflo OS Theme"
echo "────────────────────────────────"
if [ -f "/opt/ruflo/shell/install.sh" ]; then
    bash /opt/ruflo/shell/install.sh
fi

# ── Step 4: Accessibility detection ──────────────────────────
echo ""
echo "Step 4: Detecting GUI Automation Capabilities"
echo "────────────────────────────────────────────────"
TIERS=""
if python3 -c "import pyatspi" 2>/dev/null; then
    TIERS="${TIERS} AT-SPI:✓"
else
    TIERS="${TIERS} AT-SPI:✗"
fi
if command -v ydotool &>/dev/null; then
    TIERS="${TIERS} ydotool:✓"
else
    TIERS="${TIERS} ydotool:✗"
fi
if command -v xdotool &>/dev/null; then
    TIERS="${TIERS} xdotool:✓"
else
    TIERS="${TIERS} xdotool:✗"
fi
echo "  Available tiers: ${TIERS}"

# ── Mark complete ────────────────────────────────────────────
touch "${MARKER_FILE}"
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     Setup complete! Ruflo OS is ready.       ║"
echo "╚══════════════════════════════════════════════╝"
