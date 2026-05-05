# Shell

macOS-inspired KDE Plasma 6 desktop shell for Ruflo OS.

## Structure

```
shell/
├── plasma-theme/    # Global Plasma look-and-feel theme
├── dock/            # macOS-style dock panel configuration
├── launcher/        # Spotlight-style KRunner plugin (QML/C++)
├── top-bar/         # Top bar widgets (clock, system tray, AI status)
├── ai-activity/     # AI Activity Center panel
├── overview/        # Mission Control workspace overview
├── branding/        # Icons, wallpapers, cursors, fonts
└── install.sh       # Theme installation script
```

## Design Goals

- macOS-like dock with magnification, app launching, and running indicators
- Global top bar with system menu, clock, and AI status
- Spotlight-style launcher with fuzzy search and AI command input
- Mission Control workspace overview with window thumbnails
- AI Activity Center showing current tasks, history, and controls
- Consistent Ruflo OS branding with dark/light theme support
