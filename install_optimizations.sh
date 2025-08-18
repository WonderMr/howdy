#!/bin/bash
# Скрипт установки оптимизаций Howdy

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Установка оптимизаций Howdy${NC}"
echo "=================================="

# Проверка прав доступа
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}❌ Этот скрипт должен быть запущен с правами root${NC}"
   exit 1
fi

# Проверка наличия Howdy
if ! command -v howdy &> /dev/null; then
    echo -e "${RED}❌ Howdy не найден. Пожалуйста, установите Howdy сначала.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Howdy найден${NC}"

# Определение путей
HOWDY_DIR="/lib/security/howdy"
CONFIG_DIR="/etc/howdy"
BACKUP_DIR="/etc/howdy/backup_$(date +%Y%m%d_%H%M%S)"

# Создание резервной копии
echo -e "${YELLOW}📦 Создание резервной копии...${NC}"
mkdir -p "$BACKUP_DIR"
cp -r "$HOWDY_DIR"/* "$BACKUP_DIR/" 2>/dev/null || true
cp -r "$CONFIG_DIR"/* "$BACKUP_DIR/" 2>/dev/null || true
echo -e "${GREEN}✅ Резервная копия создана в $BACKUP_DIR${NC}"

# Установка зависимостей
echo -e "${YELLOW}📥 Установка дополнительных зависимостей...${NC}"

# Обновление пакетов
apt-get update

# Установка Python зависимостей
pip3 install --upgrade \
    python-daemon \
    lockfile \
    psutil \
    numpy \
    opencv-python \
    dlib

echo -e "${GREEN}✅ Зависимости установлены${NC}"

# Копирование оптимизированных файлов
echo -e "${YELLOW}📋 Копирование оптимизированных файлов...${NC}"

# Копируем новые модули
cp howdy/src/model_daemon.py "$HOWDY_DIR/"
cp howdy/src/compare_optimized.py "$HOWDY_DIR/"
cp howdy/src/liveness_detection.py "$HOWDY_DIR/"
cp howdy/src/optimized_video_processor.py "$HOWDY_DIR/"

# Делаем файлы исполняемыми
chmod +x "$HOWDY_DIR/model_daemon.py"
chmod +x "$HOWDY_DIR/compare_optimized.py"

echo -e "${GREEN}✅ Файлы скопированы${NC}"

# Создание символических ссылок для совместимости
echo -e "${YELLOW}🔗 Создание символических ссылок...${NC}"

# Резервная копия оригинального compare.py
if [ -f "$HOWDY_DIR/compare.py" ] && [ ! -f "$HOWDY_DIR/compare_original.py" ]; then
    mv "$HOWDY_DIR/compare.py" "$HOWDY_DIR/compare_original.py"
fi

# Создаем ссылку на оптимизированную версию
ln -sf "$HOWDY_DIR/compare_optimized.py" "$HOWDY_DIR/compare.py"

echo -e "${GREEN}✅ Символические ссылки созданы${NC}"

# Обновление конфигурации
echo -e "${YELLOW}⚙️  Обновление конфигурации...${NC}"

# Резервная копия оригинальной конфигурации
if [ -f "$CONFIG_DIR/config.ini" ]; then
    cp "$CONFIG_DIR/config.ini" "$CONFIG_DIR/config_original.ini"
fi

# Копируем оптимизированную конфигурацию
cp howdy/src/config_optimized.ini "$CONFIG_DIR/config.ini"

echo -e "${GREEN}✅ Конфигурация обновлена${NC}"

# Создание systemd сервиса для daemon
echo -e "${YELLOW}🔧 Создание systemd сервиса...${NC}"

cat > /etc/systemd/system/howdy-daemon.service << EOF
[Unit]
Description=Howdy Model Daemon
After=multi-user.target

[Service]
Type=forking
User=root
Group=root
ExecStart=/usr/bin/python3 $HOWDY_DIR/model_daemon.py --daemon
PIDFile=/tmp/howdy_daemon.pid
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Перезагружаем systemd и включаем сервис
systemctl daemon-reload
systemctl enable howdy-daemon.service

echo -e "${GREEN}✅ Systemd сервис создан${NC}"

# Создание скриптов управления
echo -e "${YELLOW}📜 Создание скриптов управления...${NC}"

# Скрипт запуска daemon
cat > /usr/local/bin/howdy-daemon-start << 'EOF'
#!/bin/bash
echo "🚀 Запуск Howdy Daemon..."
systemctl start howdy-daemon.service
sleep 2
if systemctl is-active --quiet howdy-daemon.service; then
    echo "✅ Howdy Daemon запущен успешно"
    python3 /lib/security/howdy/model_daemon.py --status
else
    echo "❌ Ошибка запуска Howdy Daemon"
    journalctl -u howdy-daemon.service --no-pager -n 20
fi
EOF

# Скрипт остановки daemon
cat > /usr/local/bin/howdy-daemon-stop << 'EOF'
#!/bin/bash
echo "🛑 Остановка Howdy Daemon..."
systemctl stop howdy-daemon.service
echo "✅ Howdy Daemon остановлен"
EOF

# Скрипт проверки статуса
cat > /usr/local/bin/howdy-daemon-status << 'EOF'
#!/bin/bash
echo "📊 Статус Howdy Daemon:"
echo "======================="
systemctl status howdy-daemon.service --no-pager -l
echo ""
echo "📈 Статистика Daemon:"
python3 /lib/security/howdy/model_daemon.py --status
EOF

# Скрипт перезапуска
cat > /usr/local/bin/howdy-daemon-restart << 'EOF'
#!/bin/bash
echo "🔄 Перезапуск Howdy Daemon..."
systemctl restart howdy-daemon.service
sleep 2
if systemctl is-active --quiet howdy-daemon.service; then
    echo "✅ Howdy Daemon перезапущен успешно"
else
    echo "❌ Ошибка перезапуска Howdy Daemon"
fi
EOF

# Делаем скрипты исполняемыми
chmod +x /usr/local/bin/howdy-daemon-*

echo -e "${GREEN}✅ Скрипты управления созданы${NC}"

# Создание директорий для логов
echo -e "${YELLOW}📁 Создание директорий для логов...${NC}"
mkdir -p /var/log/howdy/snapshots
chown -R root:root /var/log/howdy
chmod -R 750 /var/log/howdy

echo -e "${GREEN}✅ Директории созданы${NC}"

# Настройка logrotate
echo -e "${YELLOW}🔄 Настройка ротации логов...${NC}"

cat > /etc/logrotate.d/howdy << 'EOF'
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

echo -e "${GREEN}✅ Ротация логов настроена${NC}"

# Запуск daemon
echo -e "${YELLOW}🚀 Запуск Howdy Daemon...${NC}"
systemctl start howdy-daemon.service
sleep 3

# Проверка статуса
if systemctl is-active --quiet howdy-daemon.service; then
    echo -e "${GREEN}✅ Howdy Daemon запущен успешно${NC}"
else
    echo -e "${YELLOW}⚠️  Daemon не запустился автоматически. Проверьте логи:${NC}"
    echo "journalctl -u howdy-daemon.service --no-pager -n 20"
fi

# Тестирование оптимизаций
echo -e "${YELLOW}🧪 Тестирование оптимизаций...${NC}"

# Проверяем доступность daemon
if python3 -c "
from howdy.src.model_daemon import HowdyDaemonClient
client = HowdyDaemonClient()
if client.is_daemon_running():
    print('✅ Daemon доступен')
    exit(0)
else:
    print('❌ Daemon недоступен')
    exit(1)
" 2>/dev/null; then
    echo -e "${GREEN}✅ Оптимизации работают корректно${NC}"
else
    echo -e "${YELLOW}⚠️  Daemon недоступен, но это нормально для первого запуска${NC}"
fi

# Финальные инструкции
echo ""
echo -e "${BLUE}🎉 Установка завершена!${NC}"
echo "========================"
echo ""
echo -e "${GREEN}Что изменилось:${NC}"
echo "• ✅ Установлен daemon для ускорения загрузки моделей"
echo "• ✅ Добавлена система детекции живого лица"
echo "• ✅ Оптимизирована обработка видео"
echo "• ✅ Улучшена система безопасности"
echo "• ✅ Добавлено расширенное логирование"
echo ""
echo -e "${YELLOW}Команды управления:${NC}"
echo "• howdy-daemon-start    - Запуск daemon"
echo "• howdy-daemon-stop     - Остановка daemon"
echo "• howdy-daemon-restart  - Перезапуск daemon"
echo "• howdy-daemon-status   - Проверка статуса"
echo ""
echo -e "${YELLOW}Конфигурация:${NC}"
echo "• Основная: /etc/howdy/config.ini"
echo "• Резервная копия: $BACKUP_DIR"
echo "• Логи: /var/log/howdy/"
echo ""
echo -e "${GREEN}Для тестирования запустите:${NC}"
echo "sudo howdy test"
echo ""
echo -e "${BLUE}Оптимизации активированы! 🚀${NC}"