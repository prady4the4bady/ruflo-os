#!/usr/bin/env python3
"""
Ruflo Package Manager - Custom CLI for Ruflo OS.
Supports apt, pip, and HuggingFace model packages.
"""
import sys
import json
import os
import subprocess
import argparse
from typing import Dict, List, Optional
import structlog

logger = structlog.get_logger(__name__)

PACKAGE_DB_PATH = "/var/ruflo/pkg-db.json"
LOCK_FILE = "/var/ruflo/pkg.lock"


class PackageManager:
    """Custom package manager for Ruflo OS."""

    def __init__(self):
        self.db = self._load_db()
        self.lock = self._load_lock()

    def _load_db(self) -> Dict:
        if os.path.exists(PACKAGE_DB_PATH):
            try:
                with open(PACKAGE_DB_PATH, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error("Failed to load package DB", error=str(e))
        return {"packages": {}}

    def _save_db(self):
        try:
            os.makedirs(os.path.dirname(PACKAGE_DB_PATH), exist_ok=True)
            with open(PACKAGE_DB_PATH, "w") as f:
                json.dump(self.db, f, indent=2)
        except Exception as e:
            logger.error("Failed to save package DB", error=str(e))

    def _load_lock(self) -> Dict:
        if os.path.exists(LOCK_FILE):
            try:
                with open(LOCK_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_lock(self):
        try:
            os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
            with open(LOCK_FILE, "w") as f:
                json.dump(self.lock, f, indent=2)
        except Exception as e:
            logger.error("Failed to save lock file", error=str(e))

    def install(self, package: str) -> bool:
        """Install a package by name."""
        # Check if it's a model package
        if package.startswith("model:"):
            return self._install_model(package[6:])

        # Check if it's a system package
        if package in self.db.get("packages", {}):
            pkg_info = self.db["packages"][package]
            return self._install_system_package(package, pkg_info)

        logger.error("Package not found", package=package)
        return False

    def _install_model(self, model_spec: str) -> bool:
        """Pull model from HuggingFace."""
        try:
            # Parse model spec: "model:hermes-3-70b"
            import model_hub.puller as puller
            parts = model_spec.split("/")
            if len(parts) == 2:
                repo_id = parts[0] + "/" + parts[1].split(":")[0]
                filename = parts[1].split(":")[1] if ":" in parts[1] else None
                puller.pull_huggingface(repo_id, filename)
                return True
            else:
                logger.error("Invalid model spec", spec=model_spec)
                return False
        except Exception as e:
            logger.error("Model install failed", error=str(e))
            return False

    def _install_system_package(self, name: str, info: Dict) -> bool:
        """Install system package using apt/pip."""
        pkg_type = info.get("type", "system")

        try:
            if pkg_type == "system":
                subprocess.run(
                    ["apt-get", "install", "-y", name],
                    check=True, capture_output=True
                )
            elif pkg_type == "python":
                subprocess.run(
                    ["pip", "install"] + info.get("pip_args", [name]),
                    check=True, capture_output=True
                )

            # Update DB
            if "installed" not in self.db["packages"][name]:
                self.db["packages"][name]["installed"] = True
            self._save_db()

            logger.info("Package installed", package=name)
            return True
        except subprocess.CalledProcessError as e:
            logger.error("Install failed", package=name, error=e.stderr.decode())
            return False
        except Exception as e:
            logger.error("Install error", package=name, error=str(e))
            return False

    def remove(self, package: str) -> bool:
        """Remove a package."""
        if package not in self.db.get("packages", {}):
            logger.error("Package not found", package=package)
            return False

        try:
            pkg_info = self.db["packages"][package]
            pkg_type = pkg_info.get("type", "system")

            if pkg_type == "system":
                subprocess.run(
                    ["apt-get", "remove", "-y", package],
                    check=True, capture_output=True
                )
            elif pkg_type == "python":
                subprocess.run(
                    ["pip", "uninstall", "-y", package],
                    check=True, capture_output=True
                )

            self.db["packages"][package]["installed"] = False
            self._save_db()

            logger.info("Package removed", package=package)
            return True
        except Exception as e:
            logger.error("Remove failed", package=package, error=str(e))
            return False

    def search(self, query: str) -> List[Dict]:
        """Search packages."""
        results = []
        for name, info in self.db.get("packages", {}).items():
            if query.lower() in name.lower() or query.lower() in info.get("description", "").lower():
                results.append({"name": name, **info})
        return results

    def list_packages(self) -> List[Dict]:
        """List all packages."""
        return [{"name": k, **v} for k, v in self.db.get("packages", {}).items()]

    def update(self):
        """Update package lists."""
        try:
            subprocess.run(["apt-get", "update"], check=True)
            logger.info("Package lists updated")
            return True
        except Exception as e:
            logger.error("Update failed", error=str(e))
            return False


def main():
    parser = argparse.ArgumentParser(description="Ruflo Package Manager")
    subparsers = parser.add_subparsers(dest="command")

    # Install
    install_parser = subparsers.add_parser("install", help="Install package")
    install_parser.add_argument("packages", nargs="+", help="Package name(s)")

    # Remove
    remove_parser = subparsers.add_parser("remove", help="Remove package")
    remove_parser.add_argument("package", help="Package name")

    # Update
    subparsers.add_parser("update", help="Update package lists")

    # Search
    search_parser = subparsers.add_parser("search", help="Search packages")
    search_parser.add_argument("query", help="Search query")

    # List
    subparsers.add_parser("list", help="List packages")

    args = parser.parse_args()

    pm = PackageManager()

    if args.command == "install":
        for pkg in args.packages:
            if pm.install(pkg):
                print(f"✓ {pkg} installed")
            else:
                print(f"✗ {pkg} installation failed")
    elif args.command == "remove":
        if pm.remove(args.package):
            print(f"✓ {args.package} removed")
        else:
            print(f"✗ {args.package} removal failed")
    elif args.command == "update":
        if pm.update():
            print("✓ Package lists updated")
    elif args.command == "search":
        results = pm.search(args.query)
        for r in results:
            print(f"{r['name']} - {r.get('description', '')}")
    elif args.command == "list":
        packages = pm.list_packages()
        for p in packages:
            status = "✓" if p.get("installed") else "✗"
            print(f"{status} {p['name']} - {p.get('description', '')}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
