package upd;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.ProgressDialog;
import android.content.Context;
import android.content.DialogInterface;
import android.content.SharedPreferences;
import android.view.Menu;
import android.view.MenuItem;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/**
 * In-app updater for the no-expire patched ModemCaps build.
 * Lives in classes2.dex; hooked into the main activity's options menu
 * (see smali patches in a/am.smali). Lists GitHub releases of
 * denniramadianto/modemcaps-noexpire, downloads release APKs into the
 * app's own folder, installs any of them via root `pm install`
 * (install = update, older version = rollback), and can delete the
 * downloaded files again.
 */
public final class Updater {

    public static final int MENU_ID = 0x75706431; // "upd1"

    private static final String API_URL =
            "https://api.github.com/repos/denniramadianto/modemcaps-noexpire/releases?per_page=30";
    private static final String PREFS = "noexpire_updater";
    private static final String KEY_TAG = "installed_tag";

    private Updater() {
    }

    // ------------------------------------------------------------------
    // Menu hooks (called from patched a.am)
    // ------------------------------------------------------------------

    public static void addMenuItem(Activity act, Menu menu) {
        try {
            if (menu == null) {
                return;
            }
            if (menu.findItem(MENU_ID) == null) {
                menu.add(0, MENU_ID, 999, "\uD83D\uDD04 Cek Update & Riwayat Versi");
            }
        } catch (Throwable ignored) {
        }
    }

    public static boolean handleItem(Activity act, MenuItem item) {
        try {
            if (item == null || item.getItemId() != MENU_ID) {
                return false;
            }
            showMain(act);
            return true;
        } catch (Throwable t) {
            return false;
        }
    }

    // ------------------------------------------------------------------
    // Data model
    // ------------------------------------------------------------------

    private static final class Release {
        String tag;
        String name;
        String date;
        String notes;
        String assetName;
        String assetUrl;
        long assetSize;
        String sha256; // may be null

        File localFile(File dir) {
            return assetName == null ? null : new File(dir, assetName);
        }
    }

    private static File apkDir(Context ctx) {
        File base = ctx.getExternalFilesDir(null);
        if (base == null) {
            base = ctx.getFilesDir();
        }
        File dir = new File(base, "apks");
        if (!dir.exists()) {
            dir.mkdirs();
        }
        return dir;
    }

    // ------------------------------------------------------------------
    // Main dialog
    // ------------------------------------------------------------------

    private static void showMain(final Activity act) {
        String installed = identifyInstalled(act);
        long used = 0;
        int count = 0;
        File[] files = apkDir(act).listFiles();
        if (files != null) {
            for (File f : files) {
                if (f.isFile()) {
                    used += f.length();
                    count++;
                }
            }
        }
        String msg = "Versi terpasang: " + installed + "\n"
                + "APK terunduh: " + count + " file (" + fmtSize(used) + ")\n\n"
                + "Tekan CEK VERSI untuk melihat riwayat rilis dari GitHub, "
                + "mengunduh, memasang / rollback, dan menghapus file APK.";
        new AlertDialog.Builder(act)
                .setTitle("ModemCaps Updater")
                .setMessage(msg)
                .setPositiveButton("CEK VERSI", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        fetchReleases(act);
                    }
                })
                .setNegativeButton("TUTUP", null)
                .show();
    }

    private static String identifyInstalled(Context ctx) {
        try {
            SharedPreferences sp = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            String tag = sp.getString(KEY_TAG, null);
            if (tag != null && tag.length() > 0) {
                return tag + " (via updater)";
            }
        } catch (Throwable ignored) {
        }
        return "2402-1 no-expire";
    }

    // ------------------------------------------------------------------
    // Release list
    // ------------------------------------------------------------------

    private static void fetchReleases(final Activity act) {
        final ProgressDialog pd = new ProgressDialog(act);
        pd.setMessage("Mengambil daftar rilis...");
        pd.setCancelable(false);
        pd.show();
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    String json = httpGet(API_URL);
                    final List<Release> rels = parseReleases(json);
                    final String myHash = sha256File(new File(act.getApplicationInfo().sourceDir));
                    act.runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            pd.dismiss();
                            showList(act, rels, myHash);
                        }
                    });
                } catch (final Exception e) {
                    act.runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            pd.dismiss();
                            error(act, "Gagal mengambil daftar rilis.\n\n" + e.getMessage()
                                    + "\n\nPeriksa koneksi internet lalu coba lagi.");
                        }
                    });
                }
            }
        }).start();
    }

    private static List<Release> parseReleases(String json) throws Exception {
        List<Release> out = new ArrayList<Release>();
        JSONArray arr = new JSONArray(json);
        for (int i = 0; i < arr.length(); i++) {
            JSONObject o = arr.getJSONObject(i);
            Release r = new Release();
            r.tag = o.optString("tag_name", "");
            r.name = o.optString("name", r.tag);
            String pub = o.optString("published_at", "");
            r.date = pub.length() >= 10 ? pub.substring(0, 10) : pub;
            r.notes = o.optString("body", "");
            JSONArray assets = o.optJSONArray("assets");
            if (assets != null) {
                for (int j = 0; j < assets.length(); j++) {
                    JSONObject a = assets.getJSONObject(j);
                    String an = a.optString("name", "");
                    if (an.endsWith(".apk")) {
                        r.assetName = an;
                        r.assetUrl = a.optString("browser_download_url", "");
                        r.assetSize = a.optLong("size", 0);
                        String digest = a.optString("digest", "");
                        if (digest.startsWith("sha256:") && digest.length() >= 71) {
                            r.sha256 = digest.substring(7, 71);
                        }
                        break;
                    }
                }
            }
            if (r.sha256 == null && r.notes != null) {
                r.sha256 = extractSha(r.notes);
            }
            out.add(r);
        }
        return out;
    }

    private static String extractSha(String text) {
        // release notes contain a full 64-char hex SHA-256 of the APK
        String lower = text.toLowerCase(Locale.US);
        for (int i = 0; i + 64 <= lower.length(); i++) {
            boolean ok = true;
            for (int k = 0; k < 64; k++) {
                char c = lower.charAt(i + k);
                if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) {
                    ok = false;
                    break;
                }
            }
            if (ok) {
                char before = i > 0 ? lower.charAt(i - 1) : ' ';
                char after = i + 64 < lower.length() ? lower.charAt(i + 64) : ' ';
                boolean bOk = !((before >= '0' && before <= '9') || (before >= 'a' && before <= 'f'));
                boolean aOk = !((after >= '0' && after <= '9') || (after >= 'a' && after <= 'f'));
                if (bOk && aOk) {
                    return lower.substring(i, i + 64);
                }
            }
        }
        return null;
    }

    private static void showList(final Activity act, final List<Release> rels, final String myHash) {
        final File dir = apkDir(act);
        final SharedPreferences sp = act.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        final String prefTag = sp.getString(KEY_TAG, "");
        List<String> labels = new ArrayList<String>();
        for (Release r : rels) {
            StringBuilder sb = new StringBuilder();
            sb.append(r.tag);
            if (r.date.length() > 0) {
                sb.append("  ·  ").append(r.date);
            }
            File f = r.localFile(dir);
            boolean downloaded = f != null && f.exists();
            boolean installed = (r.sha256 != null && r.sha256.equals(myHash))
                    || (prefTag != null && prefTag.equals(r.tag) && !downloaded);
            if (installed) {
                sb.append("\nSEDANG TERPASANG");
            } else if (downloaded) {
                sb.append("\nTerunduh · ").append(fmtSize(f.length()));
            } else {
                sb.append("\nBelum diunduh · ").append(fmtSize(r.assetSize));
            }
            labels.add(sb.toString());
        }
        String[] items = labels.toArray(new String[0]);
        new AlertDialog.Builder(act)
                .setTitle("Riwayat Versi (GitHub)")
                .setItems(items, new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int which) {
                        showRelease(act, rels.get(which), myHash);
                    }
                })
                .setNegativeButton("TUTUP", null)
                .show();
    }

    // ------------------------------------------------------------------
    // Per-release actions
    // ------------------------------------------------------------------

    private static void showRelease(final Activity act, final Release r, final String myHash) {
        final File dir = apkDir(act);
        final File f = r.localFile(dir);
        final boolean downloaded = f != null && f.exists();
        boolean installed = r.sha256 != null && r.sha256.equals(myHash);

        StringBuilder msg = new StringBuilder();
        msg.append("Tanggal: ").append(r.date).append("\n");
        msg.append("Status: ").append(installed ? "SEDANG TERPASANG"
                : downloaded ? "Terunduh (" + fmtSize(f.length()) + ")" : "Belum diunduh").append("\n\n");
        String notes = r.notes == null ? "" : r.notes.replace("`", "").trim();
        if (notes.length() > 700) {
            notes = notes.substring(0, 700) + "...";
        }
        msg.append(notes);

        AlertDialog.Builder b = new AlertDialog.Builder(act)
                .setTitle("Rilis " + r.tag)
                .setMessage(msg.toString())
                .setNegativeButton("TUTUP", null);
        if (!downloaded) {
            b.setPositiveButton("UNDUH", new DialogInterface.OnClickListener() {
                @Override
                public void onClick(DialogInterface d, int w) {
                    download(act, r);
                }
            });
        } else {
            b.setPositiveButton("PASANG VERSI INI", new DialogInterface.OnClickListener() {
                @Override
                public void onClick(DialogInterface d, int w) {
                    confirmInstall(act, r, f);
                }
            });
            b.setNeutralButton("HAPUS FILE", new DialogInterface.OnClickListener() {
                @Override
                public void onClick(DialogInterface d, int w) {
                    confirmDelete(act, r, f);
                }
            });
        }
        b.show();
    }

    private static void confirmDelete(final Activity act, final Release r, final File f) {
        new AlertDialog.Builder(act)
                .setTitle("Hapus file?")
                .setMessage(f.getName() + " (" + fmtSize(f.length()) + ") akan dihapus dari penyimpanan.")
                .setPositiveButton("HAPUS", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        boolean ok = f.delete();
                        Toast.makeText(act, ok ? "File terhapus." : "Gagal menghapus file.",
                                Toast.LENGTH_SHORT).show();
                    }
                })
                .setNegativeButton("BATAL", null)
                .show();
    }

    // ------------------------------------------------------------------
    // Download
    // ------------------------------------------------------------------

    private static void download(final Activity act, final Release r) {
        final File dir = apkDir(act);
        final File dest = r.localFile(dir);
        final ProgressDialog pd = new ProgressDialog(act);
        pd.setTitle("Mengunduh " + r.tag);
        pd.setMessage(r.assetName);
        pd.setProgressStyle(ProgressDialog.STYLE_HORIZONTAL);
        pd.setMax(100);
        pd.setCancelable(false);
        pd.show();
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    httpDownload(r.assetUrl, dest, pd, act);
                    act.runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            pd.dismiss();
                            Toast.makeText(act, "Unduhan selesai: " + dest.getName(),
                                    Toast.LENGTH_LONG).show();
                            String myHash = null;
                            try {
                                myHash = sha256File(new File(act.getApplicationInfo().sourceDir));
                            } catch (Throwable ignored) {
                            }
                            showRelease(act, r, myHash);
                        }
                    });
                } catch (final Exception e) {
                    act.runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            pd.dismiss();
                            if (dest.exists()) {
                                dest.delete();
                            }
                            error(act, "Unduhan gagal.\n\n" + e.getMessage());
                        }
                    });
                }
            }
        }).start();
    }

    // ------------------------------------------------------------------
    // Install (root pm install; -r keeps data, -d permits rollback)
    // ------------------------------------------------------------------

    private static void confirmInstall(final Activity act, final Release r, final File f) {
        new AlertDialog.Builder(act)
                .setTitle("Pasang " + r.tag + "?")
                .setMessage("Aplikasi akan memasang versi ini menimpa yang sekarang "
                        + "(data & pengaturan tidak hilang). Selama pemasangan aplikasi "
                        + "akan tertutup oleh sistem — buka lagi setelahnya.")
                .setPositiveButton("PASANG", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        doInstall(act, r, f);
                    }
                })
                .setNegativeButton("BATAL", null)
                .show();
    }

    private static void doInstall(final Activity act, final Release r, final File f) {
        final ProgressDialog pd = new ProgressDialog(act);
        pd.setMessage("Memasang " + r.tag + "...");
        pd.setCancelable(false);
        pd.show();
        new Thread(new Runnable() {
            @Override
            public void run() {
                String out;
                int code;
                try {
                    Process p = Runtime.getRuntime().exec(new String[]{
                            "su", "-c", "pm install -r -d \"" + f.getAbsolutePath() + "\""});
                    StringBuilder sb = new StringBuilder();
                    BufferedReader br = new BufferedReader(new InputStreamReader(p.getInputStream()));
                    String line;
                    while ((line = br.readLine()) != null) {
                        sb.append(line).append('\n');
                    }
                    BufferedReader er = new BufferedReader(new InputStreamReader(p.getErrorStream()));
                    while ((line = er.readLine()) != null) {
                        sb.append(line).append('\n');
                    }
                    code = p.waitFor();
                    out = sb.toString().trim();
                } catch (Exception e) {
                    code = -1;
                    out = String.valueOf(e.getMessage());
                }
                final int fCode = code;
                final String fOut = out;
                act.runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        pd.dismiss();
                        if (fCode == 0 && (fOut.contains("Success") || fOut.length() == 0)) {
                            act.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                                    .edit().putString(KEY_TAG, r.tag).apply();
                            Toast.makeText(act, "Berhasil memasang " + r.tag,
                                    Toast.LENGTH_LONG).show();
                        } else {
                            error(act, "Pemasangan gagal (kode " + fCode + ").\n\n" + fOut
                                    + "\n\nPastikan izin root untuk aplikasi ini aktif di Magisk.");
                        }
                    }
                });
            }
        }).start();
    }

    // ------------------------------------------------------------------
    // HTTP + utils
    // ------------------------------------------------------------------

    private static String httpGet(String url) throws Exception {
        HttpURLConnection c = open(url);
        try {
            InputStream in = c.getInputStream();
            StringBuilder sb = new StringBuilder();
            BufferedReader br = new BufferedReader(new InputStreamReader(in, "UTF-8"));
            char[] buf = new char[4096];
            int n;
            while ((n = br.read(buf)) != -1) {
                sb.append(buf, 0, n);
            }
            return sb.toString();
        } finally {
            c.disconnect();
        }
    }

    private static HttpURLConnection open(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(20000);
        c.setReadTimeout(60000);
        c.setRequestProperty("User-Agent", "ModemCaps-NoExpire-Updater");
        c.setRequestProperty("Accept", "application/vnd.github+json");
        c.setInstanceFollowRedirects(true);
        return c;
    }

    private static void httpDownload(String url, File dest, final ProgressDialog pd,
                                     final Activity act) throws Exception {
        HttpURLConnection c = open(url);
        try {
            int status = c.getResponseCode();
            if (status >= 400) {
                throw new Exception("HTTP " + status);
            }
            final long total = c.getContentLength();
            InputStream in = c.getInputStream();
            FileOutputStream fos = new FileOutputStream(dest);
            try {
                byte[] buf = new byte[16384];
                long done = 0;
                int n;
                while ((n = in.read(buf)) != -1) {
                    fos.write(buf, 0, n);
                    done += n;
                    if (total > 0) {
                        final int pct = (int) (done * 100 / total);
                        act.runOnUiThread(new Runnable() {
                            @Override
                            public void run() {
                                pd.setProgress(pct);
                            }
                        });
                    }
                }
            } finally {
                fos.close();
                in.close();
            }
        } finally {
            c.disconnect();
        }
    }

    private static String sha256File(File f) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            FileInputStream fis = new FileInputStream(f);
            try {
                byte[] buf = new byte[65536];
                int n;
                while ((n = fis.read(buf)) != -1) {
                    md.update(buf, 0, n);
                }
            } finally {
                fis.close();
            }
            byte[] dig = md.digest();
            StringBuilder sb = new StringBuilder();
            for (byte b : dig) {
                sb.append(String.format("%02x", b & 0xff));
            }
            return sb.toString();
        } catch (Throwable t) {
            return null;
        }
    }

    private static String fmtSize(long bytes) {
        if (bytes <= 0) {
            return "-";
        }
        double mb = bytes / 1048576.0;
        return String.format(Locale.US, "%.2f MB", mb);
    }

    private static void error(Activity act, String msg) {
        new AlertDialog.Builder(act)
                .setTitle("Error")
                .setMessage(msg)
                .setPositiveButton("OK", null)
                .show();
    }

    // kept for potential UI date formatting needs
    private static String today() {
        return new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(new Date());
    }
}
