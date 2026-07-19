package asena.plug

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow

/** Uygulama davranış tercihleri, kalıcı. */
object SettingsStore {
    private const val PREF = "asena"
    private const val K_BOOT = "connect_on_boot"
    private const val K_SCOPE = "scope"       // "blacklist" | "everything"
    private const val K_HTTP2 = "use_http2"   // HTTP/2 (true) veya HTTP/3 (false)
    private const val K_BATTERY_ASKED = "battery_asked"  // pil muafiyeti bir kez soruldu mu

    val connectOnBoot = MutableStateFlow(false)
    val scope = MutableStateFlow("everything")   // varsayılan: full-tünel
    val useHttp2 = MutableStateFlow(true)        // TR'de HTTP/2 önerilir
    var batteryAsked = false                     // (reactive değil; tek seferlik prompt gate)
        private set

    fun load(ctx: Context) {
        connectOnBoot.value = prefs(ctx).getBoolean(K_BOOT, false)
        scope.value = prefs(ctx).getString(K_SCOPE, "everything") ?: "everything"
        useHttp2.value = prefs(ctx).getBoolean(K_HTTP2, true)
        batteryAsked = prefs(ctx).getBoolean(K_BATTERY_ASKED, false)
    }
    fun setBatteryAsked(ctx: Context, v: Boolean) {
        batteryAsked = v
        prefs(ctx).edit().putBoolean(K_BATTERY_ASKED, v).apply()
    }
    fun setUseHttp2(ctx: Context, v: Boolean) {
        useHttp2.value = v
        prefs(ctx).edit().putBoolean(K_HTTP2, v).apply()
    }
    fun setConnectOnBoot(ctx: Context, v: Boolean) {
        connectOnBoot.value = v
        prefs(ctx).edit().putBoolean(K_BOOT, v).apply()
    }
    fun setScope(ctx: Context, v: String) {
        scope.value = v
        prefs(ctx).edit().putString(K_SCOPE, v).apply()
    }
    val isBlacklist: Boolean get() = scope.value == "blacklist"

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
}
