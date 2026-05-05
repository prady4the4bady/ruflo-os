# Distro

Debian Bookworm-based distribution build system for Ruflo OS.

## Structure

```
distro/
├── live-build/      # Debian live-build configuration
├── packages/        # Package lists (base, desktop, ai-runtime)
├── branding/        # Plymouth splash, GRUB theme, wallpapers
├── calamares/       # Calamares installer configuration
├── systemd/         # Service unit files for Ruflo services
├── apt-channel/     # APT repository and update channel config
├── first-run/       # First-run setup wizard
└── Makefile         # ISO build targets
```

## Building

```bash
# Requires Debian live-build tools
sudo apt install live-build calamares-settings-debian
make iso
```
