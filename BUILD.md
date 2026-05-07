# Building Ruflo OS ISO

This guide explains how to build the Ruflo OS ISO image for testing in VMware, VirtualBox, or bare metal.

## CI Build Status

**Note**: The ISO build workflow (`.github/workflows/build-iso.yml`) is currently disabled for GitHub Actions CI due to:
- `live-build` requiring systemd and specific Debian repository access
- 404 errors when downloading package Contents file in CI environment
- Native Debian environment required for reliable builds

To build the ISO, use one of the native build options below.

## Prerequisites

- A Debian or Ubuntu system (or WSL2 on Windows)
- `live-build` installed (`sudo apt install live-build`)
- At least 20GB free disk space
- Internet connection for package downloads

## Option 1: Building on Linux (Native or VM)

1. Clone or copy the `ruflo-os` repository to your Linux machine.

2. Open a terminal and navigate to the `distro/live-build` directory:

   ```bash
   cd ruflo-os/distro/live-build
   ```

3. Run the build script:

   ```bash
   sudo bash build-iso.sh
   ```

   This will:
   - Configure live-build for Debian Bookworm
   - Download and install packages
   - Copy NemOS source code into the image
   - Build the ISO (may take 30-60 minutes)

4. Once complete, the ISO will be at:
   ```
   ruflo-os/ruflo-os-0.1.0-amd64.iso
   ```

## Option 2: Building on Windows using WSL2

1. Install WSL2 with a Debian or Ubuntu distribution:
   - Open PowerShell as Administrator and run:
     ```powershell
     wsl --install -d Debian
     ```
   - Reboot if prompted, then launch Debian from Start menu.

2. Inside the WSL Debian shell, install live-build:
   ```bash
   sudo apt update
   sudo apt install live-build git
   ```

3. Copy the `ruflo-os` folder into your WSL home directory (e.g., using Windows Explorer to `\\wsl$\Debian\home\youruser\`).

4. Run the build script from within WSL:
   ```bash
   cd ruflo-os/distro/live-build
   sudo bash build-iso.sh
   ```

5. After build, the ISO will be in the `ruflo-os` directory inside WSL. Copy it out to Windows:
   ```bash
   cp ruflo-os-0.1.0-amd64.iso /mnt/c/Users/youruser/Desktop/
   ```

## Option 3: Quick Test without Building ISO

If you just want to test the NemOS desktop environment without building an ISO:

1. Install Debian Bookworm (or use an existing Debian VM).
2. Clone the repository:
   ```bash
   git clone https://github.com/yourrepo/ruflo-os.git
   cd ruflo-os
   ```
3. Install dependencies:
   ```bash
   sudo apt install python3 python3-venv pip
   pip install -r requirements.txt
   ```
4. Run the desktop shell:
   ```bash
   cd ruflo-shell
   python main.py
   ```

## Using the ISO in VMware

1. Open VMware Workstation/Player.
2. Create a new Virtual Machine:
   - Select "Installer disc image (iso)" and browse to `ruflo-os-0.1.0-amd64.iso`.
   - Guest OS: Debian 12.x 64-bit.
   - Memory: at least 4GB recommended.
   - Disk: 40GB or more.
   - Network: NAT or Bridged.
3. Start the VM. It will boot into a live session.
4. To install to disk, double-click "Install Ruflo OS" on the desktop (Calamares installer).

## Troubleshooting

- **Build fails with package errors**: Ensure you have an internet connection and the Debian repositories are reachable.
- **Missing branding images**: The build will still succeed but use default themes. To add custom branding, place PNG images in `distro/branding/grub/` and `distro/branding/plymouth/`.
- **WSL build issues**: live-build may not work perfectly under WSL due to systemd requirements. Consider using a native Linux VM.

## Current Status

The build system is functional but minimal. The following components are included:

- ✅ Base system (Debian Bookworm)
- ✅ KDE Plasma 6 desktop
- ✅ NemOS services (model-gateway, control-plane, accessibility)
- ✅ Python venv with dependencies
- ✅ Calamares installer
- ⚠️ Branding images (placeholders created, may need real artwork)
- ⚠️ Custom GRUB/Plymouth themes (basic configuration present)

For any issues, please report at: https://github.com/yourrepo/ruflo-os/issues
