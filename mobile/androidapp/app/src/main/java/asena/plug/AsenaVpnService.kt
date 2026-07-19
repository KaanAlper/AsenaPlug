package asena.plug

import android.content.Intent
import android.net.VpnService
import android.os.ParcelFileDescriptor
import android.util.Log
import androidcore.Androidcore

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
            val builder = Builder()
                .setSession("AsenaPlug")
                .setMtu(1280)
                .addAddress("172.16.0.2", 32)
                .addRoute("0.0.0.0", 0)
                .addDnsServer("1.1.1.1")
                .addDnsServer("1.0.0.1")
            try { builder.addDisallowedApplication(packageName) } catch (e: Exception) {
                Log.w(TAG, "disallow self başarısız: ${e.message}")
            }

            val cfg = ConfigStore.getOrLoad(this)
            if (cfg == null) {
                Log.e(TAG, "config yok — önce kayıt gerekli")
                fail()
                return
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
