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

  4. Daftar band tidak lagi kosong — mask kapabilitas RAT (extra "b")
     di layar Band Preferences (`a/em`) hanya pernah terisi bit
     NSA/NR oleh parser DIAG build ini, sehingga grup GSM/UMTS/LTE
     tidak pernah terbentuk di modem era LTE. Bit grup GSM(2)/UMTS(3)/
     LTE(4) disuntikkan saat layar membaca extra tersebut; isi grup
     tetap dari tabel band asli modem (extra d..L).

  5. Anti force-close — runnable auto-expand di `a/em` tidak lagi
     memanggil `expandGroup(0)` bila adapter kosong
     (sebelumnya: IndexOutOfBoundsException di `a.bg.getChildrenCount`).

Idempoten: aman dijalankan dua kali (patch yang sudah ada dilewati).

Pakai:
    python3 apply_patch.py <path-ke-a/z.smali> <path-ke-a/am.smali> <path-ke-a/em.smali>
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
        print("[1/5] gerbang expired: sudah terpatch, lewati")
    else:
        ctx = PATCH1_CTX + "\n" + PATCH1_OLD
        if ctx not in src:
            print("[1/3] GAGAL: konteks gerbang expired tidak ditemukan "
                  "(pastikan ini smali dari build 2402-1)")
            return -1
        src = src.replace(ctx, PATCH1_CTX + "\n" + PATCH1_NEW, 1)
        changed = True
        print("[1/5] gerbang expired: DIPATCH")

    if "PATCH-NOEXPIRE-2" in src:
        print("[2/5] banner handler: sudah terpatch, lewati")
    else:
        if src.count(PATCH2_OLD) != 1:
            print("[2/3] GAGAL: kunci banner EXPIRED tidak ditemukan "
                  "tepat 1x (build tidak cocok?)")
            return -1
        src = src.replace(PATCH2_OLD, PATCH2_NEW, 1)
        changed = True
        print("[2/5] banner handler: DIPATCH")

    if changed:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        print("OK — file diperbarui:", path)
    return 0


def patch_am(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    if "PATCH-NOEXPIRE-3" in src:
        print("[3/5] menu Band Preferences: sudah terpatch, lewati")
        return 0
    if src.count(PATCH3_CTX) != 1:
        print("[3/5] GAGAL: konteks enable item 0 tidak ditemukan tepat 1x "
              "(build tidak cocok?)")
        return -1
    src = src.replace(PATCH3_CTX, PATCH3_CTX + PATCH3_NEW, 1)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("[3/5] menu Band Preferences: DIPATCH")
    return 0


def patch_em(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    changed = False

    # --- Patch 4 -----------------------------------------------------------
    if "PATCH-NOEXPIRE-4" in src:
        print("[4/5] mask RAT Band Preferences: sudah terpatch, lewati")
    else:
        ctx = (
            "    iput-object v0, p0, La/em;->a:[J\n"
            "\n"
            "    invoke-virtual {p0}, La/em;->getIntent()Landroid/content/Intent;\n"
        )
        new = (
            "    iput-object v0, p0, La/em;->a:[J\n"
            "\n"
            + PATCH4_BODY +
            "    invoke-virtual {p0}, La/em;->getIntent()Landroid/content/Intent;\n"
        )
        if src.count(ctx) != 1:
            print("[4/5] GAGAL: konteks extra \"b\" di em tidak ditemukan tepat 1x")
            return -1
        src = src.replace(ctx, new, 1)
        changed = True
        print("[4/5] mask RAT Band Preferences: DIPATCH")

    # --- Patch 5 -----------------------------------------------------------
    if "PATCH-NOEXPIRE-5" in src:
        print("[5/5] pengaman expandGroup: sudah terpatch, lewati")
    else:
        ctx = (
            "    check-cast p0, La/el;\n"
            "\n"
            "    if-eqz p0, :cond_b\n"
            "\n"
            "    const/4 v0, 0x0\n"
        )
        new = (
            "    check-cast p0, La/el;\n"
            "\n"
            "    if-eqz p0, :cond_b\n"
            "\n"
            + PATCH5_BODY +
            "    const/4 v0, 0x0\n"
        )
        if src.count(ctx) != 1:
            print("[5/5] GAGAL: konteks expandGroup di em tidak ditemukan tepat 1x")
            return -1
        src = src.replace(ctx, new, 1)
        changed = True
        print("[5/5] pengaman expandGroup: DIPATCH")

    if changed:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
    return 0


PATCH4_BODY = """    # PATCH-NOEXPIRE-4: the RAT-capability mask in extra "b" only ever gets
    # NSA/NR bits from this build's DIAG parsers, so the Band Preferences
    # screen builds zero groups (and used to crash) on LTE-era modems.
    # Force the GSM(2)/UMTS(3)/LTE(4) group bits the phone's radios support;
    # group contents still come from the real modem band tables (extras d..L).
    if-eqz v0, :patch4_done

    array-length v1, v0

    const/4 v2, 0x0

    :patch4_loop
    if-ge v2, v1, :patch4_done

    aget-wide v3, v0, v2

    const-wide/16 v5, 0x1c

    or-long/2addr v3, v5

    aput-wide v3, v0, v2

    add-int/lit8 v2, v2, 0x1

    goto :patch4_loop

    :patch4_done
"""

PATCH5_BODY = """    # PATCH-NOEXPIRE-5: never expand group 0 of an empty adapter
    # (was: IndexOutOfBoundsException in a.dr.get -> force close).
    invoke-virtual {p0}, Landroid/widget/ExpandableListView;->getExpandableAdapter()Landroid/widget/ExpandableListAdapter;

    move-result-object v0

    if-eqz v0, :cond_b

    invoke-interface {v0}, Landroid/widget/ExpandableListAdapter;->getGroupCount()I

    move-result v0

    if-lez v0, :cond_b

"""


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    z_rc = patch_z(sys.argv[1])
    if z_rc != 0:
        return 1
    if patch_am(sys.argv[2]) != 0:
        return 1
    if patch_em(sys.argv[3]) != 0:
        return 1
    print("OK — patch selesai")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
