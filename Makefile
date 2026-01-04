# Makefile for Howdy Optimized
# Convenient commands for building, testing, and managing

.PHONY: help build test clean install uninstall package test-local demo benchmark deps check

# Colors for output
BLUE = \033[0;34m
GREEN = \033[0;32m
YELLOW = \033[1;33m
RED = \033[0;31m
NC = \033[0m # No Color

# Variables
BUILDDIR = build
TESTDIR = test_env
PKGNAME = howdy-optimized-git

help: ## Show help
	@echo "$(BLUE)🚀 Howdy Optimized - Makefile commands$(NC)"
	@echo "=================================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)Usage examples:$(NC)"
	@echo "  make deps          # Install dependencies"
	@echo "  make test-local    # Local testing"
	@echo "  make package       # Build Arch package"

deps: ## Install dependencies for Arch Linux
	@echo "$(BLUE)📦 Installing dependencies...$(NC)"
	sudo pacman -S --needed \
		python python-numpy python-opencv python-dlib \
		python-pillow python-daemon python-lockfile python-psutil \
		meson ninja cmake pkgconf git base-devel
	@echo "$(GREEN)✅ Dependencies installed$(NC)"

check: ## Check dependencies and syntax
	@echo "$(BLUE)🔍 Checking dependencies and syntax...$(NC)"
	@python3 -c "import cv2, numpy, dlib, daemon, lockfile, psutil; print('✅ Python dependencies OK')"
	@command -v meson >/dev/null 2>&1 && echo "✅ meson found" || (echo "❌ meson not found" && exit 1)
	@command -v ninja >/dev/null 2>&1 && echo "✅ ninja found" || (echo "❌ ninja not found" && exit 1)
	@python3 -m py_compile howdy/src/*.py && echo "✅ Python file syntax correct"
	@echo "$(GREEN)✅ All checks passed$(NC)"

build: ## Build project with meson
	@echo "$(BLUE)🔨 Building project...$(NC)"
	meson setup $(BUILDDIR) --buildtype=release
	meson compile -C $(BUILDDIR)
	@echo "$(GREEN)✅ Project built$(NC)"

test-local: ## Run local testing without installation
	@echo "$(BLUE)🧪 Local testing...$(NC)"
	@if [ "$$EUID" -ne 0 ]; then \
		echo "$(YELLOW)⚠️  Root privileges required for full testing$(NC)"; \
		echo "Run: sudo make test-local"; \
		exit 1; \
	fi
	chmod +x test_local.sh
	./test_local.sh

test: test-local ## Alias for test-local

package: clean ## Build Arch Linux package
	@echo "$(BLUE)📦 Building Arch package...$(NC)"
	@if [ ! -f PKGBUILD ]; then \
		echo "$(RED)❌ PKGBUILD not found$(NC)"; \
		exit 1; \
	fi
	makepkg -sf
	@echo "$(GREEN)✅ Package built$(NC)"
	@ls -la *.pkg.tar.* 2>/dev/null || echo "$(YELLOW)⚠️  Package files not found$(NC)"

install-package: package ## Build and install package
	@echo "$(BLUE)📥 Installing package...$(NC)"
	makepkg -si
	@echo "$(GREEN)✅ Package installed$(NC)"

demo: ## Run interactive demonstration
	@echo "$(BLUE)🎭 Starting demo...$(NC)"
	@echo "$(YELLOW)Demo script removed. Use 'howdy test' instead.$(NC)"

benchmark: ## Run performance benchmark
	@echo "$(BLUE)📊 Running benchmark...$(NC)"
	@echo "$(YELLOW)Benchmark script removed. Use 'howdy test' with end_report=true instead.$(NC)"

clean: ## Clean temporary files
	@echo "$(BLUE)🧹 Cleaning...$(NC)"
	rm -rf $(BUILDDIR) $(TESTDIR)
	rm -f *.pkg.tar.*
	rm -f *.log
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "$(GREEN)✅ Cleanup complete$(NC)"

# Development commands
dev-setup: deps ## Setup development environment
	@echo "$(BLUE)🛠️  Setting up development environment...$(NC)"
	pip3 install --user pytest black flake8 mypy
	@echo "$(GREEN)✅ Development environment ready$(NC)"

lint: ## Check code with flake8
	@echo "$(BLUE)🔍 Checking code...$(NC)"
	flake8 howdy/src/*.py --max-line-length=120 --ignore=E501,W503
	@echo "$(GREEN)✅ Code check complete$(NC)"

format: ## Format code with black
	@echo "$(BLUE)✨ Formatting code...$(NC)"
	black howdy/src/*.py --line-length=120
	@echo "$(GREEN)✅ Code formatted$(NC)"

# Commands for managing installed version
daemon-start: ## Start Howdy daemon (requires installation)
	@echo "$(BLUE)🚀 Starting Howdy daemon...$(NC)"
	sudo howdy-daemon-start

daemon-stop: ## Stop Howdy daemon
	@echo "$(BLUE)🛑 Stopping Howdy daemon...$(NC)"
	sudo howdy-daemon-stop

daemon-status: ## Show daemon status
	@echo "$(BLUE)📊 Howdy daemon status:$(NC)"
	sudo howdy-daemon-status

daemon-restart: ## Restart daemon
	@echo "$(BLUE)🔄 Restarting Howdy daemon...$(NC)"
	sudo howdy-daemon-restart

# Debug commands
debug-build: ## Build in debug mode
	@echo "$(BLUE)🐛 Debug build...$(NC)"
	meson setup $(BUILDDIR)_debug --buildtype=debug
	meson compile -C $(BUILDDIR)_debug
	@echo "$(GREEN)✅ Debug build complete$(NC)"

debug-test: ## Run tests with debug information
	@echo "$(BLUE)🐛 Debug testing...$(NC)"
	DEBUG=1 ./test_local.sh

# Information commands
info: ## Show system information
	@echo "$(BLUE)ℹ️  System information:$(NC)"
	@echo "OS: $$(uname -a)"
	@echo "Python: $$(python3 --version)"
	@echo "OpenCV: $$(python3 -c 'import cv2; print(cv2.__version__)' 2>/dev/null || echo 'not installed')"
	@echo "dlib: $$(python3 -c 'import dlib; print(dlib.DLIB_VERSION)' 2>/dev/null || echo 'not installed')"
	@echo "NumPy: $$(python3 -c 'import numpy; print(numpy.__version__)' 2>/dev/null || echo 'not installed')"
	@echo "Meson: $$(meson --version 2>/dev/null || echo 'not installed')"

version: ## Show project version
	@echo "$(BLUE)📋 Howdy Optimized version:$(NC)"
	@git describe --tags --always --dirty 2>/dev/null || echo "unknown"
	@echo "Commit: $$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
	@echo "Branch: $$(git branch --show-current 2>/dev/null || echo 'unknown')"

# Documentation commands
docs: ## Show documentation links
	@echo "$(BLUE)📚 Documentation:$(NC)"
	@echo "• README: README.md"
	@echo "• Security Settings: SECURITY_SETTINGS.md"
	@echo ""
	@echo "$(BLUE)🎮 Quick start:$(NC)"
	@echo "1. make deps           # Install dependencies"
	@echo "2. make check          # Check system"
	@echo "3. make test-local     # Test locally"
	@echo "4. make package        # Build package"
	@echo "5. make install-package # Install package"

# CI/CD commands
ci-test: check test-local ## Full testing for CI
	@echo "$(GREEN)✅ CI testing complete$(NC)"

# Show help by default
all: help
