# Makefile for Howdy Optimized
# Удобные команды для сборки, тестирования и управления

.PHONY: help build test clean install uninstall package test-local demo benchmark deps check

# Цвета для вывода
BLUE = \033[0;34m
GREEN = \033[0;32m
YELLOW = \033[1;33m
RED = \033[0;31m
NC = \033[0m # No Color

# Переменные
BUILDDIR = build
TESTDIR = test_env
PKGNAME = howdy-optimized-git

help: ## Показать справку
	@echo "$(BLUE)🚀 Howdy Optimized - Makefile команды$(NC)"
	@echo "=================================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)Примеры использования:$(NC)"
	@echo "  make deps          # Установить зависимости"
	@echo "  make test-local    # Локальное тестирование"
	@echo "  make package       # Собрать Arch пакет"
	@echo "  make demo          # Запустить демонстрацию"

deps: ## Установить зависимости для Arch Linux
	@echo "$(BLUE)📦 Установка зависимостей...$(NC)"
	sudo pacman -S --needed \
		python python-numpy python-opencv python-dlib \
		python-pillow python-daemon python-lockfile python-psutil \
		meson ninja cmake pkgconf git base-devel
	@echo "$(GREEN)✅ Зависимости установлены$(NC)"

check: ## Проверить зависимости и синтаксис
	@echo "$(BLUE)🔍 Проверка зависимостей и синтаксиса...$(NC)"
	@python3 -c "import cv2, numpy, dlib, daemon, lockfile, psutil; print('✅ Python зависимости в порядке')"
	@command -v meson >/dev/null 2>&1 && echo "✅ meson найден" || (echo "❌ meson не найден" && exit 1)
	@command -v ninja >/dev/null 2>&1 && echo "✅ ninja найден" || (echo "❌ ninja не найден" && exit 1)
	@python3 -m py_compile howdy/src/*.py && echo "✅ Синтаксис Python файлов корректен"
	@echo "$(GREEN)✅ Все проверки пройдены$(NC)"

build: ## Собрать проект с meson
	@echo "$(BLUE)🔨 Сборка проекта...$(NC)"
	meson setup $(BUILDDIR) --buildtype=release
	meson compile -C $(BUILDDIR)
	@echo "$(GREEN)✅ Проект собран$(NC)"

test-local: ## Запустить локальное тестирование без установки
	@echo "$(BLUE)🧪 Локальное тестирование...$(NC)"
	@if [ "$$EUID" -ne 0 ]; then \
		echo "$(YELLOW)⚠️  Требуются права root для полного тестирования$(NC)"; \
		echo "Запустите: sudo make test-local"; \
		exit 1; \
	fi
	chmod +x test_local.sh
	./test_local.sh

test: test-local ## Алиас для test-local

package: clean ## Собрать Arch Linux пакет
	@echo "$(BLUE)📦 Сборка Arch пакета...$(NC)"
	@if [ ! -f PKGBUILD ]; then \
		echo "$(RED)❌ PKGBUILD не найден$(NC)"; \
		exit 1; \
	fi
	makepkg -sf
	@echo "$(GREEN)✅ Пакет собран$(NC)"
	@ls -la *.pkg.tar.* 2>/dev/null || echo "$(YELLOW)⚠️  Файлы пакета не найдены$(NC)"

install-package: package ## Собрать и установить пакет
	@echo "$(BLUE)📥 Установка пакета...$(NC)"
	makepkg -si
	@echo "$(GREEN)✅ Пакет установлен$(NC)"

demo: ## Запустить интерактивную демонстрацию
	@echo "$(BLUE)🎭 Запуск демонстрации...$(NC)"
	python3 demo_improvements.py

benchmark: ## Запустить бенчмарк производительности
	@echo "$(BLUE)📊 Запуск бенчмарка...$(NC)"
	@if [ -z "$(USER_NAME)" ]; then \
		echo "$(YELLOW)Использование: make benchmark USER_NAME=username$(NC)"; \
		echo "Или запустите: python3 performance_benchmark.py --user username"; \
	else \
		python3 performance_benchmark.py --user $(USER_NAME); \
	fi

clean: ## Очистить временные файлы
	@echo "$(BLUE)🧹 Очистка...$(NC)"
	rm -rf $(BUILDDIR) $(TESTDIR)
	rm -f *.pkg.tar.*
	rm -f *.log
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "$(GREEN)✅ Очистка завершена$(NC)"

# Команды для разработки
dev-setup: deps ## Настроить среду разработки
	@echo "$(BLUE)🛠️  Настройка среды разработки...$(NC)"
	pip3 install --user pytest black flake8 mypy
	@echo "$(GREEN)✅ Среда разработки настроена$(NC)"

lint: ## Проверить код с помощью flake8
	@echo "$(BLUE)🔍 Проверка кода...$(NC)"
	flake8 howdy/src/*.py --max-line-length=120 --ignore=E501,W503
	@echo "$(GREEN)✅ Проверка кода завершена$(NC)"

format: ## Форматировать код с помощью black
	@echo "$(BLUE)✨ Форматирование кода...$(NC)"
	black howdy/src/*.py --line-length=120
	@echo "$(GREEN)✅ Код отформатирован$(NC)"

# Команды для управления установленной версией
daemon-start: ## Запустить Howdy daemon (требует установки)
	@echo "$(BLUE)🚀 Запуск Howdy daemon...$(NC)"
	sudo howdy-daemon-start

daemon-stop: ## Остановить Howdy daemon
	@echo "$(BLUE)🛑 Остановка Howdy daemon...$(NC)"
	sudo howdy-daemon-stop

daemon-status: ## Показать статус daemon
	@echo "$(BLUE)📊 Статус Howdy daemon...$(NC)"
	sudo howdy-daemon-status

daemon-restart: ## Перезапустить daemon
	@echo "$(BLUE)🔄 Перезапуск Howdy daemon...$(NC)"
	sudo howdy-daemon-restart

# Команды для отладки
debug-build: ## Сборка в режиме отладки
	@echo "$(BLUE)🐛 Отладочная сборка...$(NC)"
	meson setup $(BUILDDIR)_debug --buildtype=debug
	meson compile -C $(BUILDDIR)_debug
	@echo "$(GREEN)✅ Отладочная сборка завершена$(NC)"

debug-test: ## Запуск тестов с отладочной информацией
	@echo "$(BLUE)🐛 Отладочное тестирование...$(NC)"
	DEBUG=1 ./test_local.sh

# Информационные команды
info: ## Показать информацию о системе
	@echo "$(BLUE)ℹ️  Системная информация:$(NC)"
	@echo "OS: $$(uname -a)"
	@echo "Python: $$(python3 --version)"
	@echo "OpenCV: $$(python3 -c 'import cv2; print(cv2.__version__)' 2>/dev/null || echo 'не установлен')"
	@echo "dlib: $$(python3 -c 'import dlib; print(dlib.DLIB_VERSION)' 2>/dev/null || echo 'не установлен')"
	@echo "NumPy: $$(python3 -c 'import numpy; print(numpy.__version__)' 2>/dev/null || echo 'не установлен')"
	@echo "Meson: $$(meson --version 2>/dev/null || echo 'не установлен')"

version: ## Показать версию проекта
	@echo "$(BLUE)📋 Версия Howdy Optimized:$(NC)"
	@git describe --tags --always --dirty 2>/dev/null || echo "unknown"
	@echo "Commit: $$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
	@echo "Branch: $$(git branch --show-current 2>/dev/null || echo 'unknown')"

# Команды для документации
docs: ## Показать ссылки на документацию
	@echo "$(BLUE)📚 Документация:$(NC)"
	@echo "• README: OPTIMIZATION_README.md"
	@echo "• План оптимизации: OPTIMIZATION_PLAN.md"
	@echo "• Сводка: SUMMARY.md"
	@echo ""
	@echo "$(BLUE)🎮 Быстрый старт:$(NC)"
	@echo "1. make deps           # Установить зависимости"
	@echo "2. make check          # Проверить систему"
	@echo "3. make test-local     # Протестировать локально"
	@echo "4. make package        # Собрать пакет"
	@echo "5. make install-package # Установить пакет"

# Команды для CI/CD
ci-test: check test-local ## Полное тестирование для CI
	@echo "$(GREEN)✅ CI тестирование завершено$(NC)"

# Показать справку по умолчанию
all: help