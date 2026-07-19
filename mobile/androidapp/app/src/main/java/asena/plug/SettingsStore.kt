package asena.plug

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow

/** Uygulama davranış tercihleri (toggle'lar), kalıcı. */
object SettingsStore {
    private const val PREF = "asena"
    private const val K_BOOT = "connect_on_boot"

    val connectOnBoot = MutableStateFlow(false)

    fun load(ctx: Context) {
        connectOnBoot.value = prefs(ctx).getBoolean(K_BOOT, false)
    }
    fun setConnectOnBoot(ctx: Context, v: Boolean) {
        connectOnBoot.value = v
        prefs(ctx).edit().putBoolean(K_BOOT, v).apply()
    }
    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
}
