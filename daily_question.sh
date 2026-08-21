#!/bin/bash
# Gündəlik sual skripti - cron tərəfindən çağırılır
set -e

source /home/ayxan/laravel-mentor/.env

export TELEGRAM_BOT_TOKEN
export TELEGRAM_CHAT_ID

cd /home/ayxan/laravel-mentor
python3 mentor.py question >> /home/ayxan/laravel-mentor/mentor.log 2>&1
