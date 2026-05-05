"""
Partitioning module for Ruflo OS installer.
Uses parted library (subprocess) for disk partitioning.
"""
import subprocess
import sys
import json
from typing import Dict, List, Optional
import structlog

logger = structlog.get_logger(__name__)


def detect_target_disk() -> Optional[str]:
    """
    Auto-detect target disk (largest non-removable block device).
    Returns device name like 'sda' or None.
    """
    try:
        result = subprocess.run(
            ["lsblk", "-d", "-n", "-o", "NAME,SIZE,TYPE,RM"],
            capture_output=True, text=True, check=True
        )
        lines = result.stdout.strip().split("\n")[1:]  # Skip header
        candidates = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 4 and parts[2] == "disk" and parts[3] == "0":
                size = parts[1]
                candidates.append((parts[0], size))

        if not candidates:
            return None

        # Return largest disk
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]
    except Exception as e:
        logger.error("Disk detection failed", error=str(e))
        return None


def create_gpt_table(disk: str) -> bool:
    """Create GPT partition table."""
    try:
        subprocess.run(["parted", "-s", f"/dev/{disk}", "mklabel", "gpt"], check=True)
        logger.info("GPT table created", disk=disk)
        return True
    except Exception as e:
        logger.error("Failed to create GPT table", error=str(e))
        return False


def create_efi_partition(disk: str) -> bool:
    """Create 512MB EFI partition."""
    try:
        subprocess.run(
            ["parted", "-s", f"/dev/{disk}", "mkpart", "EFI", "fat32", "1MiB", "513MiB"],
            check=True
        )
        subprocess.run(
            ["parted", "-s", f"/dev/{disk}", "set", "1", "boot", "on"],
            check=True
        )
        logger.info("EFI partition created", disk=disk)
        return True
    except Exception as e:
        logger.error("EFI partition failed", error=str(e))
        return False


def create_root_partition(disk: str) -> bool:
    """Create 50GB root partition."""
    try:
        subprocess.run(
            ["parted", "-s", f"/dev/{disk}", "mkpart", "root", "ext4", "513MiB", "51713MiB"],
            check=True
        )
        logger.info("Root partition created", disk=disk)
        return True
    except Exception as e:
        logger.error("Root partition failed", error=str(e))
        return False


def create_home_partition(disk: str) -> bool:
    """Create home partition with remaining space."""
    try:
        subprocess.run(
            ["parted", "-s", f"/dev/{disk}", "mkpart", "home", "ext4", "51713MiB", "100%"],
            check=True
        )
        logger.info("Home partition created", disk=disk)
        return True
    except Exception as e:
        logger.error("Home partition failed", error=str(e))
        return False


def validate_disk_size(disk: str, min_gb: int = 20) -> bool:
    """Validate disk size >= min_gb GB."""
    try:
        result = subprocess.run(
            ["lsblk", "-b", "-d", "-n", "-o", "SIZE", f"/dev/{disk}"],
            capture_output=True, text=True, check=True
        )
        size_bytes = int(result.stdout.strip())
        min_bytes = min_gb * 1024 * 1024 * 1024
        if size_bytes < min_bytes:
            logger.error("Disk too small", size_gb=size_bytes/(1024**3), min_gb=min_gb)
            return False
        return True
    except Exception as e:
        logger.error("Disk validation failed", error=str(e))
        return False


def get_partition_map(disk: str) -> List[Dict]:
    """Get partition map as list of dicts."""
    try:
        result = subprocess.run(
            ["lsblk", "-n", "-o", "NAME,SIZE,TYPE", f"/dev/{disk}"],
            capture_output=True, text=True, check=True
        )
        partitions = []
        for line in result.stdout.strip().split("\n")[1:]:
            parts = line.split()
            if len(parts) >= 3 and parts[2] == "part":
                partitions.append({
                    "name": parts[0],
                    "size": parts[1],
                    "type": parts[2]
                })
        return partitions
    except Exception as e:
        logger.error("Failed to get partition map", error=str(e))
        return []


def partition_disk(disk: str) -> Dict[str, Any]:
    """
    Main function to partition disk for Ruflo OS.
    Returns partition map JSON to stdout.
    """
    if not validate_disk_size(disk):
        return {"success": False, "error": "Disk too small (need >= 20GB)"}

    steps = [
        ("Create GPT table", lambda: create_gpt_table(disk)),
        ("Create EFI partition", lambda: create_efi_partition(disk)),
        ("Create root partition", lambda: create_root_partition(disk)),
        ("Create home partition", lambda: create_home_partition(disk)),
    ]

    for name, func in steps:
        if not func():
            return {"success": False, "error": f"Failed: {name}"}

    partition_map = get_partition_map(disk)
    return {
        "success": True,
        "disk": disk,
        "partitions": partition_map
    }


if __name__ == "__main__":
    disk = sys.argv[1] if len(sys.argv) > 1 else detect_target_disk()
    if not disk:
        print(json.dumps({"success": False, "error": "No suitable disk found"}))
        sys.exit(1)

    result = partition_disk(disk)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)
