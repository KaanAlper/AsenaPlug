package asena.plug

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow

/**
 * DomainStore — kullanıcının yasaklı-site listesi (kalıcı, SharedPreferences).
 * Şu an full-tünel bunu KULLANMIYOR; selective mode gelince (asenacore router) bu liste
 * "tünele girecek" alanları belirleyecek. Liste gerçek kullanıcı verisi — sahte değil.
 */
object DomainStore {
    private const val PREF = "asena"
    private const val KEY = "domains"

    val domains = MutableStateFlow<List<String>>(emptyList())

    fun load(ctx: Context) {
        val set = prefs(ctx).getStringSet(KEY, emptySet()) ?: emptySet()
        domains.value = set.sorted()
    }

    fun add(ctx: Context, raw: String) {
        val d = normalize(raw) ?: return
        if (domains.value.contains(d)) return
        commit(ctx, (domains.value + d).sorted())
    }

    /** .txt / URL listesi yapıştırma: satır/virgül/boşlukla ayır, hepsini normalize et. */
    fun addMany(ctx: Context, text: String) {
        val add = text.split('\n', ',', ' ', '\t').mapNotNull { normalize(it) }
        if (add.isEmpty()) return
        commit(ctx, (domains.value + add).distinct().sorted())
    }

    fun remove(ctx: Context, d: String) {
        commit(ctx, domains.value - d)
    }

    private fun commit(ctx: Context, list: List<String>) {
        domains.value = list
        prefs(ctx).edit().putStringSet(KEY, list.toSet()).apply()
    }

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    /** state.py normalize_domain ruhu: yorum/‘*.’/baş-son nokta temizle, en az bir nokta iste. */
    private fun normalize(raw: String): String? {
        var d = raw.substringBefore('#').trim().lowercase()
        d = d.removePrefix("https://").removePrefix("http://").substringBefore('/')
        d = d.removePrefix("*.").trim('.')
        if (d.isEmpty() || !d.contains('.') || d.contains(' ')) return null
        return d
    }
}

/** Alt-alanlar apex altında gruplanır (reddit.com ▾ img.reddit.com). */
data class DomainGroup(val apex: String, val members: List<String>)

private fun apexOf(d: String): String {
    val parts = d.split('.')
    return if (parts.size <= 2) d else parts.takeLast(2).joinToString(".")
}

fun groupDomains(list: List<String>): List<DomainGroup> =
    list.groupBy { apexOf(it) }
        .toSortedMap()
        .map { (apex, members) ->
            DomainGroup(apex, members.sortedWith(compareBy({ it != apex }, { it })))
        }

