#!/bin/sh
# Setup cli-autobuy di OpenWrt AArch64 (B860H v1/v2)
# Jalankan sebagai root

set -e
cd "$(dirname "$0")"

echo "=== Install Python3 ==="
opkg update
opkg install python3 python3-pip python3-logging python3-urllib3

echo "=== Install pip packages ==="
pip3 install --no-cache-dir -r requirements-openwrt.txt

echo "=== Install pure-Python AES (pengganti pycryptodome) ==="
pip3 install --no-cache-dir pyaes

echo "=== Selesai ==="
python3 -c "import requests, dotenv, pyaes; print('OK semua dependency tersedia')"
