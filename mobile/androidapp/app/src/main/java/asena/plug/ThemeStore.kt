package asena.plug

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow

enum class ThemeMode { SYSTEM, DARK, LIGHT }

/** Aksan rengi: dark için c/c2, light için cLight (mockup paleti). */
data class Accent(val name: String, val c: Long, val c2: Long, val cLight: Long)

val ACCENTS = listOf(
    Accent("Amber", 0xFFF5B841, 0xFFFFD27A, 0xFFB67C14),
    Accent("Turkuaz", 0xFF39C7AE, 0xFF78ECD8, 0xFF1E9B86),
    Accent("Yeşil", 0xFF63D18F, 0xFF9CEBBC, 0xFF3FA96B),
    Accent("Mavi", 0xFF6E9BE8, 0xFFA6C4F5, 0xFF3F6FC0),
    Accent("Kızıl", 0xFFE5695B, 0xFFF49E94, 0xFFC24638),
    Accent("Mor", 0xFFB98BE8, 0xFFD7BAF7, 0xFF8B5FC0),
)

/** Tema tercihi (mod + aksan), kalıcı. Compose gözler; Ayarlar yazar. */
object ThemeStore {
    private const val PREF = "asena"
    private const val K_MODE = "theme_mode"
    private const val K_ACCENT = "accent"

    val mode = MutableStateFlow(ThemeMode.SYSTEM)
    val accentIndex = MutableStateFlow(0)

    fun load(ctx: Context) {
        val p = prefs(ctx)
        mode.value = runCatching { ThemeMode.valueOf(p.getString(K_MODE, "SYSTEM")!!) }.getOrDefault(ThemeMode.SYSTEM)
        accentIndex.value = p.getInt(K_ACCENT, 0).coerceIn(0, ACCENTS.lastIndex)
    }

    fun setMode(ctx: Context, m: ThemeMode) {
        mode.value = m
        prefs(ctx).edit().putString(K_MODE, m.name).apply()
    }

    fun setAccent(ctx: Context, i: Int) {
        accentIndex.value = i
        prefs(ctx).edit().putInt(K_ACCENT, i).apply()
    }

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
}
