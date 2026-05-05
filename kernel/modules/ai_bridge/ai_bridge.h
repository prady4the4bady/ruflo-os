/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _AI_BRIDGE_H
#define _AI_BRIDGE_H

#include <linux/ioctl.h>
#include <linux/netlink.h>
#include <linux/input.h>

#define AI_BRIDGE_DEVICE_NAME "ai_bridge"
#define AI_BRIDGE_MAJOR 0
#define AI_BRIDGE_MINOR 0

#define NETLINK_AI_BRIDGE 31

#define AI_BRIDGE_IOCTL_MAGIC 'a'
#define AI_BRIDGE_IOCTL_INJECT_KEY _IOW(AI_BRIDGE_IOCTL_MAGIC, 1, struct input_event)
#define AI_BRIDGE_IOCTL_INJECT_MOUSE _IOW(AI_BRIDGE_IOCTL_MAGIC, 2, struct input_event)
#define AI_BRIDGE_IOCTL_INJECT_SCROLL _IOW(AI_BRIDGE_IOCTL_MAGIC, 3, struct input_event)
#define AI_BRIDGE_IOCTL_SCREEN_LOCK _IO(AI_BRIDGE_IOCTL_MAGIC, 4)
#define AI_BRIDGE_IOCTL_SCREEN_UNLOCK _IO(AI_BRIDGE_IOCTL_MAGIC, 5)

struct ai_bridge_event {
    __u32 type;
    __u32 code;
    __s32 value;
    __u64 timestamp_ns;
    char device_name[64];
};

struct ai_bridge_netlink_msg {
    __u16 msg_type;
    __u16 payload_len;
    char payload[];
};

enum ai_bridge_msg_type {
    AI_BRIDGE_MSG_KEY_EVENT = 1,
    AI_BRIDGE_MSG_MOUSE_EVENT = 2,
    AI_BRIDGE_MSG_SCREEN_LOCK = 3,
    AI_BRIDGE_MSG_SCREEN_UNLOCK = 4,
};

#ifdef __KERNEL__
struct ai_bridge_dev {
    struct cdev cdev;
    struct device *dev;
    struct netlink_kernel_cfg nl_cfg;
    struct sock *nl_sk;
    bool screen_locked;
    spinlock_t lock;
    struct list_head event_queue;
    wait_queue_head_t readq;
};
#endif

#endif /* _AI_BRIDGE_H */