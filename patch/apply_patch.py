#!/usr/bin/env python3
"""Patcher no-expire untuk Qct Modem Capabilities 2402-1 (ru.fieldtest.modemcaps).

Menerapkan 2 perubahan pada file smali hasil baksmali `a/z.smali`:

  1. Gerbang expired dimatikan — lompatan bersyarat menuju blok
     `throw IllegalArgumentException('x__x__d')` ("Build expired",
     terpicu saat am.b()[4] == 0) diganti lompatan tanpa syarat ke
     jalur lanjut inisialisasi. Blok throw menjadi kode mati.

  2. Jaring pengaman — kunci string banner 'EXPIRED. SOME FEATURES
     DISABLED' pada handler catch-all diganti kunci string spasi,
     sehingga banner tidak pernah tampil sekalipun handler terpanggil.

  3. Tombol "RAT/Band Preferences" (menu item 0, ikon centang di bar
     atas) selalu aktif — gerbang `SparseIntArray.get(3) != 0 &&
     am.b()[4] != 0` di `onPrepareOptionsMenu` dilewati.

Idempoten: aman dijalankan dua kali (patch yang sudah ada dilewati).

Pakai:
    python3 apply_patch.py <path-ke-a/z.smali> <path-ke-a/am.smali>
"""
import sys

PATCH1_OLD = "    if-eqz v2, :cond_e46d\n"
PATCH1_NEW = (
    "    # PATCH-NOEXPIRE-1: expiry gate disabled - never throw the coded\n"
    "    # \"Build expired\" IllegalArgumentException, always continue init.\n"
    "    goto :goto_e47c\n"
)
PATCH1_CTX = "    cmp-long v2, v4, v6\n"

PATCH2_OLD = "    const-wide v8, -0xa591659fedf0L\n"   # banner EXPIRED
PATCH2_NEW = (
    "    # PATCH-NOEXPIRE-2: banner key now decodes to a single space, so the\n"
    "    # handler in a.z can never render the \"EXPIRED\" banner into the header.\n"
    "    const-wide v8, -0xd996381edde0L\n"             # string " "
)

# gerbang enable tombol item 0 (RAT/Band Preferences) di onPrepareOptionsMenu:
# ... setShowAsAction(2), lalu getItem(0) dan hitung boolean dari f319b[3]/f324b[4]
PATCH3_CTX = (
    "    invoke-interface {v0, v1}, Landroid/view/MenuItem;->setShowAsAction(I)V\n"
    "\n"
    "    invoke-interface {p1, v4}, Landroid/view/Menu;->getItem(I)Landroid/view/MenuItem;\n"
    "\n"
    "    move-result-object v0\n"
)
PATCH3_NEW = (
    "    # PATCH-NOEXPIRE-3: \"RAT/Band Preferences\" (menu item 0, the action-bar\n"
    "    # checkmark / band-lock entry) is always enabled: skip its state gate\n"
    "    # (SparseIntArray.get(3) != 0 && am.b()[4] != 0) and force enabled.\n"
    "    const/4 v6, 0x1\n"
    "\n"
    "    goto :goto_3f\n"
    "\n"
)


def patch_z(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    changed = False

    if "PATCH-NOEXPIRE-1" in src:
        print("[1/3] gerbang expired: sudah terpatch, lewati")
    else:
        ctx = PATCH1_CTX + "\n" + PATCH1_OLD
        if ctx not in src:
            print("[1/3] GAGAL: konteks gerbang expired tidak ditemukan "
                  "(pastikan ini smali dari build 2402-1)")
            return -1
        src = src.replace(ctx, PATCH1_CTX + "\n" + PATCH1_NEW, 1)
        changed = True
        print("[1/3] gerbang expired: DIPATCH")

    if "PATCH-NOEXPIRE-2" in src:
        print("[2/3] banner handler: sudah terpatch, lewati")
    else:
        if src.count(PATCH2_OLD) != 1:
            print("[2/3] GAGAL: kunci banner EXPIRED tidak ditemukan "
                  "tepat 1x (build tidak cocok?)")
            return -1
        src = src.replace(PATCH2_OLD, PATCH2_NEW, 1)
        changed = True
        print("[2/3] banner handler: DIPATCH")

    if changed:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        print("OK — file diperbarui:", path)
    return 0


def patch_am(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    if "PATCH-NOEXPIRE-3" in src:
        print("[3/3] menu Band Preferences: sudah terpatch, lewati")
        return 0
    if src.count(PATCH3_CTX) != 1:
        print("[3/3] GAGAL: konteks enable item 0 tidak ditemukan tepat 1x "
              "(build tidak cocok?)")
        return -1
    src = src.replace(PATCH3_CTX, PATCH3_CTX + PATCH3_NEW, 1)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("[3/3] menu Band Preferences: DIPATCH")
    return 0


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    z_rc = patch_z(sys.argv[1])
    if z_rc != 0:
        return 1
    if patch_am(sys.argv[2]) != 0:
        return 1
    print("OK — patch selesai" if z_rc == 0 else "OK — tidak ada perubahan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
