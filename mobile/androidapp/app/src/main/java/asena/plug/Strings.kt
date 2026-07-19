package asena.plug

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow

enum class Lang { SYSTEM, TR, EN }

/** Tüm UI metinleri (derleme-güvenli). TR + EN. */
data class Strings(
    // genel / nav
    val brand: String, val navConnect: String, val navSites: String, val navSettings: String,
    // bağlan
    val protected: String, val connecting: String, val off: String,
    val subScope: String, val subHandshake: String, val subTapToConnect: String,
    val speed: String, val download: String, val upload: String, val session: String, val siteUnit: String, val noLeak: String,
    val exit: String, val cloudflare: String, val viaTunnel: String, val viaDirect: String,
    // onboarding
    val start: String, val onboardDesc: String, val creatingAccount: String,
    // siteler
    val sitesTitle: String, val searchHint: String, val importFile: String, val importHint: String,
    val emptyList: String, val noMatch: String, val inList: String,
    val addSiteTitle: String, val addSiteHint: String, val addSitePlaceholder: String, val add: String, val cancel: String,
    // ayarlar
    val settingsTitle: String, val transport: String, val scope: String, val theme: String, val color: String, val language: String,
    val system: String, val dark: String, val light: String, val onlyBlacklist: String, val everything: String,
    val connectOnBoot: String, val connectOnBootDesc: String, val version: String,
    val tutSkip: String, val tutTapHint: String, val tutReplay: String, val tutorial: List<Pair<String, String>>,
)

private val TR = Strings(
    brand = "Asena", navConnect = "Bağlan", navSites = "Siteler", navSettings = "Ayarlar",
    protected = "Korumadasın", connecting = "Bağlanıyor…", off = "Kapalı",
    subScope = "HTTP/2 · Her şey", subHandshake = "MASQUE el sıkışıyor", subTapToConnect = "Dokun ve bağlan",
    speed = "Hız", download = "İndirme", upload = "Yükleme", session = "Oturum", siteUnit = "site", noLeak = "sızıntı yok",
    exit = "Çıkış", cloudflare = "Cloudflare", viaTunnel = "tünel", viaDirect = "direkt",
    start = "Başla", onboardDesc = "Başlamak için anonim bir Cloudflare WARP hesabı oluşturulur. Kişisel bilgi gerekmez — sadece bir cihaz anahtarı.", creatingAccount = "Hesabın oluşturuluyor…",
    sitesTitle = "Siteler", searchHint = "alan ara…", importFile = "Listeden içe aktar", importHint = ".txt dosyası",
    emptyList = "Henüz site yok — + ile ekle", noMatch = "Eşleşme yok", inList = "listede",
    addSiteTitle = "Site ekle", addSiteHint = "Bir alan adı gir.", addSitePlaceholder = "ornek.com", add = "Ekle", cancel = "Vazgeç",
    settingsTitle = "Mod & Ayarlar", transport = "Taşıma", scope = "Kapsam", theme = "Tema", color = "Renk", language = "Dil",
    system = "Sistem", dark = "Koyu", light = "Açık", onlyBlacklist = "Sadece blacklist", everything = "Her şey",
    connectOnBoot = "Açılışta bağlan", connectOnBootDesc = "Telefon açılınca otomatik", version = "Sürüm 0.1 · PoC",
    tutSkip = "Atla", tutTapHint = "vurgulanan yere dokun", tutReplay = "Turu tekrar göster",
    tutorial = listOf(
        "Tünelleme yöntemi" to "HTTP/2 sağlam, HTTP/3 daha hızlı. Türkiye'de HTTP/2 önerilir.",
        "Kapsam" to "Her şey: tüm trafik tünelde. Sadece blacklist: yalnızca listendekiler.",
        "Site ekle" to "+ ile yasaklı alan adı ekle (örn. discord.com).",
        "Dosyadan içe aktar" to "Hazır bir .txt listesini buradan yükle.",
        "Hız testi" to "⟳ ile hızını ölç (bağlıyken tünel, kapalıyken düz hız).",
        "Bağlan" to "Dokun ve korumaya başla. Tur burada biter.",
    ),
)

private val EN = Strings(
    brand = "Asena", navConnect = "Connect", navSites = "Sites", navSettings = "Settings",
    protected = "Protected", connecting = "Connecting…", off = "Off",
    subScope = "HTTP/2 · Everything", subHandshake = "MASQUE handshaking", subTapToConnect = "Tap to connect",
    speed = "Speed", download = "Download", upload = "Upload", session = "Session", siteUnit = "sites", noLeak = "no leaks",
    exit = "Exit", cloudflare = "Cloudflare", viaTunnel = "tunnel", viaDirect = "direct",
    start = "Start", onboardDesc = "To begin, an anonymous Cloudflare WARP account is created. No personal info — just a device key.", creatingAccount = "Creating your account…",
    sitesTitle = "Sites", searchHint = "search domain…", importFile = "Import from list", importHint = ".txt file",
    emptyList = "No sites yet — add with +", noMatch = "No match", inList = "listed",
    addSiteTitle = "Add site", addSiteHint = "Enter a domain.", addSitePlaceholder = "example.com", add = "Add", cancel = "Cancel",
    settingsTitle = "Mode & Settings", transport = "Transport", scope = "Scope", theme = "Theme", color = "Color", language = "Language",
    system = "System", dark = "Dark", light = "Light", onlyBlacklist = "Blacklist only", everything = "Everything",
    connectOnBoot = "Connect on boot", connectOnBootDesc = "Auto-start when phone boots", version = "Version 0.1 · PoC",
    tutSkip = "Skip", tutTapHint = "tap the highlighted area", tutReplay = "Replay tour",
    tutorial = listOf(
        "Transport" to "HTTP/2 is robust, HTTP/3 is faster. HTTP/2 recommended in Turkey.",
        "Scope" to "Everything: all traffic tunneled. Blacklist only: just your list.",
        "Add site" to "Use + to add a blocked domain (e.g. discord.com).",
        "Import from file" to "Load a ready .txt list from here.",
        "Speed test" to "Measure speed with ⟳ (tunnel when on, direct when off).",
        "Connect" to "Tap and get protected. The tour ends here.",
    ),
)

fun stringsFor(lang: Lang, systemIsTr: Boolean): Strings = when (lang) {
    Lang.TR -> TR
    Lang.EN -> EN
    Lang.SYSTEM -> if (systemIsTr) TR else EN
}

object LangStore {
    private const val PREF = "asena"
    private const val KEY = "lang"
    val lang = MutableStateFlow(Lang.SYSTEM)

    fun load(ctx: Context) {
        lang.value = runCatching { Lang.valueOf(prefs(ctx).getString(KEY, "SYSTEM")!!) }.getOrDefault(Lang.SYSTEM)
    }
    fun set(ctx: Context, l: Lang) {
        lang.value = l
        prefs(ctx).edit().putString(KEY, l.name).apply()
    }
    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
}
