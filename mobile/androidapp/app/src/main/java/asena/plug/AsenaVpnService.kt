package asena.plug

import android.content.Intent
import android.net.IpPrefix
import android.net.VpnService
import android.os.Build
import android.os.ParcelFileDescriptor
import android.util.Log
import androidcore.Androidcore
import org.json.JSONObject
import java.net.InetAddress

/**
 * AsenaVpnService — full-tünel VpnService.
 *
 * VpnService TUN'unu kurar (172.16.0.2/32, 0.0.0.0/0 route), fd'yi usque çekirdeğine
 * (Androidcore.start) verir. TÜM IPv4 trafiği MASQUE tünelinden geçer.
 *
 * LOOP ÖNLEME: addDisallowedApplication(kendi paket) -> usque'nun Cloudflare'e giden bağlantısı
 * VPN'e geri girmez.  Durum: TunnelState.status (Compose UI gözler).
 */
class AsenaVpnService : VpnService() {

    companion object {
        private const val TAG = "AsenaVpn"
        const val ACTION_STOP = "asena.plug.STOP"
    }

    private var tun: ParcelFileDescriptor? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopTunnel()
            return START_NOT_STICKY
        }
        startTunnel()
        return START_STICKY
    }

    private fun startTunnel() {
        if (Androidcore.isRunning()) {
            TunnelState.status.value = TunnelStatus.ON
            return
        }
        TunnelState.status.value = TunnelStatus.CONNECTING
        try {
            val cfg = ConfigStore.getOrLoad(this)
            if (cfg == null) {
                Log.e(TAG, "config yok — önce kayıt gerekli")
                fail()
                return
            }

            val builder = Builder()
                .setSession("AsenaPlug")
                .setMtu(1280)
                .addAddress("172.16.0.2", 32)
                .addRoute("0.0.0.0", 0)
                .addDnsServer("1.1.1.1")
                .addDnsServer("1.0.0.1")

            // LOOP ÖNLEME: yalnızca Cloudflare endpoint IP'lerini tünel DIŞINDA tut. Böylece app'in
            // kalan trafiği (speed test dahil) tünelden geçer -> bağlıyken TÜNEL hızı ölçülür.
            // (Eski: addDisallowedApplication tüm app'i hariç tutuyordu -> hep düz hız.)
            val endpoints = endpointIps(cfg)
            if (Build.VERSION.SDK_INT >= 33) {
                for (ip in endpoints) {
                    try { builder.excludeRoute(IpPrefix(InetAddress.getByName(ip), 32)) }
                    catch (e: Exception) { Log.w(TAG, "excludeRoute $ip: ${e.message}") }
                }
            } else {
                // API < 33: excludeRoute yok -> tüm app'i hariç tut (eski cihazda düz hız ölçer)
                try { builder.addDisallowedApplication(packageName) } catch (_: Exception) {}
            }

            val pfd = builder.establish()
            if (pfd == null) {
                Log.e(TAG, "establish() null — VPN izni yok?")
                fail()
                return
            }
            tun = pfd

            val fd = pfd.detachFd()

            Thread {
                try {
                    Androidcore.start(fd.toLong(), cfg, true /*http2*/)
                    Log.i(TAG, "usque çekirdeği başladı (fd=$fd)")
                    TunnelState.status.value = TunnelStatus.ON
                } catch (e: Exception) {
                    Log.e(TAG, "Androidcore.start hata: ${e.message}", e)
                    fail()
                }
            }.start()
        } catch (e: Exception) {
            Log.e(TAG, "startTunnel hata: ${e.message}", e)
            fail()
        }
    }

    /** config JSON'dan Cloudflare endpoint IPv4'lerini çıkar (tünel dışında tutulacaklar). */
    private fun endpointIps(cfg: String): Set<String> {
        val out = linkedSetOf<String>()
        try {
            val j = JSONObject(cfg)
            for (k in listOf("endpoint_v4", "endpoint_h2_v4")) {
                val v = j.optString(k, "").trim()
                if (v.isNotEmpty() && v.contains(".")) out.add(v)
            }
        } catch (e: Exception) {
            Log.w(TAG, "endpointIps parse: ${e.message}")
        }
        if (out.isEmpty()) out.add("162.159.198.2") // fallback (varsayılan CF endpoint)
        return out
    }

    private fun fail() {
        try { tun?.close() } catch (_: Exception) {}
        tun = null
        TunnelState.status.value = TunnelStatus.OFF
        stopSelf()
    }

    private fun stopTunnel() {
        try { Androidcore.stop() } catch (_: Exception) {}
        try { tun?.close() } catch (_: Exception) {}
        tun = null
        TunnelState.status.value = TunnelStatus.OFF
        stopSelf()
    }

    override fun onRevoke() { stopTunnel(); super.onRevoke() }
    override fun onDestroy() { stopTunnel(); super.onDestroy() }
}
