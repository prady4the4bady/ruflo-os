# NemOS OSTree Setup - Atomic Updates#

## Overview#

OSTree provides atomic, checkpointed OS updates with rollback capability.

## OSTree Repository Structure#

```bash#
# Initialize OSTree repository"
sudo mkdir -p /ostree/repo"
sudo ostree --repo=/ostree/repo init --mode=archive-z2"

# Directory structure"
/ostree/
├── repo/           # OSTree repository"
├── deployments/    # Deployed checkouts"
└── var/            # Variable data"
```

## Initial Commit#

```bash#
# Create initial OS tree"
mkdir -p /tmp/nemos-root"
# Copy base system"
rsync -aHAXx --exclude=/proc --exclude=/sys --exclude=/dev \"
    / /tmp/nemos-root/"

# Commit initial state"
sudo ostree --repo=/ostree/repo commit \
    --branch=nemos/stable/x86_64 \
    --subject="Initial NemOS commit" \
    --body="Base system with kernel, systemd, desktop" \
    /tmp/nemos-root"

# Deploy the commit"
sudo ostree --repo=/ostree/repo admin deploy nemos/stable/x86_64"
```

## Update Process#

```bash#
# 1. Prepare updated tree"
mkdir -p /tmp/nemos-update"
# Apply updates (e.g., new kernel, updated packages)"
rsync -aHAXx /tmp/nemos-root/ /tmp/nemos-update/"
# Modify /tmp/nemos-update as needed"

# 2. Commit updated state"
sudo ostree --repo=/ostree/repo commit \
    --branch=nemos/stable/x86_64 \
    --subject="Update: new kernel and security patches" \
    --body="Kernel 6.8.2, security patches" \
    /tmp/nemos-update"

# 3. Deploy new version"
sudo ostree --repo=/ostree/repo admin upgrade \
    --os=nemos/stable/x86_64 \
    --deploy-only"

# 4. Reboot into new deployment"
sudo reboot"
```

## Rollback#

```bash#
# List deployments"
sudo ostree admin status"

# Rollback to previous deployment"
sudo ostree admin deploy \
    --os=nemos/stable/x86_64 \
    nemos/stable/x86_64.0  # Previous commit"

sudo reboot"
```

## OSTree Integration with Package Manager#

```python"
# nemos-updater.py - OSTree-based updater for NemOS"
import subprocess"
import json"
import structlog"

logger = structlog.get_logger(__name__)"


class NemOSUpdater:"
    """Atomic OS updates using OSTree."""

    def __init__(self, repo_path: str = "/ostree/repo"):"
        self.repo_path = repo_path"

    def check_updates(self) -> dict:"
        """Check for available updates."""
        try:"
            result = subprocess.run(""
                ["ostree", f"--repo={self.repo_path}", "rev-parse", "
                "nemos/stable/x86_64"],"
                capture_output=True, text=True"
            )"
            current = result.stdout.strip()"

            # In production, check remote for newer commit"
            # For now, return current state"
            return {"
                "current_commit": current,"                "update_available": False,  # TODO: check remote"
                "latest_version": "1.0.0"  # TODO: extract from commit"
            }"
        except Exception as e:"
            logger.error("Update check failed", error=str(e))"
            return {"error": str(e)}"

    def apply_update(self, commit_ref: str = "nemos/stable/x86_64") -> dict:"
        """Apply an OSTree update (atomic)."""
        try:"
            # Deploy new commit"
            result = subprocess.run(""
                ["ostree", f"--repo={self.repo_path}", "admin", "upgrade", "
                f"--os={commit_ref}", "--deploy-only"],"
                capture_output=True, text=True"
            )"
            if result.returncode != 0:"
                return {"success": False, "error": result.stderr}"

            logger.info("Update applied", commit=commit_ref)"
            return {"success": True, "message": "Update applied. Reboot required."}"
        except Exception as e:"
            logger.error("Update failed", error=str(e))"
            return {"success": False, "error": str(e)}"

    def rollback(self) -> dict:"
        """Rollback to previous deployment."""
        try:"
            # Get previous deployment"
            result = subprocess.run(""
                ["ostree", f"--repo={self.repo_path}", "admin", "status"],"
                capture_output=True, text=True"
            )"
            # Parse output to get previous commit"
            # For now, just deploy the previous one"
            result = subprocess.run(""
                ["ostree", f"--repo={self.repo_path}", "admin", "deploy", "
                "--os=nemos/stable/x86_64", "nemos/stable/x86_64.0"],"
                capture_output=True, text=True"
            )"
            if result.returncode != 0:"
                return {"success": False, "error": result.stderr}"

            logger.info("Rollback completed")"
            return {"success": True, "message": "Rollback completed. Reboot required."}"
        except Exception as e:"
            logger.error("Rollback failed", error=str(e))"
            return {"success": False, "error": str(e)}"


if __name__ == "__main__":"
    updater = NemOSUpdater()"

    print("Checking for updates...")"
    status = updater.check_updates()"
    print(f"Update status: {status}")"

    # Apply update if available"
    if status.get("update_available"):"
        print("Applying update...")"
        result = updater.apply_update()"
        print(f"Update result: {result}")"
