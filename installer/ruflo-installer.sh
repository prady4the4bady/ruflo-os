#!/bin/bash
# Ruflo OS Installer - Full OS installation script
# Runs in live environment to install Ruflo OS to disk

set -e
export DEBIAN_FRONTEND=noninteractive

echo "=== Ruflo OS Installer ==="
echo "Detecting hardware..."

# Detect target disk (largest non-removable block device)
TARGET_DISK=$(lsblk -d -n -o NAME,SIZE,TYPE,RM | awk '$3=="disk" && $4==0 {print $1}' | sort -k2 -h | tail -1)
if [ -z "$TARGET_DISK" ]; then
    echo "Error: No suitable disk found"
    exit 1
fi
TARGET_DISK="/dev/$TARGET_DISK"

echo "Target disk: $TARGET_DISK"

# Verify disk size >= 20GB
DISK_SIZE=$(lsblk -b -d -n -o SIZE $TARGET_DISK)
MIN_SIZE=$((20 * 1024 * 1024 * 1024))
if [ $DISK_SIZE -lt $MIN_SIZE ]; then
    echo "Error: Disk too small. Need at least 20GB"
    exit 1
fi

echo "Step 1: Partitioning disk..."
python3 installer/partitioning.py $TARGET_DISK

echo "Step 2: Formatting partitions..."
mkfs.ext4 ${TARGET_DISK}2
mkswap ${TARGET_DISK}3
mkfs.ext4 ${TARGET_DISK}4

echo "Step 3: Mounting partitions..."
mount ${TARGET_DISK}2 /mnt
mkdir -p /mnt/home
mount ${TARGET_DISK}4 /mnt/home
swapon ${TARGET_DISK}3

echo "Step 4: Debootstrapping Ubuntu 24.04 base..."
debootstrap noble /mnt http://archive.ubuntu.com/ubuntu

echo "Step 5: Configuring base system..."
echo "ruflo-os" > /mnt/etc/hostname
echo "127.0.0.1 ruflo-os" >> /mnt/etc/hosts

# Copy Ruflo OS files
echo "Step 6: Installing Ruflo OS components..."
mkdir -p /mnt/opt/ruflo
cp -r nemoclaw /mnt/opt/ruflo/
cp -r ruflo-agent /mnt/opt/ruflo/
cp -r ruflo-shell /mnt/opt/ruflo/
cp -r hermes-integration /mnt/opt/ruflo/
cp -r api /mnt/opt/ruflo/
cp -r model-hub /mnt/opt/ruflo/
cp pyproject.toml /mnt/opt/ruflo/
cp Makefile /mnt/opt/ruflo/

# Install kernel with Ruflo patches
echo "Step 7: Building and installing kernel..."
cp -r kernel /mnt/opt/ruflo/
chroot /mnt bash -c "cd /opt/ruflo/kernel && make -C modules/ai_bridge && make -C modules/ruflo_input"

# Install systemd services
echo "Step 8: Installing systemd services..."
mkdir -p /mnt/etc/systemd/system/
cp init-system/service-manager/*.service /mnt/etc/systemd/system/
chroot /mnt systemctl enable nemoclaw.service
chroot /mnt systemctl enable ruflo-agent.service
chroot /mnt systemctl enable ruflo-shell.service
chroot /mnt systemctl enable ruflo-api.service

# Configure GRUB with Ruflo theme
echo "Step 9: Installing bootloader..."
chroot /mnt bash -c "apt-get update && apt-get install -y grub-pc grub-themes-ruflo"
chroot /mnt grub-install $TARGET_DISK
chroot /mnt update-grub

# Create default user
echo "Step 10: Creating default user..."
chroot /mnt bash -c "useradd -m -s /bin/bash -G sudo,docker ruflo"
chroot /mnt bash -c "echo 'ruflo:ruflo' | chpasswd"

# Create /opt/ruflo directory structure
chroot /mnt bash -c "mkdir -p /opt/ruflo/models /var/ruflo/memory /var/ruflo/audit /run"

echo "Step 11: Building Ruflo Shell compositor..."
chroot /mnt bash -c "cd /opt/ruflo/ruflo-shell/compositor && meson setup build && ninja -C build"

echo "=== Installation Complete ==="
echo "Post-install summary:"
echo "  - OS: Ruflo OS 1.0.0-production"
echo "  - Disk: $TARGET_DISK"
echo "  - User: ruflo (password: ruflo)"
echo "  - Desktop: Ruflo Shell (macOS-inspired)"
echo ""
echo "Please reboot to start Ruflo OS"
