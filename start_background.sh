#!/bin/bash
# Jalankan cli-autobuy di background
# Monitor tetap jalan walau Termux ditutup (swipe close)
# 
# CARA PAKAI:
#   chmod +x start_background.sh
#   ./start_background.sh
#
# PANTAU LOG:
#   tail -f ~/cli-autobuy/autobuy.log
#
# STOP:
#   cat ~/cli-autobuy/autobuy.pid | xargs kill

cd "$(dirname "$0")"
PID_FILE="autobuy.pid"

# Cek apakah sudah jalan
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Sudah jalan (PID $OLD_PID)"
        echo "Stop dulu: kill $OLD_PID"
        exit 1
    fi
fi

# Jalankan dengan nohup
nohup python main.py --background > /dev/null 2>&1 &
echo $! > "$PID_FILE"
echo "✅ Jalan di background (PID $(cat $PID_FILE))"
echo "Log: tail -f autobuy.log"
echo "Stop: kill $(cat $PID_FILE)"
