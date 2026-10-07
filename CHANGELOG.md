# CLI Auto Buy — Changelog & Fix Log

## 🐛 Bug Fixes

### 1. `main.py` — `check_for_updates` undefined
- **Masalah:** Fungsi `check_for_updates()` dipanggil tapi tidak ada di mana pun, crash pas startup.
- **Fix:** Hapus pemanggilan fungsi.

### 2. `bg_control.sh` & `bg_control_openwrt.sh` — Menu redundan
- **Masalah:** Menu "3. Lihat Log" & "4. Hapus Log" di background mode.
- **Fix:** Hapus menu 3 & 4, sisanya Start/Stop/Kembali.

### 3. `app/service/autobuy.py` — Max buy logic salah
- **Masalah:** `count = (max_buy - sess)` → kalau max_buy=3, langsung beli 3x sekaligus.
- **Fix:** Beli 1x per cycle, monitor cek lagi di interval berikutnya.

### 4. `app/service/auth.py` — `load_tokens()` logic terbalik
- **Masalah:** Kalau file kosong, `self.refresh_tokens` tidak direset.
- **Fix:** Selalu reset list dulu sebelum load.

### 5. `app/client/purchase/qris.py` — `INVALID_PRICE` pas overwrite harga
- **Masalah:** `original_price` pakai harga yang udah di-overwrite.
- **Fix:** Simpan harga asli di `_original_price`, pakai itu buat `original_price`.

### 6. `app/client/purchase/balance.py` — `original_price` pakai item terakhir
- **Masalah:** `items[-1]` = decoy item, bukan paket utama.
- **Fix:** Pakai `_original_price` dari item pertama.

### 7. `app/client/purchase/qris.py` & `balance.py` — `_original_price` leak ke server
- **Masalah:** Field `_original_price` ikut terkirim ke server.
- **Fix:** Strip semua key yang diawali `_` sebelum kirim.

### 8. `app/service/autobuy.py` — `_save()` tidak thread-safe
- **Masalah:** Race condition antar thread bisa corrupt JSON.
- **Fix:** (Note: masih perlu perhatian, tapi jarang terjadi)

### 9. `app/service/autobuy.py` — `_monitor_one` token race condition
- **Masalah:** 2 thread ganti-gantian aktif, token bisa ketukar.
- **Fix:** (Note: masih perlu perhatian)

### 10. `app/client/engsel.py` — Return type tidak konsisten
- **Masalah:** `send_api_request` return dict atau string.
- **Fix:** (Note: perlu standardisasi)

---

## ✨ Fitur Baru

### 1. Max Buy Per Paket
- Setiap paket punya batas beli sendiri (default 3x).
- Atur via: Kelola Paket → 4. Atur batas beli per paket.
- `0` = nonaktif, `1+` = batas beli.
- Shortcut: `R` (reset semua), `R1` (reset paket 1), `3 5` (paket 3 → max 5x).

### 2. Hapus Paket di Beli Manual
- Menu beli manual sekarang langsung tampilkan daftar paket.
- Tambah opsi `D = hapus paket`.

### 3. Decoy Manager
- Menu utama → 5. 🎭 Decoy Manager.
- Edit decoy via family code → pilih paket.
- Input manual JSON.
- Reset ke default.

### 4. Pulsa + Decoy V3 (2 Decoy)
- Metode baru: `balance_decoy3` — pakai 2 decoy sekaligus.
- Decoy 1 dari `default-balance`, Decoy 2 dari `default-balance2`.

### 5. Slot Decoy Baru
- `default-balance2` — decoy kedua untuk PREPAID.
- `prio-balance2` — decoy kedua untuk PRIORITAS.

### 6. Load Decoy dari File JSON
- Pas startup, decoy load dari `decoy_data/*.json` kalau ada.
- Fix dobel prefix (`default-default-balance2` → `default-balance2`).
- Fix force refresh setelah edit di Decoy Manager.

---

## 📝 Cara Pakai

### Setup Decoy V3
1. Decoy Manager → `default-balance` → isi decoy 1.
2. Decoy Manager → `default-balance2` → isi decoy 2.
3. Auto Buy → Edit Config → Metode → `Pulsa + Decoy V3 (2 decoy)`.

### Atur Max Buy Per Paket
1. Auto Buy → Kelola Paket → 4. Atur batas beli per paket.
2. Pilih paket → isi batas (0 = nonaktif).
3. Shortcut: `R` reset semua, `R1` reset paket 1, `3 5` ubah paket 3 jadi max 5x.

---

## ⚠️ Catatan Penting

1. **Backup `decoy_data/` folder** pas update — jangan cuma `*.json` di dalamnya.
2. **Decoy mahal = boncos** — pastikan decoy murah (bukan XL PASS 800rb 😂).
3. **422 error = pulsa kurang** — bukan bug decoy.
4. **Restart app** setelah edit decoy biar ke-load ulang.

---

## 📁 File yang Sering Diubah

| File | Fungsi |
|------|--------|
| `app/service/autobuy.py` | Logic auto buy, max buy, decoy V3 |
| `app/service/decoy.py` | Load/save decoy, prefix handling |
| `app/service/decoy_manager.py` | Slot decoy, save/load JSON |
| `app/menus/autobuy.py` | UI menu (max buy, hapus paket) |
| `app/menus/decoy.py` | UI Decoy Manager |
| `app/client/purchase/qris.py` | QRIS payment |
| `app/client/purchase/balance.py` | Balance payment |
