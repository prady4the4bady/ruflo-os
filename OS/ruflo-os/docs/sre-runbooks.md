# NemOS SRE Runbooks#

## Overview#

Site Reliability Engineering runbooks for NemOS production operations.

## Table of Contents#

1. [Agent Failure Recovery](#agent-failure-recovery)
2. [Model Gateway Outage](#model-gateway-outage)
3. [Desktop Shell Crash](#desktop-shell-crash)
4. [Kernel Module Issues](#kernel-module-issues)
5. [Security Incident Response](#security-incident-response)
6. [Performance Degradation](#performance-degradation)
7. [Backup and Restore](#backup-and-restore)

---

## Agent Failure Recovery#

### Symptoms#
- Agent not responding
- Tasks stuck in "running" state
- High error rate in agent logs

### Diagnosis#
```bash#
# Check agent status"
curl http://localhost:8002/v1/agent/status"

# Check agent logs"
journalctl -u nemos-agent -n 50 --no-pager"

# Check resource usage"
ps aux | grep ruflo-agent"
free -h"
df -h /var/ruflo"
```

### Resolution#
```bash#
# 1. Restart agent service"
sudo systemctl restart nemos-agent"

# 2. Clear stuck tasks"
python -c "
from orchestration.agent-runtime.src.runtime import get_agent
agent = get_agent()
# Force complete all stuck tasks"
for task_id in list(agent.active_tasks.keys()):
    agent.active_tasks[task_id].state = 'failed'
""

# 3. Check model health"
curl http://localhost:8001/health"
```

### Escalation#
- If agent fails to restart > 3 times in 1 hour → Page on-call
- If data loss suspected → Stop all services, restore from backup

---

## Model Gateway Outage#

### Symptoms#
- API returns 503 Service Unavailable
- Tasks failing with "Model not found"
- High latency in model responses

### Diagnosis#
```bash#
# Check gateway health"
curl http://localhost:8001/health"
journalctl -u nemos-gateway -n 50 --no-pager"

# Check Ollama"
curl http://localhost:11434/api/version"

# Check vLLM (if using)"
ps aux | grep vllm"
```

### Resolution#
```bash#
# 1. Restart gateway"
sudo systemctl restart nemos-gateway"

# 2. Restart Ollama if needed"
sudo systemctl restart ollama"

# 3. Reload models"
curl -X POST http://localhost:8001/v1/models/phi3-mini/load"
```

### Escalation#
- If cloud models failing → Check API keys, network connectivity
- If local models crashing → Check VRAM, reduce model precision

---

## Desktop Shell Crash#

### Symptoms#
- Desktop frozen or black screen
- Wayland compositor crashed
- Input not responding

### Diagnosis#
```bash#
# Check compositor status"
journalctl -u nemos-shell -n 50 --no-pager"

# Check display server"
ps aux | grep ruflo-compositor"
echo $DISPLAY"
echo $WAYLAND_DISPLAY"
```

### Resolution#
```bash#
# 1. Restart shell"
sudo systemctl restart nemos-shell"

# 2. If Wayland crashed, switch to X11 temporarily"
sudo sed -i 's/ExecStart=.*wayland.*/ExecStart=\/usr\/bin\/startx11/' /etc/systemd/system/nemos-shell.service"
sudo systemctl daemon-reload"
sudo systemctl restart nemos-shell"

# 3. Check GPU drivers"
lspci | grep VGA"
nvidia-smi  # If NVIDIA"
```

### Escalation#
- If hardware failure suspected → Check dmesg for GPU errors
- If persistent → Boot to recovery mode, check logs

---

## Kernel Module Issues#

### Symptoms#
- `/dev/ai_bridge` not found
- Input injection not working
- Kernel panics or oops messages

### Diagnosis#
```bash#
# Check kernel modules"
lsmod | grep -E 'ai_bridge|ruflo_input'"
dmesg | grep -E 'ai_bridge|ruflo_input|ERROR|WARN' | tail -20"
```

### Resolution#
```bash#
# 1. Rebuild modules for current kernel"
cd kernel/modules/ai_bridge"
make clean && make"
sudo insmod ai_bridge.ko"

cd ../ruflo_input"
make clean && make"
sudo insmod ruflo_input.ko"
```

### Escalation#
- If modules fail to load → Check kernel version compatibility
- If panic → Boot previous kernel, report bug

---

## Security Incident Response#

### Symptoms#
- Unauthorized model downloads
- Suspicious network traffic
- Agent performing unexpected actions

### Diagnosis#
```bash#
# Check audit logs"
cat /var/ruflo/audit/audit.log | grep -i 'denied\|violation' | tail -20"

# Check network connections"
ss -tunap | grep -E '11434|8001|8002'"

# Check model registry"
cat /opt/ruflo/models/registry/model_registry.json | grep -i 'suspicious\|unknown'"
```

### Resolution#
```bash#
# 1. Stop all agents"
sudo systemctl stop nemos-agent"
sudo systemctl stop nemos-gateway"

# 2. Revoke suspicious models"
# Edit model_registry.json, set loaded=false"

# 3. Review and reset policies"
sudo nano /opt/ruflo/nemoclaw/security/*.yaml"
```

### Escalation#
- If breach confirmed → Isolate machine, preserve evidence, notify security team
- Follow incident response playbook

---

## Performance Degradation#

### Symptoms#
- Tasks taking > 5x normal time
- High CPU/memory usage
- Screen capture FPS < 1

### Diagnosis#
```bash#
# Check system resources"
top"
iotop"
nvidia-smi  # If GPU"

# Check for memory leaks"
ps aux --sort=-%mem | head -10"
```

### Resolution#
```bash#
# 1. Restart services (memory leak workaround)"
sudo systemctl restart nemos-agent"
sudo systemctl restart nemos-gateway"

# 2. Clear old tasks"
rm -rf /var/ruflo/tasks/*"
rm -rf /var/ruflo/history.json"

# 3. Reduce agent concurrency"
sudo nano /opt/ruflo/ruflo-agent/agent.config.yaml"
# Set max_agents: 2"
```

### Escalation#
- If persistent → Scale up hardware, optimize models, profile code

---

## Backup and Restore#

### Backup Procedure#
```bash#
#!/bin/bash"
# NemOS Backup Script"
set -e"

BACKUP_DIR="/var/backups/nemos-$(date +%Y%m%d)""
mkdir -p $BACKUP_DIR"

echo "Backing up configuration...""
tar -czf $BACKUP_DIR/config.tar.gz \
    /opt/ruflo/nemoclaw/config.yaml \
    /opt/ruflo/ruflo-agent/agent.config.yaml \
    /etc/systemd/system/nemos-*.service"

echo "Backing up model registry...""
tar -czf $BACKUP_DIR/models.tar.gz \
    /opt/ruflo/models/registry/"

echo "Backing up task history...""
tar -czf $BACKUP_DIR/tasks.tar.gz \
    /var/ruflo/"

echo "Backup complete: $BACKUP_DIR""

# Upload to S3 (optional)"
# aws s3 cp $BACKUP_DIR s3://nemos-backups/"
```

### Restore Procedure#
```bash#
#!/bin/bash"
# NemOS Restore Script"
BACKUP_FILE=$1"

if [ -z "$BACKUP_FILE" ]; then"
    echo "Usage: $0 <backup-file.tar.gz>""
    exit 1"
fi"

echo "Restoring from $BACKUP_FILE...""

tar -xzf $BACKUP_FILE -C /"

echo "Restarting services...""
sudo systemctl restart nemos-gateway"
sudo systemctl restart nemos-agent"
sudo systemctl restart nemos-shell"

echo "Restore complete!""
```

---

## Contact Information#

- **Primary On-Call:** +1-555-NEMOS-001
- **Secondary On-Call:** +1-555-NEMOS-002
- **Slack Channel:** #nemos-sre
- **PagerDuty Service:** NemOS Production
- **Escalation Email:** sre-critical@nemos.ai
