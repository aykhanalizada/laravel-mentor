#!/bin/bash
cd /home/ayxan/Documents/Projects/laravel-mentor
source .env
export TELEGRAM_BOT_TOKEN
export TELEGRAM_CHAT_ID
exec python3 -u bot_listener.py >> /home/ayxan/Documents/Projects/laravel-mentor/bot.log 2>&1
