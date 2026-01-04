# Maintainer: Your Name <your.email@example.com>
# Contributor: Howdy Community

pkgname=howdy-optimized-git
pkgver=r$(git rev-list --count HEAD).$(git rev-parse --short HEAD)
pkgrel=1
pkgdesc="Windows Hello style authentication for Linux - Optimized version with daemon and liveness detection"
arch=('x86_64')
url="https://github.com/boltgolt/howdy"
license=('MIT')
depends=(
    'opencv'
    'python'
    'python-numpy'
    'python-pillow'
    'python-dlib'
    'python-face-recognition'
    'pam'
    'libevdev'
    'python-daemon'
    'python-lockfile'
    'python-psutil'
)
makedepends=(
    'git'
    'meson'
    'ninja'
    'cmake'
    'pkgconf'
)
optdepends=(
    'hplip: for some HP webcam support'
    'v4l-utils: for camera configuration'
    'qv4l2: for camera configuration GUI'
)
provides=('howdy')
conflicts=('howdy' 'howdy-beta-git')
backup=('etc/howdy/config.ini')
source=("git+file://$(pwd)")
sha256sums=('SKIP')

pkgver() {
    cd "$srcdir/${pkgname%-git}"
    printf "r%s.%s" "$(git rev-list --count HEAD)" "$(git rev-parse --short HEAD)"
}

build() {
    cd "$srcdir/${pkgname%-git}"
    
    # Setup build directory
    meson setup build \
        --prefix=/usr \
        --sysconfdir=/etc \
        --localstatedir=/var \
        --buildtype=release
    
    # Build the project
    meson compile -C build
}

check() {
    cd "$srcdir/${pkgname%-git}"
    
    # Basic syntax check for Python files
    python -m py_compile howdy/src/*.py
    
    # Check if all required modules are importable
    python -c "
import sys
sys.path.insert(0, 'howdy/src')
try:
    import model_daemon
    import liveness_detection
    import optimized_video_processor
    print('✅ All optimization modules can be imported')
except ImportError as e:
    print(f'❌ Import error: {e}')
    sys.exit(1)
"
}

package() {
    cd "$srcdir/${pkgname%-git}"
    
    # Install using meson
    meson install -C build --destdir="$pkgdir"
    
    # Create additional directories
    install -dm755 "$pkgdir/var/log/howdy"
    install -dm755 "$pkgdir/var/log/howdy/snapshots"
    
    # Install systemd service for daemon
    install -Dm644 /dev/stdin "$pkgdir/usr/lib/systemd/system/howdy-daemon.service" << 'EOF'
[Unit]
Description=Howdy Model Daemon - Optimized face recognition daemon
Documentation=https://github.com/boltgolt/howdy
After=multi-user.target
Wants=multi-user.target

[Service]
Type=forking
User=root
Group=root
ExecStart=/usr/bin/python -m howdy.src.model_daemon --daemon
PIDFile=/tmp/howdy_daemon.pid
Restart=on-failure
RestartSec=5
TimeoutStartSec=30
TimeoutStopSec=10

# Security settings
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/tmp /var/log/howdy /etc/howdy
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
    
    # Install management scripts
    install -Dm755 /dev/stdin "$pkgdir/usr/bin/howdy-daemon-start" << 'EOF'
#!/bin/bash
echo "🚀 Starting Howdy Daemon..."
systemctl start howdy-daemon.service
sleep 2
if systemctl is-active --quiet howdy-daemon.service; then
    echo "✅ Howdy Daemon started successfully"
    python -m howdy.src.model_daemon --status
else
    echo "❌ Failed to start Howdy Daemon"
    journalctl -u howdy-daemon.service --no-pager -n 10
fi
EOF
    
    install -Dm755 /dev/stdin "$pkgdir/usr/bin/howdy-daemon-stop" << 'EOF'
#!/bin/bash
echo "🛑 Stopping Howdy Daemon..."
systemctl stop howdy-daemon.service
echo "✅ Howdy Daemon stopped"
EOF
    
    install -Dm755 /dev/stdin "$pkgdir/usr/bin/howdy-daemon-restart" << 'EOF'
#!/bin/bash
echo "🔄 Restarting Howdy Daemon..."
systemctl restart howdy-daemon.service
sleep 2
if systemctl is-active --quiet howdy-daemon.service; then
    echo "✅ Howdy Daemon restarted successfully"
else
    echo "❌ Failed to restart Howdy Daemon"
fi
EOF
    
    install -Dm755 /dev/stdin "$pkgdir/usr/bin/howdy-daemon-status" << 'EOF'
#!/bin/bash
echo "📊 Howdy Daemon Status:"
echo "======================"
systemctl status howdy-daemon.service --no-pager -l
echo ""
echo "📈 Daemon Statistics:"
python -m howdy.src.model_daemon --status 2>/dev/null || echo "Daemon not responding"
EOF
    
    # Install benchmark script
    install -Dm755 "$srcdir/${pkgname%-git}/performance_benchmark.py" "$pkgdir/usr/bin/howdy-benchmark"
    
    # Install demo script
    install -Dm755 "$srcdir/${pkgname%-git}/demo_improvements.py" "$pkgdir/usr/bin/howdy-demo"
    
    # Install logrotate configuration
    install -Dm644 /dev/stdin "$pkgdir/etc/logrotate.d/howdy" << 'EOF'
/var/log/howdy/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 640 root root
    postrotate
        systemctl reload howdy-daemon.service 2>/dev/null || true
    endscript
}
EOF
    
    # Install documentation
    install -Dm644 "$srcdir/${pkgname%-git}/OPTIMIZATION_README.md" "$pkgdir/usr/share/doc/howdy/OPTIMIZATION_README.md"
    install -Dm644 "$srcdir/${pkgname%-git}/OPTIMIZATION_PLAN.md" "$pkgdir/usr/share/doc/howdy/OPTIMIZATION_PLAN.md"
    install -Dm644 "$srcdir/${pkgname%-git}/SUMMARY.md" "$pkgdir/usr/share/doc/howdy/SUMMARY.md"
    
    # Set correct permissions
    chmod 750 "$pkgdir/var/log/howdy"
    chmod 755 "$pkgdir/usr/bin/howdy-daemon-"*
    chmod 755 "$pkgdir/usr/bin/howdy-benchmark"
    chmod 755 "$pkgdir/usr/bin/howdy-demo"
}

# Post-installation message
post_install() {
    echo ""
    echo "🎉 Howdy Optimized has been installed!"
    echo "======================================"
    echo ""
    echo "📚 Quick Start:"
    echo "  1. Add your face model: sudo howdy add"
    echo "  2. Start the daemon: sudo howdy-daemon-start"
    echo "  3. Enable auto-start: sudo systemctl enable howdy-daemon.service"
    echo "  4. Test authentication: sudo howdy test"
    echo ""
    echo "🚀 New Features:"
    echo "  • Model daemon for faster loading"
    echo "  • Liveness detection for security"
    echo "  • Enhanced logging and monitoring"
    echo "  • Performance optimizations"
    echo ""
    echo "🎮 Management Commands:"
    echo "  • howdy-daemon-start     - Start daemon"
    echo "  • howdy-daemon-stop      - Stop daemon"
    echo "  • howdy-daemon-restart   - Restart daemon"
    echo "  • howdy-daemon-status    - Show status"
    echo "  • howdy-benchmark        - Performance test"
    echo "  • howdy-demo            - Feature demo"
    echo ""
    echo "⚙️  Configuration:"
    echo "  • Main config: /etc/howdy/config.ini"
    echo "  • Logs: /var/log/howdy/"
    echo "  • Documentation: /usr/share/doc/howdy/"
    echo ""
    echo "🔧 To enable optimizations, edit /etc/howdy/config.ini:"
    echo "  [daemon]"
    echo "  enabled = true"
    echo ""
    echo "  [security]"
    echo "  liveness_check = true"
    echo ""
    echo "📖 Full documentation: /usr/share/doc/howdy/OPTIMIZATION_README.md"
    echo ""
}

post_upgrade() {
    post_install
    
    echo "🔄 Restarting services..."
    if systemctl is-active --quiet howdy-daemon.service; then
        systemctl restart howdy-daemon.service
        echo "✅ Howdy daemon restarted"
    fi
}

pre_remove() {
    echo "🛑 Stopping Howdy services..."
    systemctl stop howdy-daemon.service 2>/dev/null || true
    systemctl disable howdy-daemon.service 2>/dev/null || true
}

post_remove() {
    echo ""
    echo "🗑️  Howdy Optimized has been removed"
    echo ""
    echo "📁 Preserved files:"
    echo "  • Configuration: /etc/howdy/"
    echo "  • Logs: /var/log/howdy/"
    echo "  • User models: /etc/howdy/models/"
    echo ""
    echo "To completely remove all data:"
    echo "  sudo rm -rf /etc/howdy /var/log/howdy"
    echo ""
}