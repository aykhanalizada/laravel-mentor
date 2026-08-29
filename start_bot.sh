#!/bin/bash
cd "$(dirname "$0")"
source .env
export TELEGRAM_BOT_TOKEN
export TELEGRAM_CHAT_ID
exec python3 -u bot_listener.py >> bot.log 2>&1
