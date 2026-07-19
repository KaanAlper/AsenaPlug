package asena.plug

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow

/**
 * ConfigStore — kayıtlı WARP config JSON'u (Androidcore.register çıktısı), kalıcı.
 * Uygulama GÖMÜLÜ anahtar taşımaz: ilk açılışta kendi hesabını oluşturur, buraya kaydeder.
 * config==null => henüz kayıt yok (onboarding göster).
 */
object ConfigStore {
    private const val PREF = "asena"
    private const val KEY = "config_json"

    val config = MutableStateFlow<String?>(null)

    fun load(ctx: Context) {
        config.value = prefs(ctx).getString(KEY, null)
    }

    fun save(ctx: Context, json: String) {
        config.value = json
        prefs(ctx).edit().putString(KEY, json).apply()
    }

    /** Servis (aynı süreç) için: yüklü değilse yükle, sonra döndür. */
    fun getOrLoad(ctx: Context): String? {
        if (config.value == null) load(ctx)
        return config.value
    }

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
}
