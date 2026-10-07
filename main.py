import time
from dotenv import load_dotenv
load_dotenv()

import sys, time, os
from app.menus.util import clear_screen, pause
from app.service.auth import AuthInstance
from app.service.autobuy import AutoBuyInstance
from app.menus.account import show_account_menu
from app.menus.autobuy import show_autobuy_menu
from app.menus.autorefresh import show_autorefresh_menu
from app.client.engsel import get_balance, get_tiering_info
from datetime import datetime

WIDTH = 58

def _bg_status():
    pid_file = os.path.join(os.path.dirname(__file__), "autobuy.pid")
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return "🟢"
    except Exception:
        return "🔴"

def show_main_menu(profile):
    clear_screen()
    print("=" * WIDTH)
    exp = datetime.fromtimestamp(profile["balance_expired_at"]).strftime("%Y-%m-%d")
    print(f"  {profile['number']}  [{profile['subscription_type']}]")
    print(f"  Pulsa: Rp {profile['balance']}  |  Aktif s/d: {exp}")
    print(f"  {profile['point_info']}")
    print("=" * WIDTH)

    ab = "🟢" if AutoBuyInstance.is_monitor_running() else "🔴"
    ar = "🟢" if AutoBuyInstance.is_refresh_running()  else "🔴"
    bg = _bg_status()
    print(f"  1. Login / Ganti Akun")
    print(f"  2. ⚡ Auto Buy          [{ab}]")
    print(f"  3. 🔄 Auto Refresh Token [{ar}]")
    print(f"  4. 🖥️  Background Mode   [{bg}]")
    print(f"  5. 🎭 Decoy Manager")
    print(f"  0. Keluar")
    print("=" * WIDTH)

def main():
    while True:
        active_user = AuthInstance.get_active_user()

        if active_user is None:
            selected = show_account_menu()
            if selected:
                AuthInstance.set_active_user(selected)
            continue

        # Ambil info profil untuk header
        try:
            balance       = get_balance(AuthInstance.api_key, active_user["tokens"]["id_token"])
            bal_remaining = balance.get("remaining", 0)
            bal_exp       = balance.get("expired_at", 0)

            point_info = "Points: N/A | Tier: N/A"
            if active_user["subscription_type"] == "PREPAID":
                tiering    = get_tiering_info(AuthInstance.api_key, active_user["tokens"])
                point_info = f"Points: {tiering.get('current_point',0)} | Tier: {tiering.get('tier',0)}"

            profile = {
                "number":            active_user["number"],
                "subscription_type": active_user["subscription_type"],
                "balance":           bal_remaining,
                "balance_expired_at": bal_exp,
                "point_info":        point_info,
            }
        except Exception as e:
            print(f"Gagal ambil profil: {e}")
            pause()
            continue

        show_main_menu(profile)
        choice = input("  Pilihan: ").strip()

        if choice == "1":
            selected = show_account_menu()
            if selected:
                AuthInstance.set_active_user(selected)

        elif choice == "2":
            show_autobuy_menu()

        elif choice == "3":
            show_autorefresh_menu()

        elif choice == "4":
            import subprocess
            _base = os.path.dirname(os.path.abspath(__file__))
            # Deteksi platform: OpenWrt atau Termux
            if os.path.exists("/etc/openwrt_release"):
                bg_script = os.path.join(_base, "bg_control_openwrt.sh")
                subprocess.call(["sh", bg_script])
            else:
                bg_script = os.path.join(_base, "bg_control.sh")
                subprocess.call(["bash", bg_script])

        elif choice == "5":
            from app.menus.decoy import _decoy_manager_menu
            _decoy_manager_menu()

        elif choice == "0":
            print("Sampai jumpa!")
            sys.exit(0)

        else:
            print("  Pilihan tidak valid.")
            pause()

if __name__ == "__main__":
    import sys as _sys
    background_mode = "--background" in _sys.argv

    try:
        if background_mode:
            # Mode background: auto-start semua, tidak tampilkan UI
            print("[BG] Background mode dimulai...")
            AutoBuyInstance.start_all()
            print("[BG] Monitor + Token-refresh jalan.")
            print("[BG] Pantau: tail -f autobuy.log")
            # Jaga proses tetap hidup
            import signal
            def _sig(s, f): AutoBuyInstance.stop_all(); _sys.exit(0)
            signal.signal(signal.SIGTERM, _sig)
            signal.signal(signal.SIGINT, _sig)
            while True:
                time.sleep(60)
        else:
            main()
    except KeyboardInterrupt:
        print("\nKeluar.")

