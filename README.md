# modemcaps-noexpire

Patch "no-expire" untuk **Qct Modem Capabilities** (`ru.fieldtest.modemcaps`) build **2402-1** —
menghilangkan status **"EXPIRED. SOME FEATURES DISABLED"** yang muncul di header laporan
sehingga aplikasi (aplikasi uji lapangan yang sudah tidak diperbarui lagi oleh pengembangnya)
tetap dapat dipakai penuh di perangkat sendiri.

> ⚠️ **Disclaimer** — Proyek tidak resmi, dibuat untuk penggunaan pribadi/di perangkat
> sendiri. Aplikasi aslinya adalah karya pengembangnya (© 13.beta2,
> https://t.me/ru_fieldtest_modemcaps). Repositori ini hanya berisi *dokumentasi analisis*
> dan *skrip patch* terhadap salinan APK yang dimiliki pengguna; bukan distribusi ulang
> aplikasi asli.

## Unduh

APK hasil patch tersedia di halaman **Releases** repositori ini
(`modemcaps-2402-1-noexpire.apk`).

| | |
|---|---|
| Package | `ru.fieldtest.modemcaps` |
| Versi | 2402-1 (versionCode 2402001), sama seperti aslinya |
| Ukuran | ± 524 KB |
| SHA-256 APK | `aaaea5b6f96e76cc2564c969fb0691ba0cc460780a03d6f23564ea69fffbfabb` |

## Cara pasang (PENTING)

1. **Uninstall dulu** versi lama. APK patch ditandatangani dengan kunci baru
   (kunci penanda tangan asli tidak dimiliki), jadi Android menolak pemasangan
   menimpa versi lama.
2. Pasang `modemcaps-2402-1-noexpire.apk`.
3. Selesai — bonus: uninstall juga menghapus header lama, karena status EXPIRED
   lama tersimpan di SharedPreferences aplikasi.
4. Aplikasi ini membutuhkan **root** (Magisk) agar jalur DIAG/QRTR ke modem
   terbuka, sama seperti versi aslinya.

## Apa sebenarnya "expired" di aplikasi ini?

Hasil reverse engineering lengkap ada di [docs/ANALISIS.md](docs/ANALISIS.md).
Ringkasnya:

- **Bukan berbasis tanggal.** Di seluruh aplikasi tidak ada satu pun pembacaan
  jam dinding (`currentTimeMillis`, `Calendar`, dsb.), tidak ada konstanta
  tanggal kedaluwarsa, dan sertifikat penandatangan berlaku sampai 2040.
- Status ditentukan di coroutine inisialisasi raksasa **`a.z`** (± 59 ribu
  instruksi). Menjelang akhir inisialisasi ada **gerbang validasi**: bila elemen
  ke-5 array state sesi `am.b()[4]` bernilai 0, kode melempar
  `IllegalArgumentException` dengan pesan berkode `'x__x__d'`.
- Handler penangkap semua exception di `a.z` menerjemahkan pesan berkode itu:
  placeholder `'x__'` pertama diganti `'Build '`, kedua diganti `'expire'`
  (→ terbaca **"Build expired"**), lalu baris
  `❌EXPIRED.⏹ SOME FEATURES DISABLED ` disisipkan ke header laporan,
  header di-XOR (kunci berjalan 19, 20, 21, …) dan disimpan ke
  SharedPreferences berkas `g` kunci `x` — makanya statusnya persisten dan
  tahapan inisialisasi sesudah gerbang tidak pernah dijalankan
  ("some features disabled").

## Patch yang diterapkan

Dua perubahan smali di `a/z.smali` (lihat `patch/`):

1. **Gerbang expired dimatikan** — lompatan bersyarat menuju blok `throw`
   "Build expired" diganti lompatan tanpa syarat ke jalur lanjut inisialisasi.
   Blok `throw`-nya sendiri menjadi kode mati. Inisialisasi kini selalu
   berjalan tuntas.
2. **Banner tidak bisa tampil lagi (jaring pengaman)** — kunci string
   banner EXPIRED (`0xFFFF5A6E9A601210`) di handler diganti kunci string
   spasi, sehingga sekalipun handler exception terpanggil karena error lain,
   yang disisipkan ke header hanyalah spasi.

APK hasil patch dibangun ulang dari DEX yang dirakit dari smali terpatch,
di-zipalign, lalu ditandatangani ulang (skema v1+v2+v3 terverifikasi).

## Bangun sendiri dari APK asli

Prasyarat: JDK 17, Android SDK build-tools 34 (aapt2 tidak wajib), `smali`/
`baksmali` 2.5.2 (Maven Central), `gh`/zip biasa.

```bash
# 1. Bongkar DEX asli
java -cp "<classpath-smali>" org.jf.baksmali.Main disassemble classes.dex -o smali

# 2. Terapkan patch
python3 patch/apply_patch.py smali/a/z.smali

# 3. Rakit DEX baru
java -cp "<classpath-smali>" org.jf.smali.Main assemble smali -o classes_patched.dex

# 4. Repack: ganti classes.dex di dalam APK, buang META-INF lama, zipalign,
#    lalu tandatangani dengan keystore Anda sendiri (apksigner).
```

Detail langkah demi langkah + bukti verifikasi ada di
[docs/ANALISIS.md](docs/ANALISIS.md) bagian "Reproduksi Patch".

## Struktur repo

- `README.md` — dokumen ini
- `docs/ANALISIS.md` — laporan reverse engineering lengkap
- `patch/apply_patch.py` — skrip patcher (idempoten, memeriksa konteks baris)
- `patch/z.smali.patch` — diff smali mentah untuk referensi manual

## Lisensi

Dokumentasi & skrip di repo ini: MIT (lihat `LICENSE`). Aplikasi asal
bukan karya repo ini dan tidak termasuk dalam lisensi tersebut.
