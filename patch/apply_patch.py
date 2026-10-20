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

Idempoten: aman dijalankan dua kali (patch yang sudah ada dilewati).

Pakai:
    python3 apply_patch.py <path-ke-a/z.smali>
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


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    changed = False

    # --- Patch 1 -----------------------------------------------------------
    if "PATCH-NOEXPIRE-1" in src:
        print("[1/2] gerbang expired: sudah terpatch, lewati")
    else:
        ctx = PATCH1_CTX + "\n" + PATCH1_OLD
        if ctx not in src:
            print("[1/2] GAGAL: konteks gerbang expired tidak ditemukan "
                  "(pastikan ini smali dari build 2402-1)")
            return 1
        src = src.replace(ctx, PATCH1_CTX + "\n" + PATCH1_NEW, 1)
        changed = True
        print("[1/2] gerbang expired: DIPATCH")

    # --- Patch 2 -----------------------------------------------------------
    if "PATCH-NOEXPIRE-2" in src:
        print("[2/2] banner handler: sudah terpatch, lewati")
    else:
        if src.count(PATCH2_OLD) != 1:
            print("[2/2] GAGAL: kunci banner EXPIRED tidak ditemukan "
                  "tepat 1x (build tidak cocok?)")
            return 1
        src = src.replace(PATCH2_OLD, PATCH2_NEW, 1)
        changed = True
        print("[2/2] banner handler: DIPATCH")

    if changed:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        print("OK — file diperbarui:", path)
    else:
        print("OK — tidak ada perubahan (sudah terpatch penuh)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
