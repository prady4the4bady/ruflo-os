# Kernel

Downstream Linux kernel fork for Ruflo OS with custom configs, patches, and build scripts.

## Structure

```
kernel/
├── configs/         # Kernel defconfig files
│   └── ruflos-defconfig
├── patches/         # Quilt-style patch queue
│   └── series       # Patch application order
├── experiments/     # Experimental kernel modules (not for production)
└── BUILD.md         # Kernel build instructions
```

## Scope

The kernel subsystem does NOT attempt to build a new kernel from scratch. It provides:

1. **Custom defconfig** — Desktop-optimized Debian kernel config with Ruflo-specific options enabled (Landlock, eBPF, seccomp-bpf, uinput)
2. **Patch queue** — Organized patches for scheduler tuning, eBPF hooks, and device control
3. **Build documentation** — Instructions for building the downstream kernel from source

## Non-Goals

- Hybrid Linux+XNU kernel
- Custom scheduler implementations (use CachyOS patches as upstream)
- Kernel-space AI inference
