# Ruflo OS Kernel Build
# ─────────────────────────────────────────────────────────────

## Prerequisites

```bash
sudo apt install build-essential bc kmod cpio flex bison libssl-dev \
    libelf-dev dwarves debhelper rsync
```

## Build Steps

```bash
# 1. Clone Debian kernel source
apt source linux-image-$(uname -r)
cd linux-*

# 2. Apply Ruflo OS defconfig overlay
scripts/kconfig/merge_config.sh .config ../ruflo-os/kernel/configs/ruflos-defconfig

# 3. Apply patches
QUILT_PATCHES=../ruflo-os/kernel/patches quilt push -a

# 4. Build
make -j$(nproc) deb-pkg LOCALVERSION=-ruflos

# 5. Install
sudo dpkg -i ../linux-image-*-ruflos*.deb
sudo dpkg -i ../linux-headers-*-ruflos*.deb
```

## Key Features Enabled

| Feature | Config | Purpose |
|---------|--------|---------|
| Landlock | `CONFIG_SECURITY_LANDLOCK=y` | Filesystem sandboxing |
| seccomp-bpf | `CONFIG_SECCOMP_FILTER=y` | Syscall filtering |
| eBPF | `CONFIG_BPF_SYSCALL=y` | Observability probes |
| uinput | `CONFIG_INPUT_UINPUT=y` | ydotool input injection |
| cgroups v2 | `CONFIG_CGROUP_V2=y` | Resource isolation |
| PREEMPT | `CONFIG_PREEMPT=y` | Desktop responsiveness |
| 1000Hz | `CONFIG_HZ_1000=y` | Low-latency desktop |
