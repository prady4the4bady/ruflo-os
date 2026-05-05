# Makefile for Ruflo OS ISO build
# Requires: live-build installed on Debian/Ubuntu

DISTRO_DIR := $(shell pwd)
BUILD_DIR := /tmp/ruflo-os-build
ISO_NAME := ruflo-os-0.1.0-amd64.iso

.PHONY: all clean iso

all: iso

iso:
	@echo "Building Ruflo OS ISO..."
	sudo $(DISTRO_DIR)/live-build/build-iso.sh

clean:
	@echo "Cleaning build artifacts..."
	sudo rm -rf $(BUILD_DIR)
	rm -f ../$(ISO_NAME)

help:
	@echo "Ruflo OS ISO Build"
	@echo ""
	@echo "Targets:"
	@echo "  iso    - Build the ISO (requires Debian/Ubuntu with live-build)"
	@echo "  clean  - Remove build artifacts"
	@echo ""
	@echo "Prerequisites:"
	@echo "  - Debian/Ubuntu system (or WSL2)"
	@echo "  - sudo apt install live-build"
	@echo "  - Internet connection for package downloads"
