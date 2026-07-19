package asena.plug

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow

/** İlk açılış tutorial'ı bir kez gösterildi mi (kalıcı). Ayarlar'dan yeniden başlatılabilir. */
object TutorialStore {
    private const val PREF = "asena"
    private const val KEY = "tutorial_done"

    val done = MutableStateFlow(false)

    fun load(ctx: Context) {
        done.value = prefs(ctx).getBoolean(KEY, false)
    }
    fun setDone(ctx: Context, v: Boolean) {
        done.value = v
        prefs(ctx).edit().putBoolean(KEY, v).apply()
    }
    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
}
