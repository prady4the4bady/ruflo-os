/* Ruflo OS eBPF Probe — Syscall Monitoring Scaffold
 *
 * This BPF program traces exec() calls from Ruflo sandbox workers.
 * It can be extended for:
 * - File access monitoring
 * - Network connection tracing
 * - Process lifecycle tracking
 * - Suspicious behavior detection
 *
 * Build: clang -O2 -target bpf -c ruflo_exec_probe.c -o ruflo_exec_probe.o
 * Load: bpftool prog load ruflo_exec_probe.o /sys/fs/bpf/ruflo_exec
 *
 * NOTE: This is scaffolding. Full eBPF probes require a Linux build environment.
 */

// #include <linux/bpf.h>
// #include <bpf/bpf_helpers.h>
// #include <bpf/bpf_tracing.h>

/*
 * Map: events ring buffer for userspace consumption
 *
 * struct {
 *     __uint(type, BPF_MAP_TYPE_RINGBUF);
 *     __uint(max_entries, 256 * 1024);
 * } events SEC(".maps");
 *
 * struct exec_event {
 *     __u32 pid;
 *     __u32 uid;
 *     __u64 timestamp;
 *     char comm[64];
 *     char filename[256];
 * };
 *
 * SEC("tracepoint/syscalls/sys_enter_execve")
 * int trace_execve(struct trace_event_raw_sys_enter *ctx)
 * {
 *     struct exec_event *event;
 *     event = bpf_ringbuf_reserve(&events, sizeof(*event), 0);
 *     if (!event)
 *         return 0;
 *
 *     event->pid = bpf_get_current_pid_tgid() >> 32;
 *     event->uid = bpf_get_current_uid_gid() & 0xFFFFFFFF;
 *     event->timestamp = bpf_ktime_get_ns();
 *     bpf_get_current_comm(&event->comm, sizeof(event->comm));
 *
 *     // Read filename from first argument
 *     const char *filename = (const char *)ctx->args[0];
 *     bpf_probe_read_user_str(&event->filename, sizeof(event->filename), filename);
 *
 *     bpf_ringbuf_submit(event, 0);
 *     return 0;
 * }
 *
 * char LICENSE[] SEC("license") = "GPL";
 */
