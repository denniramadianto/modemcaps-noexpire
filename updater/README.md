# Updater dalam aplikasi (v1.4+)

`Updater.java` adalah kode updater yang dikompilasi menjadi
`classes2.dex` dan digabungkan ke APK hasil patch. Ia menambahkan menu
"🔄 Cek Update & Riwayat Versi" di layar utama ModemCaps: daftar rilis
dari GitHub repo ini, unduh APK rilis ke folder aplikasi, pasang /
rollback via root `pm install -r -d`, dan hapus file unduhan.

`add_internet_permission.py` menyisipkan
`<uses-permission android:name="android.permission.INTERNET"/>` ke
manifest biner (APK asli tidak punya izin apa pun; tanpa ini updater
tidak bisa mengunduh). Skrip hanya menambahkan string baru ke string
pool (indeks lama tidak berubah) dan menyisipkan elemen sebelum
`<uses-sdk>`; hasil diverifikasi dengan `aapt2 dump xmltree`.

## Reproduksi classes2.dex

```sh
export PATH=<jdk17>/bin:$PATH
javac -encoding UTF-8 -cp <sdk>/platforms/android-34/android.jar \
      -d updater-classes updater/Updater.java
<sdk>/build-tools/34.0.0/d8 --lib <sdk>/platforms/android-34/android.jar \
      --output . --min-api 16 updater-classes/upd/*.class
# menghasilkan classes.dex -> ganti nama menjadi classes2.dex
```

Kait di sisi aplikasi ada di Patch 6 (`patch/apply_patch.py`):
`addMenuItem()` dipanggil dari `onCreateOptionsMenu` dan `handleItem()`
dicegat di awal `onOptionsItemSelected` pada `a/am.smali`. Perhatian:
method terakhir memakai `.registers 39` sehingga kaitnya WAJIB memakai
bentuk `invoke-static/range` (register parameter berada di atas v15).
