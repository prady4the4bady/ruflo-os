# NemOS Migration Guide#

## Overview#

Migrate from previous OS (Ubuntu, Fedora, etc.) to NemOS.

## Pre-Migration Checklist#

- [ ] Backup all important data"
- [ ] Verify hardware compatibility (check `docs/FEASIBILITY_ASSESSMENT.md`)"
- [ ] Ensure 50GB+ free disk space"
- [ ] Stable internet connection"
- [ ] USB drive (8GB+) for ISO installation"

## Migration Paths#

### From Ubuntu/Debian#

```bash#
# 1. Export package list"
dpkg --get-selections > ~/ubuntu-packages.txt"
apt-mark showauto > ~/ubuntu-auto-packages.txt"

# 2. Export user data"
rsync -avz /home/$USER/ /backup/home/"
sudo rsync -avz /etc/ /backup/etc/"
sudo rsync -avz /var/www/ /backup/var/www  # If running web server"

# 3. Export databases (if any)"
# MySQL"
mysqldump -u root -p --all-databases > ~/mysql-backup.sql"

# PostgreSQL"
pg_dumpall -U postgres > ~/postgres-backup.sql"

# 4. Install NemOS (see install section below)"
```

### From Fedora/RHEL/CentOS#

```bash#
# 1. Export package list"
rpm -qa > ~/fedora-packages.txt"

# 2. Export user data (same as above)"
rsync -avz /home/$USER/ /backup/home/"

# 3. Export services config"
sudo rsync -avz /etc/systemd/system/ /backup/systemd-system/"
sudo rsync -avz /etc/httpd/ /backup/etc/  # Apache"
sudo rsync -avz /etc/nginx/ /backup/etc/  # Nginx"

# 4. Install NemOS"
```

## Installation Methods#

### Method 1: Clean Install (Recommended)#

```bash#
# 1. Download NemOS ISO"
wget https://releases.nemos.ai/v1.0.0/nemos-v1.0.0.iso"

# 2. Create bootable USB"
sudo dd if=nemos-v1.0.0.iso of=/dev/sdX bs=4M status=progress"

# 3. Boot from USB and follow installer"
# The installer will:"
#   - Auto-detect target disk"
#   - Create partitions (EFI + root + home)"
#   - Install base system"
#   - Install NemOS desktop"
#   - Create 'ruflo' user"
```

### Method 2: Dual Boot#

```bash#
# 1. Shrink existing partition"
sudo parted /dev/sda resize 2 50GB  # Shrink to 50GB"

# 2. Boot NemOS ISO and install to free space"
# Installer will detect existing OS and add to GRUB"
```

### Method 3: Virtual Machine#

```bash#
# Using VirtualBox"
VBoxManage createvm --name "NemOS" --ostype "Linux_64""
VBoxManage modifyvm "NemOS" --memory 8192 --cpus 4"
VBoxManage createhd --filename "NemOS.vdi" --size 51200  # 50GB"
VBoxManage storagectl "NemOS" addidecontroller --name "IDE" --controller "PIIX4""
VBoxManage storageattach "NemOS" --storagectl "IDE" --port 0 --device 0 \
    --type hdd --medium "NemOS.vdi""
VBoxManage storageattach "NemOS" --storagectl "IDE" --port 1 --device 0 \
    --type dvddrive --medium "nemos-v1.0.0.iso""

VBoxManage startvm "NemOS"```

## Post-Installation#

### 1. First Boot Setup#

```bash#
# Login as 'ruflo' (password: 'ruflo')"
# The desktop will auto-start with:"
#   - Ruflo Shell (macOS-inspired desktop)"
#   - Dock, MenuBar, Spotlight"
#   - TaskIntake app ready"
```

### 2. Install Previous Packages#

```bash#
# For Ubuntu/Debian packages:"
sudo apt-get install $(cat ~/ubuntu-packages.txt | grep -v deinstall | awk '{print $1}')"

# For Fedora packages (manual check):"
cat ~/fedora-packages.txt | while read pkg; do"
    sudo rpm -ivh $pkg  # Or find equivalent NemOS package"
done"
```

### 3. Restore User Data#

```bash#
# Restore home directory"
rsync -avz /backup/home/$USER/ /home/$USER/"

# Restore configs (carefully!)"
sudo rsync -avz /backup/etc/ /etc/ --dry-run  # Check first!"
# sudo rsync -avz /backup/etc/ /etc/  # Actual restore"

# Restore databases"
mysql -u root -p < ~/mysql-backup.sql"
psql -U postgres < ~/postgres-backup.sql"
```

### 4. Setup AI Models#

```bash#
# Pull default models (requires ~16GB VRAM for Hermes 3 70B Q4)"
curl -X POST http://localhost:8080/api/v1/models/pull \
  -H "Content-Type: application/json" \
  -d '{"source": "huggingface", "identifier": "NousResearch/Hermes-3-Llama-3.1-70B-GGUF"}'"

# Or use smaller default model for less VRAM:"
curl -X POST http://localhost:8080/api/v1/models/pull \
  -H "Content-Type: application/json" \
  -d '{"source": "huggingface", "identifier": "microsoft/Phi-3.5-mini-instruct-gguf"}'"

# Set as default:"
curl -X POST http://localhost:8080/api/v1/models/phi3-mini/default"
```

### 5. Verify Installation#

```bash#
# Check services"
systemctl status nemoclaw"
systemctl status ruflo-agent"
systemctl status ruflo-shell"
systemctl status ruflo-api"

# Check kernel modules"
lsmod | grep -E 'ai_bridge|ruflo_input'"

# Test a simple task"
curl -X POST http://localhost:8080/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{"task": "Open Firefox and search for AI news"}'"

# Monitor task progress"
watch -n 1 'curl -s http://localhost:8080/api/v1/tasks/{task_id} | jq .'"
```

## Common Issues#

### GPU Not Detected#

```bash#
# Check NVIDIA GPU"
lspci | grep -i nvidia"

# Install drivers (if needed)"
sudo apt-get install nvidia-driver-535"

# Verify CUDA"
nvidia-smi"
```

### Model Load Fails#

```bash#
# Check VRAM"
nvidia-smi  # Check memory usage"

# Use smaller model"
curl -X POST http://localhost:8080/api/v1/models/pull \
  -d '{"source": "huggingface", "identifier": "microsoft/Phi-3.5-mini-instruct-gguf"}'"

# Fallback to CPU (slow!)"
# Edit nemoclaw.config.yaml, set 'gpu_auto_detect: false'"
```

### Desktop Not Starting#

```bash#
# Check display"
echo $DISPLAY"
echo $WAYLAND_DISPLAY"

# Check compositor logs"
journalctl -u ruflo-shell -n 50"

# Try X11 fallback"
sudo nano /etc/systemd/system/ruflo-shell.service"
# Change: ExecStart=/usr/bin/startx /usr/bin/ruflo-desktop"
sudo systemctl daemon-reload"
sudo systemctl restart ruflo-shell"
```

## Next Steps#

1. **Complete onboarding** - Walk through first task with TaskIntake"
2. **Setup cloud models** - Configure API keys for OpenAI/NVIDIA"
3. **Install plugins** - Browse and install from plugin marketplace"
4. **Read documentation** - See `docs/` folder"
5. **Join community** - https://discord.gg/nemos"
