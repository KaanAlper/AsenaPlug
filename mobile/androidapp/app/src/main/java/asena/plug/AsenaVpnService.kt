package asena.plug

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.IpPrefix
import android.net.VpnService
import android.os.Build
import android.os.ParcelFileDescriptor
import android.util.Log
import androidcore.Androidcore
import androidcore.ProtectFunc
import org.json.JSONArray
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
        const val ACTION_RECONNECT = "asena.plug.RECONNECT"
        private const val CH_ID = "asena_vpn"
        private const val NOTIF_ID = 1001
    }

    private var tun: ParcelFileDescriptor? = null
    private var selectiveMode = false

    /** Kalıcı foreground bildirimi -> sistem servisi arka planda/uykuda öldürmez. */
    private fun ensureForeground(text: String) {
        val nm = getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CH_ID) == null) {
            val ch = NotificationChannel(CH_ID, "AsenaPlug VPN", NotificationManager.IMPORTANCE_LOW)
            ch.setShowBadge(false)
            ch.description = "MASQUE tüneli bağlıyken kalıcı bildirim"
            nm.createNotificationChannel(ch)
        }
        val pi = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val notif: Notification = Notification.Builder(this, CH_ID)
            .setContentTitle("AsenaPlug")
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_stat_shield)
            .setOngoing(true)
            .setContentIntent(pi)
            .build()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIF_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIF_ID, notif)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> { stopTunnel(); return START_NOT_STICKY }
            ACTION_RECONNECT -> { reconnect(); return START_STICKY }
            else -> startTunnel()
        }
        return START_STICKY
    }

    private fun startTunnel() {
        if (Androidcore.isRunning() || Androidcore.isSelectiveRunning()) {
            TunnelState.status.value = TunnelStatus.ON
            return
        }
        TunnelState.status.value = TunnelStatus.CONNECTING
        ensureForeground("MASQUE el sıkışıyor…")   // servisi hemen foreground yap (öldürülme koruması)
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
            val useSelective = SettingsStore.isBlacklist
            val http2 = SettingsStore.useHttp2.value
            val blJson = if (useSelective) JSONArray(DomainStore.domains.value).toString() else "[]"

            Thread {
                try {
                    if (useSelective) {
                        // selective: TCP blacklist IP->tünel, gerisi direkt; DNS blacklist->tünelden temiz.
                        val protect = ProtectFunc { f -> protect(f) } // VpnService.protect -> direkt bypass
                        Androidcore.startSelective(fd.toLong(), cfg, blJson, http2, protect)
                        selectiveMode = true
                        Log.i(TAG, "selective çekirdek başladı (fd=$fd, ${DomainStore.domains.value.size} site, http2=$http2)")
                    } else {
                        Androidcore.start(fd.toLong(), cfg, http2)
                        selectiveMode = false
                        Log.i(TAG, "full-tünel çekirdek başladı (fd=$fd, http2=$http2)")
                    }
                    TunnelState.status.value = TunnelStatus.ON
                    val modeText = if (selectiveMode) "Seçili siteler tünelde" else "Tüm trafik korumada"
                    ensureForeground("Korumadasın · $modeText")
                } catch (e: Exception) {
                    Log.e(TAG, "çekirdek başlatma hata: ${e.message}", e)
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
        try { stopForeground(STOP_FOREGROUND_REMOVE) } catch (_: Exception) {}
        stopSelf()
    }

    /** Go çekirdeğini durdur + tun'u kapat (servis lifecycle'a dokunmadan). */
    private fun teardownCore() {
        try { if (selectiveMode) Androidcore.stopSelective() else Androidcore.stop() } catch (_: Exception) {}
        try { tun?.close() } catch (_: Exception) {}
        tun = null
        selectiveMode = false
    }

    private fun stopTunnel() {
        teardownCore()
        TunnelState.status.value = TunnelStatus.OFF
        try { stopForeground(STOP_FOREGROUND_REMOVE) } catch (_: Exception) {}
        stopSelf()
    }

    /**
     * Blacklist değişince yeniden bağlan: çekirdeği durdur, yeni TUN + yeni blacklist ile başlat.
     * (Blacklist snapshot'ı bağlanma anında alınıyor -> yeni site eklenince yeniden başlamalı.)
     */
    private fun reconnect() {
        if (!Androidcore.isRunning() && !Androidcore.isSelectiveRunning()) { startTunnel(); return }
        TunnelState.status.value = TunnelStatus.CONNECTING
        Thread {
            teardownCore()
            try { Thread.sleep(350) } catch (_: Exception) {}  // fd'nin serbest kalması için kısa nefes
            startTunnel()
        }.start()
    }

    override fun onRevoke() { stopTunnel(); super.onRevoke() }
    override fun onDestroy() { stopTunnel(); super.onDestroy() }
}
