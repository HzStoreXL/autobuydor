#!/bin/bash
cd "$(dirname "$0")"
PID_FILE="autobuy.pid"
LOG_FILE="autobuy.log"

_is_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

_start() {
    if _is_running; then
        echo "  ⚠️  Sudah jalan (PID $(cat $PID_FILE))"
        return
    fi
    termux-wake-lock 2>/dev/null
    nohup python main.py --background >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 1
    if _is_running; then
        echo "  ✅ Background mode jalan (PID $(cat $PID_FILE))"
    else
        echo "  ❌ Gagal start. Cek log."
        termux-wake-unlock 2>/dev/null
    fi
}

_stop() {
    if _is_running; then
        kill "$(cat "$PID_FILE")"
        rm -f "$PID_FILE"
        termux-wake-unlock 2>/dev/null
        echo "  🛑 Dihentikan."
    else
        echo "  ⚠️  Tidak sedang jalan."
        rm -f "$PID_FILE" 2>/dev/null
    fi
}

while true; do
    clear
    echo "================================"
    echo "   🤖 CLI AUTOBUY — BACKGROUND"
    echo "================================"
    if _is_running; then
        echo "  Status : 🟢 JALAN (PID $(cat $PID_FILE))"
    else
        echo "  Status : 🔴 MATI"
    fi
    echo "================================"
    echo "  1. ▶️  Start"
    echo "  2. ⏹️  Stop"
    echo "  0. ↩️  Kembali ke menu utama"
    echo "================================"
    read -p "  Pilihan: " c
    case "$c" in
        1) _start; read -p "  [Enter] lanjut..." ;;
        2) _stop;  read -p "  [Enter] lanjut..." ;;
        0) break ;;
        *) ;;
    esac
done
