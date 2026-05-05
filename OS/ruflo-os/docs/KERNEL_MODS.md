# Kernel Modifications for Ruflo OS

## AI Bridge Module (`kernel/modules/ai_bridge/`)

- Creates `/dev/ai_bridge` character device
- Bidirectional IPC between kernel space and Nemoclaw daemon
- Intercepts input events (keyboard, mouse) and forwards to agent
- Netlink socket family `NETLINK_AI_BRIDGE` for low-latency event streaming
- IOCTL commands for injecting input and locking screen

## eBPF Hooks (`kernel/patches/0002-ebpf-ai-hooks.patch`)

- `kprobe on do_sys_openat2`: Monitor file access patterns
- `kprobe on sys_execve`: Track process launches
- `tracepoint on net/net_dev_xmit`: Monitor network activity
- `uprobe on libX11.so/libwayland-client`: Intercept display events
- XDP program for network policy enforcement

## Ruflo Input Driver (`kernel/modules/ruflo_input/`)

- Virtual input device registering as keyboard + mouse via uinput
- Supports absolute/relative mouse positioning
- Full keyboard emulation including modifier keys
- Configurable debounce and injection rate limiting

## Kernel Configuration (`kernel/config/ruflo_defconfig`)

- Custom config with AI Bridge, eBPF, Landlock, seccomp support
- Docker/container support (cgroups, namespaces)
- Wayland/graphics support
- Security features enabled