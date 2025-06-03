#!/bin/bash
cd "$(dirname "$0")"
PID_FILE="bot.pid"
LOG_FILE="bot.log"
SCRIPT="bot.py"
VENV_PATH="./venv/bin/python"

if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p $OLD_PID > /dev/null 2>&1; then
        kill -9 $OLD_PID
        sleep 1
    fi
    rm "$PID_FILE"
fi

nohup "$VENV_PATH" "$SCRIPT" >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "Bot started with PID $(cat $PID_FILE), logging to $LOG_FILE"
