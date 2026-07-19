package asena.plug

import kotlinx.coroutines.flow.MutableStateFlow
import java.net.HttpURLConnection
import java.net.URL

/**
 * StatsStore — İndirme/Yükleme hızı SÜREKLİ değil, ELLE (⟳) ölçülür. Cloudflare speed uçları ile
 * gerçek ölçüm. (Not: full-tünel'de uygulama kendi trafiği hariç tutulduğu için ölçüm mevcut
 * doğrudan hızı yansıtır; selective mode gelince tünel-içi sayaçlara bağlanacak.)
 */
object StatsStore {
    val downloadMbps = MutableStateFlow<Double?>(null)
    val uploadMbps = MutableStateFlow<Double?>(null)
    val measuring = MutableStateFlow(false)

    @Volatile private var running = false

    fun measure() {
        if (running) return
        running = true
        measuring.value = true
        Thread {
            runCatching { downloadMbps.value = testDownload() }
            runCatching { uploadMbps.value = testUpload() }
            measuring.value = false
            running = false
        }.start()
    }

    private fun testDownload(): Double {
        val bytes = 8_000_000L
        val c = URL("https://speed.cloudflare.com/__down?bytes=$bytes").openConnection() as HttpURLConnection
        c.connectTimeout = 8000; c.readTimeout = 20000
        val t0 = System.nanoTime()
        var total = 0L
        c.inputStream.use { s ->
            val buf = ByteArray(65536)
            while (true) { val n = s.read(buf); if (n < 0) break; total += n }
        }
        val secs = (System.nanoTime() - t0) / 1e9
        return total * 8.0 / secs / 1e6
    }

    private fun testUpload(): Double {
        val bytes = 4_000_000
        val c = URL("https://speed.cloudflare.com/__up").openConnection() as HttpURLConnection
        c.doOutput = true; c.requestMethod = "POST"
        c.setFixedLengthStreamingMode(bytes)
        c.connectTimeout = 8000; c.readTimeout = 20000
        val t0 = System.nanoTime()
        c.outputStream.use { it.write(ByteArray(bytes)); it.flush() }
        c.inputStream.use { it.readBytes() }
        val secs = (System.nanoTime() - t0) / 1e9
        return bytes * 8.0 / secs / 1e6
    }
}
