// SPDX-License-Identifier: GPL-2.0
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/input.h>
#include <linux/uinput.h>
#include <linux/device.h>
#include <linux/fs.h>
#include <linux/cdev.h>
#include <linux/spinlock.h>
#include <linux/uaccess.h>
#include "ai_bridge.h"

#define RUFLO_INPUT_NAME "ruflo_input"
#define RUFLO_INPUT_MINOR 1

struct ruflo_input_dev {
    struct cdev cdev;
    struct device *dev;
    struct input_dev *input;
    spinlock_t lock;
    unsigned int rate_limit_us;
    u64 last_inject_time;
};

static struct ruflo_input_dev *ruflo_input = NULL;
static int ruflo_major;
static struct class *ruflo_input_class = NULL;

static int ruflo_input_open(struct inode *inode, struct file *file)
{
    file->private_data = ruflo_input;
    return 0;
}

static int ruflo_input_release(struct inode *inode, struct file *file)
{
    return 0;
}

static ssize_t ruflo_input_write(struct file *file, const char __user *buf, size_t count, loff_t *f_pos)
{
    struct ruflo_input_dev *dev = file->private_data;
    struct input_event ev;
    u64 now;

    if (count < sizeof(ev))
        return -EINVAL;

    if (copy_from_user(&ev, buf, sizeof(ev)))
        return -EFAULT;

    spin_lock(&dev->lock);
    now = ktime_to_ns(ktime_get());
    if (dev->rate_limit_us > 0 && (now - dev->last_inject_time) < dev->rate_limit_us * 1000)
        goto skip;
    dev->last_inject_time = now;

    input_event(dev->input, ev.type, ev.code, ev.value);
    input_sync(dev->input);
    spin_unlock(&dev->lock);
    return sizeof(ev);

skip:
    spin_unlock(&dev->lock);
    return -EBUSY;
}

static struct file_operations ruflo_input_fops = {
    .owner = THIS_MODULE,
    .open = ruflo_input_open,
    .release = ruflo_input_release,
    .write = ruflo_input_write,
};

static int __init ruflo_input_init(void)
{
    dev_t dev_num;
    int ret;

    ruflo_input = kzalloc(sizeof(struct ruflo_input_dev), GFP_KERNEL);
    if (!ruflo_input)
        return -ENOMEM;

    spin_lock_init(&ruflo_input->lock);
    ruflo_input->rate_limit_us = 1000; // 1ms debounce

    ruflo_input->input = input_allocate_device();
    if (!ruflo_input->input) {
        ret = -ENOMEM;
        goto err_free;
    }

    ruflo_input->input->name = RUFLO_INPUT_NAME;
    ruflo_input->input->id.bustype = BUS_VIRTUAL;
    ruflo_input->input->id.vendor = 0x1234;
    ruflo_input->input->id.product = 0x0001;

    set_bit(EV_SYN, ruflo_input->input->evbit);
    set_bit(EV_KEY, ruflo_input->input->evbit);
    set_bit(EV_REL, ruflo_input->input->evbit);
    set_bit(EV_ABS, ruflo_input->input->evbit);

    // Keyboard keys
    for (int i = KEY_ESC; i <= KEY_MENU; i++)
        set_bit(i, ruflo_input->input->keybit);
    // Mouse buttons
    set_bit(BTN_LEFT, ruflo_input->input->keybit);
    set_bit(BTN_RIGHT, ruflo_input->input->keybit);
    set_bit(BTN_MIDDLE, ruflo_input->input->keybit);
    // Mouse axes
    set_bit(REL_X, ruflo_input->input->relbit);
    set_bit(REL_Y, ruflo_input->input->relbit);
    set_bit(REL_WHEEL, ruflo_input->input->relbit);
    // Touchpad axes
    set_bit(ABS_X, ruflo_input->input->absbit);
    set_bit(ABS_Y, ruflo_input->input->absbit);
    input_set_abs_params(ruflo_input->input, ABS_X, 0, 1920, 0, 0);
    input_set_abs_params(ruflo_input->input, ABS_Y, 0, 1080, 0, 0);

    ret = input_register_device(ruflo_input->input);
    if (ret) {
        input_free_device(ruflo_input->input);
        goto err_free;
    }

    ret = alloc_chrdev_region(&dev_num, 0, 1, RUFLO_INPUT_NAME);
    if (ret < 0)
        goto err_input;

    ruflo_major = MAJOR(dev_num);
    cdev_init(&ruflo_input->cdev, &ruflo_input_fops);
    ruflo_input->cdev.owner = THIS_MODULE;

    ret = cdev_add(&ruflo_input->cdev, dev_num, 1);
    if (ret < 0)
        goto err_unregister;

    ruflo_input_class = class_create(THIS_MODULE, RUFLO_INPUT_NAME);
    if (IS_ERR(ruflo_input_class)) {
        ret = PTR_ERR(ruflo_input_class);
        goto err_cdev_del;
    }

    ruflo_input->dev = device_create(ruflo_input_class, NULL, dev_num, NULL, RUFLO_INPUT_NAME);
    if (IS_ERR(ruflo_input->dev)) {
        ret = PTR_ERR(ruflo_input->dev);
        goto err_class_destroy;
    }

    pr_info("ruflo_input: module loaded, major %d\n", ruflo_major);
    return 0;

err_class_destroy:
    class_destroy(ruflo_input_class);
err_cdev_del:
    cdev_del(&ruflo_input->cdev);
err_unregister:
    unregister_chrdev_region(dev_num, 1);
err_input:
    input_unregister_device(ruflo_input->input);
err_free:
    kfree(ruflo_input);
    return ret;
}

static void __exit ruflo_input_exit(void)
{
    dev_t dev_num = MKDEV(ruflo_major, 0);

    device_destroy(ruflo_input_class, dev_num);
    class_destroy(ruflo_input_class);
    cdev_del(&ruflo_input->cdev);
    unregister_chrdev_region(dev_num, 1);
    input_unregister_device(ruflo_input->input);
    kfree(ruflo_input);
    pr_info("ruflo_input: module unloaded\n");
}

module_init(ruflo_input_init);
module_exit(ruflo_input_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Pradyun Kumar Sinha");
MODULE_DESCRIPTION("Ruflo Input Virtual Device Driver for Ruflo OS");
MODULE_VERSION("1.0.0");