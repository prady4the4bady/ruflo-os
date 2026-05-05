// SPDX-License-Identifier: GPL-2.0
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/fs.h>
#include <linux/cdev.h>
#include <linux/uaccess.h>
#include <linux/slab.h>
#include <linux/input.h>
#include <linux/uinput.h>
#include <linux/netlink.h>
#include <linux/skbuff.h>
#include <linux/spinlock.h>
#include <linux/wait.h>
#include <linux/list.h>
#include <linux/device.h>
#include <net/net_namespace.h>
#include <linux/input-event-codes.h>
#include "ai_bridge.h"

#define DEVICE_NAME "ai_bridge"
#define CLASS_NAME "ai_bridge"

static int major_number;
static struct class *ai_bridge_class = NULL;
static struct device *ai_bridge_device = NULL;
static struct ai_bridge_dev *ai_bridge_dev = NULL;

struct ai_bridge_event_node {
    struct ai_bridge_event event;
    struct list_head list;
};

static int ai_bridge_open(struct inode *inode, struct file *file)
{
    file->private_data = ai_bridge_dev;
    return 0;
}

static int ai_bridge_release(struct inode *inode, struct file *file)
{
    return 0;
}

static long ai_bridge_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
    struct ai_bridge_dev *dev = file->private_data;
    struct input_event ev;
    int ret = 0;

    switch (cmd) {
    case AI_BRIDGE_IOCTL_INJECT_KEY: {
        if (copy_from_user(&ev, (void __user *)arg, sizeof(ev)))
            return -EFAULT;
        // Inject key event via uinput
        struct input_event kev;
        memset(&kev, 0, sizeof(kev));
        kev.type = EV_KEY;
        kev.code = ev.code;
        kev.value = ev.value;
        // TODO: Send to uinput device
        break;
    }
    case AI_BRIDGE_IOCTL_INJECT_MOUSE: {
        if (copy_from_user(&ev, (void __user *)arg, sizeof(ev)))
            return -EFAULT;
        // Inject mouse event via uinput
        break;
    }
    case AI_BRIDGE_IOCTL_INJECT_SCROLL: {
        if (copy_from_user(&ev, (void __user *)arg, sizeof(ev)))
            return -EFAULT;
        // Inject scroll event
        break;
    }
    case AI_BRIDGE_IOCTL_SCREEN_LOCK:
        spin_lock(&dev->lock);
        dev->screen_locked = true;
        spin_unlock(&dev->lock);
        break;
    case AI_BRIDGE_IOCTL_SCREEN_UNLOCK:
        spin_lock(&dev->lock);
        dev->screen_locked = false;
        spin_unlock(&dev->lock);
        break;
    default:
        return -ENOTTY;
    }
    return ret;
}

static ssize_t ai_bridge_read(struct file *file, char __user *buf, size_t count, loff_t *f_pos)
{
    struct ai_bridge_dev *dev = file->private_data;
    struct ai_bridge_event_node *node;
    ssize_t ret = 0;

    if (wait_event_interruptible(dev->readq, !list_empty(&dev->event_queue)))
        return -ERESTARTSYS;

    spin_lock(&dev->lock);
    if (list_empty(&dev->event_queue)) {
        spin_unlock(&dev->lock);
        return -EAGAIN;
    }
    node = list_first_entry(&dev->event_queue, struct ai_bridge_event_node, list);
    if (count < sizeof(node->event)) {
        spin_unlock(&dev->lock);
        return -EINVAL;
    }
    if (copy_to_user(buf, &node->event, sizeof(node->event))) {
        spin_unlock(&dev->lock);
        return -EFAULT;
    }
    list_del(&node->list);
    spin_unlock(&dev->lock);
    kfree(node);
    return sizeof(node->event);
}

static struct file_operations ai_bridge_fops = {
    .owner = THIS_MODULE,
    .open = ai_bridge_open,
    .release = ai_bridge_release,
    .unlocked_ioctl = ai_bridge_ioctl,
    .read = ai_bridge_read,
};

static void netlink_recv_msg(struct sk_buff *skb)
{
    // Handle netlink messages from userspace
}

static int __init ai_bridge_init(void)
{
    dev_t dev_num;
    int ret;

    ai_bridge_dev = kzalloc(sizeof(struct ai_bridge_dev), GFP_KERNEL);
    if (!ai_bridge_dev)
        return -ENOMEM;

    spin_lock_init(&ai_bridge_dev->lock);
    INIT_LIST_HEAD(&ai_bridge_dev->event_queue);
    init_waitqueue_head(&ai_bridge_dev->readq);
    ai_bridge_dev->screen_locked = false;

    ret = alloc_chrdev_region(&dev_num, 0, 1, DEVICE_NAME);
    if (ret < 0)
        goto err_free;

    major_number = MAJOR(dev_num);
    cdev_init(&ai_bridge_dev->cdev, &ai_bridge_fops);
    ai_bridge_dev->cdev.owner = THIS_MODULE;

    ret = cdev_add(&ai_bridge_dev->cdev, dev_num, 1);
    if (ret < 0)
        goto err_unregister;

    ai_bridge_class = class_create(CLASS_NAME);
    if (IS_ERR(ai_bridge_class)) {
        ret = PTR_ERR(ai_bridge_class);
        goto err_cdev_del;
    }

    ai_bridge_device = device_create(ai_bridge_class, NULL, dev_num, NULL, DEVICE_NAME);
    if (IS_ERR(ai_bridge_device)) {
        ret = PTR_ERR(ai_bridge_device);
        goto err_class_destroy;
    }

    ai_bridge_dev->nl_cfg = (struct netlink_kernel_cfg){
        .input = netlink_recv_msg,
    };
    ai_bridge_dev->nl_sk = netlink_kernel_create(&init_net, NETLINK_AI_BRIDGE, &ai_bridge_dev->nl_cfg);
    if (!ai_bridge_dev->nl_sk) {
        ret = -ENOMEM;
        goto err_device_destroy;
    }

    pr_info("ai_bridge: module loaded, major %d\n", major_number);
    return 0;

err_device_destroy:
    device_destroy(ai_bridge_class, dev_num);
err_class_destroy:
    class_destroy(ai_bridge_class);
err_cdev_del:
    cdev_del(&ai_bridge_dev->cdev);
err_unregister:
    unregister_chrdev_region(dev_num, 1);
err_free:
    kfree(ai_bridge_dev);
    return ret;
}

static void __exit ai_bridge_exit(void)
{
    dev_t dev_num = MKDEV(major_number, 0);

    netlink_kernel_release(ai_bridge_dev->nl_sk);
    device_destroy(ai_bridge_class, dev_num);
    class_destroy(ai_bridge_class);
    cdev_del(&ai_bridge_dev->cdev);
    unregister_chrdev_region(dev_num, 1);
    kfree(ai_bridge_dev);
    pr_info("ai_bridge: module unloaded\n");
}

module_init(ai_bridge_init);
module_exit(ai_bridge_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Pradyun Kumar Sinha");
MODULE_DESCRIPTION("AI Bridge Kernel Module for Ruflo OS");
MODULE_VERSION("1.0.0");