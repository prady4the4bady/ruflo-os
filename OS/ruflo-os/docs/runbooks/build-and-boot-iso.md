# Ruflo OS — Build and Boot ISO Runbook

## Prerequisites

- Debian 12 (Bookworm) host system or Docker with Debian
- Root access for live-build
- At least 20GB free disk space
- Internet connection for package downloads

```bash
sudo apt install live-build debootstrap squashfs-tools \
    xorriso grub-efi-amd64-bin mtools
```

## Build ISO

```bash
cd ruflo-os/distro/live-build
chmod +x build-iso.sh
sudo ./build-iso.sh
```

The ISO will be output to `ruflo-os/ruflo-os-0.1.0-amd64.iso`.

## Test in QEMU

```bash
# Quick boot test
qemu-system-x86_64 \
    -enable-kvm \
    -m 4096 \
    -smp 4 \
    -drive file=ruflo-os-0.1.0-amd64.iso,format=raw,media=cdrom \
    -boot d \
    -vga virtio \
    -display sdl

# With EFI
qemu-system-x86_64 \
    -enable-kvm \
    -m 4096 \
    -smp 4 \
    -bios /usr/share/ovmf/OVMF.fd \
    -drive file=ruflo-os-0.1.0-amd64.iso,format=raw,media=cdrom \
    -boot d \
    -vga virtio
```

## Test in VirtualBox

1. Create new VM: Linux / Debian 64-bit
2. RAM: 4096MB, CPUs: 4
3. Enable EFI
4. Mount ISO as optical drive
5. Boot and select "Live (Ruflo OS)"

## Write to USB

```bash
# CAUTION: This will erase the USB drive!
sudo dd if=ruflo-os-0.1.0-amd64.iso of=/dev/sdX bs=4M status=progress
sync
```

## Post-Boot Verification

1. SDDM login screen appears
2. KDE Plasma desktop loads with Ruflo dock
3. `systemctl status ruflo-model-gateway` is active
4. `systemctl status ruflo-control-plane` is active
5. `curl http://localhost:8100/healthz` returns `{"status":"ok"}`
6. `curl http://localhost:9000/healthz` returns `{"status":"ok"}`
