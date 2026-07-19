package asena.plug

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import java.net.HttpURLConnection
import java.net.URL

/**
 * StatsStore — İndirme/Yükleme hızı SÜREKLİ değil, ELLE (⟳) ölçülür. fast.com tarzı:
 * ölçüm sırasında değer CANLI tırmanır (her ~150ms emit), sonra sonuca oturur.
 * Doğruluk: bağlantı/TLS/ilk-chunk (ramp-up) timer'a DAHİL EDİLMEZ; zaman-sınırlı (~6sn) pencere.
 * (Not: full-tünel'de uygulama kendi trafiği hariç tutulur -> ölçüm mevcut doğrudan hızı yansıtır;
 * selective mode gelince tünel-içi sayaçlara bağlanır.)
 */
object StatsStore {
    val downloadMbps = MutableStateFlow<Double?>(null)
    val uploadMbps = MutableStateFlow<Double?>(null)
    val measuring = MutableStateFlow(false)

    @Volatile private var running = false
    private const val WINDOW_NS = 6_000_000_000L      // ~6 sn ölçüm penceresi
    private const val EMIT_NS = 150_000_000L          // ~150ms'de bir canlı güncelle
    // Cloudflare Java UA'yı 403'lüyor -> tarayıcı UA
    private const val UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

    fun measure() {
        if (running) return
        running = true
        measuring.value = true
        downloadMbps.value = null
        uploadMbps.value = null
        Thread {
            // download + upload PARALEL (aynı anda ikisi de canlı tırmanır)
            val dt = Thread { runCatching { testDownload() }.onFailure { Log.e("Stats", "download: ${it.message}", it) } }
            val ut = Thread { runCatching { testUpload() }.onFailure { Log.e("Stats", "upload: ${it.message}", it) } }
            dt.start(); ut.start()
            dt.join(); ut.join()
            measuring.value = false
            running = false
        }.start()
    }

    private fun mbps(bytes: Long, nanos: Long): Double =
        if (nanos <= 0) 0.0 else bytes * 8.0 / (nanos / 1e9) / 1e6

    private fun testDownload() {
        // 50MB — Cloudflare __down max ~50MB (100MB'de 403). Pencere dolunca zaten erken dururuz.
        val c = URL("https://speed.cloudflare.com/__down?bytes=50000000").openConnection() as HttpURLConnection
        c.connectTimeout = 8000; c.readTimeout = 20000
        c.setRequestProperty("User-Agent", UA)
        val code = c.responseCode
        if (code != 200) {
            Log.e("Stats", "download responseCode=$code")
            runCatching { c.errorStream?.close() }
            return
        }
        c.inputStream.use { s ->
            val buf = ByteArray(65536)
            // ramp-up: ilk chunk'ı say(ma) — timer'ı ilk bayt GELDİKTEN sonra başlat
            if (s.read(buf) < 0) return
            val t0 = System.nanoTime()
            var total = 0L
            var lastEmit = t0
            while (true) {
                val n = s.read(buf); if (n < 0) break
                total += n
                val now = System.nanoTime()
                if (now - lastEmit >= EMIT_NS) {
                    downloadMbps.value = mbps(total, now - t0)   // CANLI
                    lastEmit = now
                }
                if (now - t0 >= WINDOW_NS) break
            }
            downloadMbps.value = mbps(total, System.nanoTime() - t0)  // sonuç
        }
    }

    private fun testUpload() {
        val c = URL("https://speed.cloudflare.com/__up").openConnection() as HttpURLConnection
        c.doOutput = true; c.requestMethod = "POST"
        c.setChunkedStreamingMode(65536)
        c.connectTimeout = 8000; c.readTimeout = 20000
        c.setRequestProperty("User-Agent", UA)
        val chunk = ByteArray(65536)
        val out = c.outputStream
        // ramp-up: birkaç chunk yaz, sonra timer başlat
        repeat(4) { out.write(chunk) }
        val t0 = System.nanoTime()
        var total = 0L
        var lastEmit = t0
        while (true) {
            out.write(chunk); total += chunk.size
            val now = System.nanoTime()
            if (now - lastEmit >= EMIT_NS) {
                uploadMbps.value = mbps(total, now - t0)   // CANLI
                lastEmit = now
            }
            if (now - t0 >= WINDOW_NS) break
        }
        val elapsed = System.nanoTime() - t0
        out.flush(); out.close()
        runCatching { c.inputStream.use { it.readBytes() } }
        uploadMbps.value = mbps(total, elapsed)   // sonuç
    }
}
