# Analisis Reverse Engineering — Qct Modem Capabilities (`ru.fieldtest.modemcaps`) & Mekanisme "EXPIRED"

Tanggal analisis: 20 Oktober 2026 · Build yang dianalisis: **2402-1** (`modemcaps-2402-1d.apk`)

## 1. Identitas APK

| Atribut | Nilai |
|---|---|
| Package | `ru.fieldtest.modemcaps` |
| versionName / versionCode | `2402-1` / `2402001` |
| Label | Qct Modem Capabilities |
| Ukuran / SHA-256 | 541.032 byte / `cf20ddb3587139b54d009f2b0b9de040ff7ecb83db8ba596c9781607cb596f7a` |
| minSdk / targetSdk | 16 / 29 |
| Permission Android | **tidak ada sama sekali** |
| Penanda tangan | self-signed `CN=13.beta2, C=RU`, berlaku 22 Nov 2015 – 15 Nov 2040 (bukan penyebab "expired") |
| Isi | 1× `classes.dex`, native `liba.so`/`libb.so`/`libc.so` per ABI (arm64-v8a, armeabi-v7a), resource ter-obfuskasi (AndResGuard) |

Aplikasi ditulis dengan Kotlin + kotlinx-coroutines; seluruh class ter-obfuskasi
ke package `a`. Enkripsi string kustomnya berhasil dipecahkan (tabel 8 potong ×
8191 char di `a.c` + PRNG di `a.a(long, String[])`), 2.184 string terdekripsi —
metode ini juga dipakai untuk menemukan teks status expired di bawah.

## 2. Cara kerja singkat

- Eskalasi root via `su` (ProcessBuilder), lalu `supolicy --live` menambal
  SELinux agar socket **QRTR** dan `/dev/diag` bisa diakses.
- Komunikasi modem dilakukan library native `liba.so` (JNI dinamis, stripped):
  frame **QMI** dirakit di Java, dikirim via DIAG + ioctl (terlihat di logcat:
  `ioctlcmd=0xc302`).
- Fitur: penampil laporan kapabilitas CA (Source RRC, tabel DL/UL Bands),
  editor file EFS (mis. `lte_feature_enable`, `cap_*` NR 256QAM/MIMO, kunci
  sel PCI/EARFCN), Band Preferences, profil PDC.

## 3. Temuan utama: di mana "expired" ditempatkan

Status pada header laporan (bukti: screenshot Redmi 4X/santoni, SDM435):

```
© 13.beta2, ver. 2402-1
EXPIRED. SOME FEATURES DISABLED ========
Xiaomi Redmi 4X
 Model ID     : santoni
 ...
```

### 3.1 Teksnya bersembunyi di class yang gagal di-decompile

Class **`a.z`** adalah coroutine inisialisasi modem raksasa (satu metode =
59.472 instruksi — ART menolak mengkompilasinya: *"Method exceeds compiler
instruction limit"*). jadx gagal men-decompile class ini, sehingga ±170 kunci
string miliknya tidak ikut terdekripsi pada pemeriksaan awal; kesimpulan
"tidak ada expired" dari pemeriksaan pertama itu ternyata keliru persis
karena lubang ini.

Teks status adalah entri tabel string terenkripsi:

- kunci `0xFFFF5A6E9A601210` → `'❌EXPIRED.⏹ SOME FEATURES DISABLED '`
  (❌/⏹ adalah penanda pewarnaan merah oleh pemformat spannable aplikasi)
- kunci lain relevan: `'expire'`, `'Build '`, placeholder `'x__'`,
  pemisah `'-================================'`, pesan pengecualian `'x__x__d'`.

### 3.2 Mekanisme keputusan (bytecode `a.z`, offset instruksi ±0xE4xx–0xE6xx)

1. Menjelang akhir inisialisasi ada blok uji:
   `v2 = (string hasil tahap tidak kosong)`. Bila tidak kosong, dijalankan
   **gerbang validasi**:

   ```
   arr = am.b()                 // long[] — state sesi modem (field La/am;.b:[J)
   if (arr[4] == 0)
       throw new IllegalArgumentException(decrypt('x__x__d'))
   ```

2. `a.z` memiliki handler *catch-all* untuk seluruh tahap inisialisasi.
   Bila exception lolos (termasuk yang di atas), handler:
   - mengambil `Throwable.getMessage()`,
   - mengganti placeholder pertama `'x__'` → `'Build '` dan kedua → `'expire'`
     via `gp.c(...)` (replace-first); pesan `'x__x__d'` berubah menjadi
     **"Build expired"** — kode status yang memang dirancang pengembang,
   - menyisipkan teks EXPIRED menggantikan potongan pemisah `'====…'`
     pada header laporan,
   - menambahkan baris info error (`'E. ' + pesan + '\nT2\n'`, diwarnai).

3. Header final di-XOR dengan kunci berjalan (19, 20, 21, …) dan disimpan
   `a.z` sendiri ke **SharedPreferences berkas `g`, kunci `x`**
   (`edit().putString("x", …).apply()`), dibaca kembali setiap start —
   status bersifat persisten. Saat menyimpan, app menandai header "tercemar"
   bila memuat `'ED ='` (potongan dari "DISABLED =") atau `'E. '`, lalu
   memotong salinan simpan di pemisah `'===\n'`.

### 3.3 Bukan berbasis tanggal

Pemeriksaan menyeluruh di dua build (2019-03-13-7 dan 2402-1):

- **0 referensi** API jam dinding di DEX: `currentTimeMillis`, `Calendar`,
  `SimpleDateFormat`, `LocalDate` — Java hanya memakai `SystemClock`
  (monotonik) dan `elapsedRealtime`.
- Native `liba.so`: `clock_gettime(CLOCK_REALTIME)` semata untuk stempel
  waktu frame DIAG/QMI; tidak ada konstanta epoch masa berlaku.
- Satu-satunya nilai "waktu" yang disentuh Java: coroutine `a.ap` menghitung
  `hash(File("/dev").lastModified() >>> 12)` ke sel status — `/dev` di
  Android berubah saat boot; ini bagian dari state sesi, bukan kalender.

Kesimpulan: label "expired" di build ini = **ketidaksesuaian state sesi
modem terhadap nilai acuan internal** (gerbang `am.b()[4] == 0`), bukan
batas waktu kalender.

## 4. Patch (yang diterapkan repo ini)

Di `a/z.smali` (hasil baksmali dari `classes.dex`):

1. **Gerbang dimatikan** — pada blok uji `am.b()[4]`:

   ```diff
        cmp-long v2, v4, v6
   -    if-eqz v2, :cond_e46d
   +    # PATCH-NOEXPIRE-1: selalu lanjut, jangan lempar "Build expired"
   +    goto :goto_e47c
   ```

   Blok `:cond_e46d` (konstruksi + `throw IllegalArgumentException`)
   menjadi kode mati. Seluruh tahap sesudah gerbang kini selalu dijalankan.

2. **Jaring pengaman tampilan** — pada handler catch-all `a.z`:

   ```diff
   -    const-wide v8, -0xa591659fedf0L
   +    # PATCH-NOEXPIRE-2: kunci banner → string spasi
   +    const-wide v8, -0xd996381edde0L
   ```

   Kunci baru terdekripsi menjadi `" "` (spasi), jadi banner EXPIRED
   tidak pernah dirender sekalipun handler terpanggil oleh error lain.

Skrip otomatisnya: `patch/apply_patch.py`.

## 5. Reproduksi patch (build dari nol)

```bash
# alat: JDK 17, baksmali/smali 2.5.2 (Maven Central: org.smali:*),
#       Android SDK build-tools 34.0.0 (zipalign, apksigner)
CP=$(ls smali-jars/*.jar | tr '\n' ':')

# 1) unzip APK asli, ambil classes.dex, bongkar
java -cp "$CP" org.jf.baksmali.Main disassemble classes.dex -o smali

# 2) patch
python3 patch/apply_patch.py smali/a/z.smali

# 3) rakit
java -cp "$CP" org.jf.smali.Main assemble smali -o classes_patched.dex

# 4) repack: salin isi APK asli (tanpa META-INF), ganti classes.dex,
#    zip, lalu:
zipalign -p -f 4 unsigned.apk aligned.apk
apksigner sign --ks <keystore-anda> --out modemcaps-2402-1-noexpire.apk aligned.apk

# 5) verifikasi
apksigner verify --verbose modemcaps-2402-1-noexpire.apk
aapt2 dump badging modemcaps-2402-1-noexpire.apk | head
```

Build referensi repo ini terverifikasi: signature scheme v1+v2+v3 valid,
ZIP utuh, SHA-256 DEX di dalam APK identik dengan DEX terpatch
(`1a95ccd8d12b86112244bb29cec455ba818533767b86145688f23e8634501721`).

## 6. Catatan pemasangan

- Tanda tangan berbeda dari aslinya → **uninstall dulu**, baru pasang.
  Sekaligus menghapus SharedPreferences lama berisi header EXPIRED.
- Tetap butuh root (jalur DIAG/QRTR + `supolicy`), sama seperti aslinya.
- Patch bersifat bedah minimal (2 instruksi): perilaku aplikasi di luar
  gerbang expired tidak diubah sama sekali.
