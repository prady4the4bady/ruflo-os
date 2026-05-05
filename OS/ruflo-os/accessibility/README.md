# Accessibility

4-tier GUI automation layer for Ruflo OS.

## Tiers

| Tier | Method | When Used |
|------|--------|-----------|
| A | AT-SPI2 semantic control | GTK/Qt apps with accessibility support |
| B | ydotool (Wayland) | When AT-SPI unavailable, Wayland session |
| C | xdotool (X11) | X11/XWayland fallback |
| D | Screenshot + VLM | Last resort, when all semantic methods fail |

## Architecture

```
GuiOperator (unified interface)
  ├── ATSPIClient (Tier A)
  ├── YdotoolInjector (Tier B)
  ├── XdotoolInjector (Tier C)
  ├── ScreenCapture
  └── VLMGrounding (Tier D)
```

## Quick Start

```bash
pip install -e ".[dev]"
pytest tests/ -v

# Run as service
uvicorn ruflo_accessibility.api:create_app --factory --port 8200
```
