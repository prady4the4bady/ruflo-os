// SPDX-License-Identifier: GPL-2.0
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/mount.h>
#include <sys/stat.h>

int main(int argc, char **argv) {
    // Ruflo OS Init (PID 1)
    printf("Ruflo OS Init starting...\n");

    // Mount essential filesystems
    mount("proc", "/proc", "proc", 0, NULL);
    mount("sysfs", "/sys", "sysfs", 0, NULL);
    mount("devtmpfs", "/dev", "devtmpfs", 0, NULL);
    mkdir("/dev/pts", 0755);
    mount("devpts", "/dev/pts", "devpts", 0, NULL);
    mkdir("/run", 0755);
    mount("tmpfs", "/run", "tmpfs", 0, NULL);

    // Setup cgroups/namespaces
    // ...

    // Start critical services in order:
    // 1. nemoclaw.service
    if (fork() == 0) {
        execl("/usr/bin/systemctl", "systemctl", "start", "nemoclaw.service", NULL);
        exit(1);
    }
    wait(NULL);

    // 2. ruflo-agent.service
    if (fork() == 0) {
        execl("/usr/bin/systemctl", "systemctl", "start", "ruflo-agent.service", NULL);
        exit(1);
    }
    wait(NULL);

    // 3. hermes.service
    if (fork() == 0) {
        execl("/usr/bin/systemctl", "systemctl", "start", "hermes.service", NULL);
        exit(1);
    }
    wait(NULL);

    // 4. ruflo-shell.service
    if (fork() == 0) {
        execl("/usr/bin/systemctl", "systemctl", "start", "ruflo-shell.service", NULL);
        exit(1);
    }
    wait(NULL);

    // 5. ruflo-api.service
    if (fork() == 0) {
        execl("/usr/bin/systemctl", "systemctl", "start", "ruflo-api.service", NULL);
        exit(1);
    }
    wait(NULL);

    printf("Ruflo OS init complete. Entering idle loop.\n");
    while (1) {
        sleep(1000);
    }
    return 0;
}