"""
AutoBuy Service — Mode Threshold Kuota
========================================
Cek kuota setiap interval_minutes menit.
Logika per entry:
  - Paket tidak ditemukan di quota-details → anggap 0 MB → beli
  - Paket ada, sisa <= threshold_mb        → beli
  - Paket ada, sisa > threshold_mb         → skip

Matching kuota (urutan prioritas):
  1. family_code + variant_code (jika tidak kosong)
  2. family_code saja
  3. Keyword dari nama benefit yang disimpan saat browse family
  4. Kata pertama option_name sebagai keyword fallback (paket lama)
  → Jika tidak match sama sekali: anggap 0 MB → beli

autobuy.json per entry:
{
    "number": 628xxxxxxxxx,
    "active": true,
    "threshold_mb": 100,
    "max_buy": 3,
    "interval_minutes": 5,
    "buy_delay_seconds": 16,
    "payment_method": "balance",
    "packages": [
        {
            "family_code":   "...",
            "family_name":   "...",
            "variant_code":  "...",
            "variant_name":  "...",
            "option_name":   "WhatsApp 10GB",
            "order":         4,
            "is_enterprise": false,
            "benefit_names": ["Whatsapp"]
        }
    ]
}
"""

import json, os, time, threading
from typing import List, Dict, Optional
from random import randint

LOG_FILE  = "autobuy.log"
LOG_MAX   = 500   # baris maksimal di log file

def _log(msg: str):
    """Print ke terminal DAN tulis ke log file. Auto-potong jika > LOG_MAX baris."""
    print(msg)
    try:
        lines = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
        lines.append(msg + "\n")
        if len(lines) > LOG_MAX:
            lines = lines[-LOG_MAX:]
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception:
        pass

from app.client.engsel import get_package_details, get_package, send_api_request
from app.client.purchase.balance import settlement_balance
from app.client.purchase.qris import settlement_qris
from app.service.decoy import DecoyInstance
from app.type_dict import PaymentItem

AUTOBUY_FILE = "autobuy.json"
TOKEN_REFRESH_INTERVAL_MIN = 55

PAYMENT_METHODS = {
    "balance":        "Pulsa (langsung)",
    "balance_decoy":  "Pulsa + Decoy V1",
    "balance_decoy2": "Pulsa + Decoy V2",
    "qris":           "QRIS",
    "qris_decoy":     "QRIS + Decoy (+Rp1K)",
    "qris_decoy0":    "QRIS + Decoy (Rp0)",
}


class AutoBuyService:
    _instance_    = None
    _initialized_ = False

    def __new__(cls, *a, **kw):
        if not cls._instance_:
            cls._instance_ = super().__new__(cls)
        return cls._instance_

    def __init__(self):
        if not self._initialized_:
            self.entries: List[Dict] = []
            self._mon_thread: Optional[threading.Thread] = None
            self._ref_thread: Optional[threading.Thread] = None
            self._mon_stop = threading.Event()
            self._ref_stop = threading.Event()
            self._load()
            self._initialized_ = True

    # ── persistence ──────────────────────────────────────────────

    def _load(self):
        if os.path.exists(AUTOBUY_FILE):
            try:
                with open(AUTOBUY_FILE, "r", encoding="utf-8") as f:
                    self.entries = json.load(f)
                self._migrate()
            except Exception as e:
                print(f"[AutoBuy] Gagal load: {e}")
                self.entries = []
        else:
            self.entries = []
            self._save()

    def _migrate(self):
        changed = False
        defs = {
            "active": True,
            "threshold_mb": 100,
            "max_buy": 3,
            "interval_minutes": 5,
            "buy_delay_seconds": 16,
            "payment_method": "balance",
            "packages": [],
            "buy_count_session": 0,
        }
        for e in self.entries:
            if "use_decoy" in e and "payment_method" not in e:
                e["payment_method"] = "balance_decoy" if e.pop("use_decoy") else "balance"
                changed = True
            for k, v in defs.items():
                if k not in e:
                    e[k] = v; changed = True
        if changed:
            self._save()

    def _save(self):
        skip = {"buy_count_session"}
        data = [{k: v for k, v in e.items() if k not in skip} for e in self.entries]
        with open(AUTOBUY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def reload(self):
        prev = {e["number"]: e.get("buy_count_session", 0) for e in self.entries}
        self._load()
        for e in self.entries:
            e["buy_count_session"] = prev.get(e["number"], 0)

    # ── CRUD ─────────────────────────────────────────────────────

    def get_all(self) -> List[Dict]:
        return self.entries.copy()

    def get_by_number(self, number: int) -> Optional[Dict]:
        return next((e for e in self.entries if e["number"] == number), None)

    def add_entry(self, number: int, threshold_mb=100, max_buy=3,
                  interval_minutes=5, buy_delay_seconds=16,
                  payment_method="balance") -> bool:
        if self.get_by_number(number):
            print(f"[AutoBuy] {number} sudah terdaftar.")
            return False
        self.entries.append({
            "number": number,
            "active": True,
            "threshold_mb": threshold_mb,
            "max_buy": max_buy,
            "interval_minutes": interval_minutes,
            "buy_delay_seconds": buy_delay_seconds,
            "payment_method": payment_method if payment_method in PAYMENT_METHODS else "balance",
            "packages": [],
            "buy_count_session": 0,
        })
        self._save()
        return True

    def remove_entry(self, number: int) -> bool:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e["number"] != number]
        if len(self.entries) < before:
            self._save(); return True
        return False

    def update_entry(self, number: int, **kw) -> bool:
        e = self.get_by_number(number)
        if not e: return False
        allowed = {"threshold_mb", "max_buy", "interval_minutes",
                   "buy_delay_seconds", "payment_method", "active"}
        for k, v in kw.items():
            if k in allowed: e[k] = v
        self._save(); return True

    def toggle_active(self, number: int) -> bool:
        e = self.get_by_number(number)
        if not e: return False
        e["active"] = not e["active"]
        self._save()
        print(f"[AutoBuy] {number} → {'AKTIF' if e['active'] else 'NONAKTIF'}")
        return True

    def add_package(self, number: int, pkg: Dict) -> bool:
        e = self.get_by_number(number)
        if not e: return False
        clean = {
            "family_code":   pkg.get("family_code", ""),
            "family_name":   pkg.get("family_name", ""),
            "variant_code":  pkg.get("variant_code", ""),
            "variant_name":  pkg.get("variant_name", ""),
            "option_name":   pkg.get("option_name", ""),
            "order":         pkg.get("order", 1),
            "is_enterprise": pkg.get("is_enterprise", False),
            "benefit_names": pkg.get("benefit_names", []),
        }
        key = (clean["family_code"], clean["variant_code"], clean["order"])
        if any((p["family_code"], p["variant_code"], p["order"]) == key
               for p in e["packages"]):
            print("[AutoBuy] Paket sudah ada."); return False
        e["packages"].append(clean)
        self._save(); return True

    def remove_package(self, number: int, idx: int) -> bool:
        e = self.get_by_number(number)
        if not e: return False
        pkgs = e["packages"]
        if not (0 <= idx < len(pkgs)):
            print("[AutoBuy] Index tidak valid."); return False
        removed = pkgs.pop(idx)
        self._save()
        print(f"[AutoBuy] '{removed.get('option_name','?')}' dihapus.")
        return True

    # ── quota check ───────────────────────────────────────────────

    def get_quota_mb(self, api_key: str, tokens: dict,
                     entry: dict) -> Optional[float]:
        """
        Cek sisa kuota (MB) untuk paket yang terdaftar di entry.

        Return:
          - float  : sisa kuota MB (bisa 0.0 jika tidak ditemukan)
          - None   : gagal request API

        Matching (berurutan, ambil pertama yang cocok):
          L1: family_code + variant_code
          L2: family_code saja
          L3: benefit_names keyword (nama benefit dari browse family)
          L4: kata pertama option_name sebagai keyword (paket lama)
          → Tidak match sama sekali = 0.0 MB (anggap tidak punya paket)
        """
        path    = "api/v8/packages/quota-details"
        payload = {"is_enterprise": False, "lang": "en", "family_member_id": ""}
        try:
            res = send_api_request(api_key, path, payload, tokens["id_token"], "POST")
            if res.get("status") != "SUCCESS":
                return None
            quotas = res["data"]["quotas"]
        except Exception as e:
            print(f"[AutoBuy] Error API quota: {e}")
            return None

        pkgs = entry.get("packages", [])
        if not pkgs:
            # Tidak ada paket terdaftar — anggap 0
            return 0.0

        # Bangun set identifier
        target_pairs    = {(p["family_code"], p["variant_code"])
                           for p in pkgs if p.get("family_code") and p.get("variant_code")}
        target_families = {p["family_code"] for p in pkgs if p.get("family_code")}

        # Keyword: dari benefit_names tersimpan, atau kata pertama option_name
        keywords: set = set()
        for p in pkgs:
            bnames = p.get("benefit_names", [])
            if bnames:
                keywords.update(b.lower().strip() for b in bnames if b)
            else:
                first = p.get("option_name", "").split()
                if first:
                    keywords.add(first[0].lower().strip())

        matched_bytes = 0
        found = False

        for q in quotas:
            fc = q.get("package_family", {}).get("package_family_code", "")
            vc = q.get("package_variants", {}).get("package_variant_code", "")
            quota_name     = q.get("name", "").lower()
            benefit_names  = [b.get("name", "").lower()
                              for b in q.get("benefits", [])]

            hit = False

            # L1
            if fc and vc and (fc, vc) in target_pairs:
                hit = True
            # L2
            elif fc and fc in target_families:
                hit = True
            # L3 / L4 — keyword matching
            elif keywords:
                all_texts = {quota_name} | set(benefit_names)
                if any(kw and txt and (kw in txt or txt in kw)
                       for kw in keywords for txt in all_texts):
                    hit = True

            if hit:
                for b in q.get("benefits", []):
                    if b.get("data_type") == "DATA":
                        matched_bytes += b.get("remaining", 0)
                found = True

        if found:
            return matched_bytes / (1024 ** 2)

        # Tidak ada match → anggap 0 (paket tidak aktif / habis)
        return 0.0

    # ── purchase ─────────────────────────────────────────────────

    def do_purchase(self, api_key: str, tokens: dict,
                    entry: Dict, count: int = 1) -> int:
        pkgs  = entry.get("packages", [])
        if not pkgs:
            print(f"[AutoBuy] [{entry['number']}] Tidak ada paket."); return 0

        method  = entry.get("payment_method", "balance")
        delay   = max(int(entry.get("buy_delay_seconds", 16)), 0)
        success = 0

        for i in range(count):
            if i > 0:
                print(f"[AutoBuy] Jeda {delay}s sebelum beli ke-{i+1}...")
                time.sleep(delay)

            bought = False
            for pi, pkg in enumerate(pkgs):
                if pi > 0:
                    print(f"[AutoBuy] Jeda {delay}s sebelum coba paket berikutnya...")
                    time.sleep(delay)
                try:
                    label = pkg.get("option_name","?")
                    _log(f"[AutoBuy] [{entry['number']}] #{i+1} {label} ...")
                    target = get_package_details(
                        api_key, tokens,
                        pkg["family_code"], pkg["variant_code"],
                        pkg["order"], pkg.get("is_enterprise", False), None
                    )
                    if not target:
                        _log(f"[AutoBuy] Gagal fetch, skip."); continue
                    ok = self._pay(api_key, tokens, method, target)
                    if ok:
                        _log(f"[AutoBuy] ✅ {label} berhasil.")
                        success += 1; bought = True; break
                    _log(f"[AutoBuy] ❌ {label} gagal, coba berikutnya...")
                except Exception as ex:
                    _log(f"[AutoBuy] Exception: {ex}"); continue

            if not bought:
                _log(f"[AutoBuy] [{entry['number']}] Semua paket gagal #{i+1}, stop.")
                break

        return success

    def _pay(self, api_key, tokens, method, target) -> bool:
        opt   = target["package_option"]
        price = opt["price"]
        main  = PaymentItem(
            item_code=opt["package_option_code"], product_type="",
            item_price=price,
            item_name=f"{randint(1000,9999)} {opt['name']}",
            tax=0, token_confirmation=target["token_confirmation"],
        )

        if method == "balance":
            res = settlement_balance(api_key, tokens, [main], "BUY_PACKAGE",
                                     False, overwrite_amount=price,
                                     token_confirmation_idx=0)
            return self._ok(res)

        elif method in ("balance_decoy", "balance_decoy2"):
            decoy = DecoyInstance.get_decoy("balance")
            if not decoy or not decoy.get("option_code"):
                print("[AutoBuy] Decoy tidak ada, fallback pulsa biasa.")
                res = settlement_balance(api_key, tokens, [main], "BUY_PACKAGE",
                                         False, overwrite_amount=price,
                                         token_confirmation_idx=0)
                return self._ok(res)
            dd = get_package(api_key, tokens, decoy["option_code"])
            if not dd: return False
            do = dd["package_option"]
            di = PaymentItem(
                item_code=do["package_option_code"], product_type="",
                item_price=do["price"],
                item_name=f"{randint(1000,9999)} {do['name']}",
                tax=0, token_confirmation=dd["token_confirmation"],
            )
            items = [main, di]
            tc    = 1 if method == "balance_decoy2" else 0
            pfor  = "🤑" if method == "balance_decoy" else "🤫"
            res   = settlement_balance(api_key, tokens, items, pfor,
                                       False, overwrite_amount=price + do["price"],
                                       token_confirmation_idx=tc)
            if res and "Bizz-err.Amount.Total" in res.get("message", ""):
                try:
                    valid = int(res["message"].split("=")[1].strip())
                    res   = settlement_balance(api_key, tokens, items, "SHARE_PACKAGE",
                                               False, overwrite_amount=valid,
                                               token_confirmation_idx=-1)
                except Exception: pass
            return self._ok(res)

        elif method == "qris":
            txn = settlement_qris(api_key, tokens, [main], "BUY_PACKAGE",
                                   False, overwrite_amount=price,
                                   token_confirmation_idx=0)
            if txn: print(f"[AutoBuy] QRIS txn: {txn} — bayar manual."); return True
            return False

        elif method in ("qris_decoy", "qris_decoy0"):
            dtype = "qris" if method == "qris_decoy" else "qris0"
            decoy = DecoyInstance.get_decoy(dtype)
            if not decoy or not decoy.get("option_code"): return False
            dd = get_package(api_key, tokens, decoy["option_code"])
            if not dd: return False
            do = dd["package_option"]
            di = PaymentItem(
                item_code=do["package_option_code"], product_type="",
                item_price=do["price"],
                item_name=f"{randint(1000,9999)} {do['name']}",
                tax=0, token_confirmation=dd["token_confirmation"],
            )
            txn = settlement_qris(api_key, tokens, [main, di], "SHARE_PACKAGE",
                                   False, token_confirmation_idx=1)
            if txn: print(f"[AutoBuy] QRIS+Decoy txn: {txn}"); return True
            return False

        print(f"[AutoBuy] Method tidak dikenal: {method}"); return False

    @staticmethod
    def _ok(res) -> bool:
        if res and res.get("status") == "SUCCESS": return True
        if res: print(f"[AutoBuy] Resp: {res.get('message','?')}")
        return False

    # ── monitor thread ────────────────────────────────────────────

    def _monitor_loop(self):
        from app.service.auth import AuthInstance
        _log("[AutoBuy] ▶ Monitor dimulai.")
        next_check: Dict[int, float] = {}

        while not self._mon_stop.is_set():
            now = time.time()
            self.reload()

            for entry in self.entries:
                if not entry.get("active", True): continue
                number   = entry["number"]
                interval = max(entry.get("interval_minutes", 5), 1) * 60

                if now < next_check.get(number, 0): continue
                next_check[number] = now + interval

                rt = next((r for r in AuthInstance.refresh_tokens
                           if r["number"] == number), None)
                if not rt: continue

                prev = AuthInstance.active_user
                try:
                    AuthInstance.set_active_user(number)
                    active = AuthInstance.get_active_user()
                    if not active: continue

                    api_key   = AuthInstance.api_key
                    tokens    = active["tokens"]
                    threshold = entry.get("threshold_mb", 100)
                    ts        = time.strftime("%H:%M:%S")

                    quota_mb = self.get_quota_mb(api_key, tokens, entry)
                    if quota_mb is None:
                        _log(f"[AutoBuy] [{number}] [{ts}] ⚠ Gagal cek kuota, skip.")
                        continue

                    pkg_label = ", ".join(
                        p.get("option_name", "?") for p in entry.get("packages", [])
                    ) or "?"

                    if quota_mb > threshold:
                        _log(f"[AutoBuy] [{number}] [{ts}] ✅ {quota_mb:.0f}MB > {threshold}MB aman.")
                        entry["buy_count_session"] = 0
                        continue

                    reason = "tidak ada" if quota_mb == 0.0 else f"sisa {quota_mb:.0f}MB"
                    _log(f"[AutoBuy] [{number}] [{ts}] ⚠ {reason} → BELI [{pkg_label}]")

                    max_buy = entry.get("max_buy", 3)
                    sess    = entry.get("buy_count_session", 0)
                    if max_buy > 0 and sess >= max_buy:
                        _log(f"[AutoBuy] [{number}] [{ts}] Max {max_buy}x tercapai.")
                        continue

                    count  = (max_buy - sess) if max_buy > 0 else 1
                    bought = self.do_purchase(api_key, tokens, entry, count=count)
                    entry["buy_count_session"] = sess + bought

                except Exception as e:
                    _log(f"[AutoBuy] [{number}] Error: {e}")
                finally:
                    if prev and prev["number"] != number:
                        try: AuthInstance.set_active_user(prev["number"])
                        except Exception: pass

            time.sleep(30)

        _log("[AutoBuy] ■ Monitor berhenti.")

    # ── refresh thread ────────────────────────────────────────────

    def _refresh_loop(self):
        from app.service.auth import AuthInstance
        from app.client.ciam import get_new_token
        interval = TOKEN_REFRESH_INTERVAL_MIN * 60
        print(f"[AutoBuy] ▶ Token-refresh dimulai (tiap {TOKEN_REFRESH_INTERVAL_MIN} mnt).")
        self._ref_stop.wait(60)

        while not self._ref_stop.is_set():
            self.reload()
            for entry in self.entries:
                if self._ref_stop.is_set(): break
                number = entry["number"]
                rt = next((r for r in AuthInstance.refresh_tokens
                           if r["number"] == number), None)
                if not rt: continue
                try:
                    print(f"[Refresh] [{number}] Refreshing token...")
                    new = get_new_token(AuthInstance.api_key,
                                       rt["refresh_token"],
                                       rt.get("subscriber_id", ""))
                    if new and "refresh_token" in new:
                        rt["refresh_token"] = new["refresh_token"]
                        AuthInstance.write_tokens_to_file()
                        if (AuthInstance.active_user and
                                AuthInstance.active_user["number"] == number):
                            AuthInstance.active_user["tokens"] = new
                        print(f"[Refresh] [{number}] ✅ OK")
                    else:
                        print(f"[Refresh] [{number}] ⚠ Gagal, skip.")
                except Exception as e:
                    print(f"[Refresh] [{number}] ⚠ {e} — skip.")
                self._ref_stop.wait(3)
            self._ref_stop.wait(interval)

        print("[AutoBuy] ■ Token-refresh berhenti.")

    # ── public ────────────────────────────────────────────────────

    def start_monitor(self):
        if self._mon_thread and self._mon_thread.is_alive():
            print("[AutoBuy] Monitor sudah jalan."); return
        self._mon_stop.clear()
        for e in self.entries: e["buy_count_session"] = 0
        self._mon_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="AutoBuyMonitor")
        self._mon_thread.start()

    def stop_monitor(self):
        self._mon_stop.set()
        if self._mon_thread: self._mon_thread.join(timeout=5)
        print("[AutoBuy] Monitor dihentikan.")

    def start_refresh(self):
        if self._ref_thread and self._ref_thread.is_alive():
            print("[AutoBuy] Refresh sudah jalan."); return
        self._ref_stop.clear()
        self._ref_thread = threading.Thread(
            target=self._refresh_loop, daemon=True, name="AutoBuyRefresh")
        self._ref_thread.start()

    def stop_refresh(self):
        self._ref_stop.set()
        if self._ref_thread: self._ref_thread.join(timeout=5)
        print("[AutoBuy] Token-refresh dihentikan.")

    def start_all(self):
        self.start_monitor(); self.start_refresh()

    def stop_all(self):
        self.stop_monitor(); self.stop_refresh()

    def is_monitor_running(self) -> bool:
        return bool(self._mon_thread and self._mon_thread.is_alive())

    def is_refresh_running(self) -> bool:
        return bool(self._ref_thread and self._ref_thread.is_alive())


AutoBuyInstance = AutoBuyService()
