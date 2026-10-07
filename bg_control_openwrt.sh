#!/bin/sh
# Background control untuk OpenWrt (B860H v1/v2)
# Tidak pakai termux-wake-lock — pakai nohup + procd watchdog

cd "$(dirname "$0")"
PID_FILE="autobuy.pid"
LOG_FILE="autobuy.log"

_is_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

_start() {
    if _is_running; then
        echo "  ⚠  Sudah jalan (PID $(cat $PID_FILE))"
        return
    fi
    nohup python3 main.py --background >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 1
    if _is_running; then
        echo "  OK Background jalan (PID $(cat $PID_FILE))"
    else
        echo "  ERR Gagal start. Cek log:"
        tail -20 "$LOG_FILE"
    fi
}

_stop() {
    if _is_running; then
        kill "$(cat "$PID_FILE")"
        rm -f "$PID_FILE"
        echo "  STOP Dihentikan."
    else
        echo "  Tidak sedang jalan."
        rm -f "$PID_FILE" 2>/dev/null
    fi
}

_install_autostart() {
    SCRIPT_PATH="$(cd "$(dirname "$0")"; pwd)/bg_control_openwrt.sh"
    # Tambah ke /etc/rc.local supaya jalan saat boot
    if ! grep -q "bg_control_openwrt" /etc/rc.local 2>/dev/null; then
        sed -i "s|exit 0|$SCRIPT_PATH start\nexit 0|" /etc/rc.local
        echo "  OK Ditambahkan ke /etc/rc.local (auto-start saat boot)"
    else
        echo "  Sudah ada di /etc/rc.local"
    fi
}

_remove_autostart() {
    sed -i '/bg_control_openwrt/d' /etc/rc.local
    echo "  OK Dihapus dari /etc/rc.local"
}

while true; do
    clear
    echo "================================"
    echo "  CLI AUTOBUY - BACKGROUND"
    echo "  OpenWrt B860H"
    echo "================================"
    if _is_running; then
        echo "  Status : JALAN (PID $(cat $PID_FILE))"
    else
        echo "  Status : MATI"
    fi
    echo "================================"
    echo "  1. Start"
    echo "  2. Stop"
    echo "  3. Pasang auto-start saat boot"
    echo "  4. Hapus auto-start"
    echo "  0. Keluar"
    echo "================================"
    printf "  Pilihan: "
    read c
    case "$c" in
        1) _start;           printf "  [Enter] lanjut..."; read x ;;
        2) _stop;            printf "  [Enter] lanjut..."; read x ;;
        3) _install_autostart; printf "  [Enter] lanjut..."; read x ;;
        4) _remove_autostart;  printf "  [Enter] lanjut..."; read x ;;
        0) break ;;
    esac
done
