#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/MillerJM2/ktradebot.git"
INSTALL_DIR="/opt/arbitrage-bot"
SERVICE_NAME="arbitrage-bot"

echo "=== [1/6] Обновление пакетов и установка зависимостей системы ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq software-properties-common curl ca-certificates git

if ! command -v python3.12 >/dev/null 2>&1; then
    add-apt-repository -y ppa:deadsnakes/ppa || true
    apt-get update -qq
fi
apt-get install -y -qq python3.12 python3.12-venv python3.12-dev

PYTHON_BIN="$(command -v python3.12)"
echo "Будет использован: $PYTHON_BIN ($($PYTHON_BIN --version))"

echo "=== [2/6] Клонирование репозитория в $INSTALL_DIR ==="
if [ -d "$INSTALL_DIR/.git" ]; then
    cd "$INSTALL_DIR"
    git fetch --all
    git reset --hard origin/main
else
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo "=== [3/6] Создание виртуального окружения и установка пакетов Python ==="
if [ -d venv ]; then
    VENV_PY_VERSION="$(./venv/bin/python --version 2>&1 || true)"
    if [[ "$VENV_PY_VERSION" != *"3.12"* ]]; then
        echo "Старое venv ($VENV_PY_VERSION) удаляю — нужно 3.12"
        rm -rf venv
    fi
fi
if [ ! -d venv ]; then
    "$PYTHON_BIN" -m venv venv
fi
./venv/bin/pip install --upgrade pip --quiet
./venv/bin/pip install -r requirements.txt --quiet

echo "=== [4/6] Проверка .env ==="
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  Файл .env создан как копия .env.example."
    echo "⚠️  Нужно отредактировать $INSTALL_DIR/.env и вписать токен и ID."
    echo "⚠️  Команда для редактирования: nano $INSTALL_DIR/.env"
    echo ""
    NEED_ENV_EDIT=1
else
    echo "Файл .env уже существует, не трогаю."
    NEED_ENV_EDIT=0
fi

echo "=== [5/6] Установка systemd-сервиса ==="
cat >/etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=Arbitrage Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}.service >/dev/null 2>&1

echo "=== [6/6] Готово ==="
if [ "$NEED_ENV_EDIT" -eq 1 ]; then
    echo ""
    echo "ДАЛЬШЕ:"
    echo "1) Отредактируй файл:  nano $INSTALL_DIR/.env"
    echo "   (вставь TELEGRAM_BOT_TOKEN и ADMIN_TELEGRAM_ID)"
    echo "2) Запусти бота:        systemctl start $SERVICE_NAME"
    echo "3) Проверь статус:      systemctl status $SERVICE_NAME"
    echo "4) Смотри логи:         journalctl -u $SERVICE_NAME -f"
else
    systemctl restart ${SERVICE_NAME}.service
    sleep 2
    systemctl status ${SERVICE_NAME}.service --no-pager -l
fi
