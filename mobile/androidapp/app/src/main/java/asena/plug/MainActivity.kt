package asena.plug

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.net.VpnService
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat
import androidcore.Androidcore
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin

/* ---- Dinamik palet: tema (koyu/açık) + aksan ---- */
data class Palette(
    val bg: Color, val surface: Color, val surface2: Color, val line: Color,
    val text: Color, val muted: Color, val faint: Color,
    val accent: Color, val accent2: Color, val accentText: Color, val onAccent: Color,
    val good: Color, val steel: Color,
)

private fun darkPalette(a: Accent) = Palette(
    bg = Color(0xFF0E1117), surface = Color(0xFF161B25), surface2 = Color(0xFF1E2531), line = Color(0xFF2A3240),
    text = Color(0xFFE9ECF3), muted = Color(0xFF8B94A6), faint = Color(0xFF5A6476),
    accent = Color(a.c), accent2 = Color(a.c2), accentText = Color(a.c), onAccent = Color(0xFF120C02),
    good = Color(0xFF63D18F), steel = Color(0xFF6E93C6),
)

private fun lightPalette(a: Accent) = Palette(
    bg = Color(0xFFEAEDF3), surface = Color(0xFFFFFFFF), surface2 = Color(0xFFF2F5FA), line = Color(0xFFDCE1EA),
    text = Color(0xFF151A23), muted = Color(0xFF5A6476), faint = Color(0xFF8A94A4),
    accent = Color(a.c), accent2 = Color(a.c2), accentText = Color(a.cLight), onAccent = Color(0xFF120C02),
    good = Color(0xFF3FA96B), steel = Color(0xFF4A72B0),
)

private val LocalPalette = staticCompositionLocalOf { darkPalette(ACCENTS[0]) }
private val LocalStrings = staticCompositionLocalOf { stringsFor(Lang.TR, true) }
private val coreInk = Color(0xFF120C02)
private val mono = Jet   // JetBrains Mono (teknik etiketler)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        DomainStore.load(this)
        ThemeStore.load(this)
        ConfigStore.load(this)
        LangStore.load(this)
        SettingsStore.load(this)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        setContent { AsenaApp() }
    }
}

private fun startVpn(ctx: Context) {
    TunnelState.status.value = TunnelStatus.CONNECTING
    ctx.startService(Intent(ctx, AsenaVpnService::class.java))
}
private fun stopVpn(ctx: Context) {
    ctx.startService(Intent(ctx, AsenaVpnService::class.java).setAction(AsenaVpnService.ACTION_STOP))
}

@Composable
fun AsenaApp() {
    val ctx = LocalContext.current
    val mode by ThemeStore.mode.collectAsState()
    val accentIdx by ThemeStore.accentIndex.collectAsState()
    val lang by LangStore.lang.collectAsState()
    val dark = when (mode) {
        ThemeMode.SYSTEM -> isSystemInDarkTheme()
        ThemeMode.DARK -> true
        ThemeMode.LIGHT -> false
    }
    val palette = if (dark) darkPalette(ACCENTS[accentIdx]) else lightPalette(ACCENTS[accentIdx])
    val systemIsTr = LocalConfiguration.current.locales[0].language == "tr"
    val strings = stringsFor(lang, systemIsTr)

    LaunchedEffect(dark) {
        (ctx as? Activity)?.let {
            WindowCompat.getInsetsController(it.window, it.window.decorView).isAppearanceLightStatusBars = !dark
        }
    }

    CompositionLocalProvider(
        LocalPalette provides palette,
        LocalStrings provides strings,
        LocalTextStyle provides TextStyle(fontFamily = Sora)   // varsayılan yazı tipi: Sora
    ) {
        AppContent()
    }
}

@Composable
private fun AppContent() {
    val p = LocalPalette.current
    val s = LocalStrings.current
    val status by TunnelState.status.collectAsState()
    val cfg by ConfigStore.config.collectAsState()
    var tab by remember { mutableIntStateOf(0) }
    var registering by remember { mutableStateOf(false) }
    var regError by remember { mutableStateOf<String?>(null) }
    val ctx = LocalContext.current

    val doRegister: () -> Unit = {
        registering = true; regError = null
        Thread {
            try {
                ConfigStore.save(ctx, Androidcore.register("AsenaPlug"))
            } catch (e: Exception) {
                regError = e.message ?: "hata"
            }
            registering = false
        }.start()
    }

    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { res -> if (res.resultCode == Activity.RESULT_OK) startVpn(ctx) }

    val toggle: () -> Unit = {
        when (status) {
            TunnelStatus.ON, TunnelStatus.CONNECTING -> stopVpn(ctx)
            TunnelStatus.OFF -> {
                val prep = VpnService.prepare(ctx)
                if (prep != null) launcher.launch(prep) else startVpn(ctx)
            }
        }
    }

    Box(
        Modifier.fillMaxSize().background(p.bg).drawBehind {
            drawRect(Brush.radialGradient(listOf(p.accent.copy(alpha = .13f), Color.Transparent),
                center = Offset(size.width * .82f, -size.height * .04f), radius = size.width * .95f))
            drawRect(Brush.radialGradient(listOf(p.steel.copy(alpha = .07f), Color.Transparent),
                center = Offset(size.width * .06f, size.height * .05f), radius = size.width * .7f))
        }
    ) {
        Column(Modifier.fillMaxSize().systemBarsPadding()) {
            AppBar()
            Box(Modifier.weight(1f).fillMaxWidth()) {
                when (tab) {
                    0 -> if (cfg == null) OnboardingScreen(registering, regError, doRegister)
                    else ConnectScreen(status, toggle)
                    1 -> SitesScreen()
                    else -> SettingsScreen()
                }
            }
            BottomNav(tab) { tab = it }
        }
    }
}

@Composable
private fun AppBar() {
    val p = LocalPalette.current
    Row(
        Modifier.fillMaxWidth().padding(start = 22.dp, end = 20.dp, top = 16.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text("AsenaPlug", color = p.text, fontSize = 21.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = (-0.3).sp)
    }
}

/* ---------- Bağlan ---------- */

@Composable
private fun ConnectScreen(status: TunnelStatus, onToggle: () -> Unit) {
    val p = LocalPalette.current
    val s = LocalStrings.current
    Column(
        Modifier.fillMaxSize().padding(horizontal = 26.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Spacer(Modifier.height(34.dp))
        Orb(status, onToggle)
        Spacer(Modifier.height(24.dp))

        val (big, sub, bigColor) = when (status) {
            TunnelStatus.ON -> Triple(s.protected, s.subScope, p.text)
            TunnelStatus.CONNECTING -> Triple(s.connecting, s.subHandshake, p.text)
            TunnelStatus.OFF -> Triple(s.off, s.subTapToConnect, p.muted)
        }
        Text(big, color = bigColor, fontSize = 25.sp, fontWeight = FontWeight.ExtraBold)
        Spacer(Modifier.height(5.dp))
        Text(sub, color = p.accentText, fontFamily = mono, fontSize = 13.sp)

        Spacer(Modifier.height(32.dp))
        InfoCard(status)
        Spacer(Modifier.weight(1f))
    }
}

@Composable
private fun Orb(status: TunnelStatus, onToggle: () -> Unit) {
    val p = LocalPalette.current
    val on = status == TunnelStatus.ON
    Box(contentAlignment = Alignment.Center, modifier = Modifier.size(232.dp)) {
        // BAĞLIYKEN: dışa büyüyen sonar halkalar (animasyon). KAPALIYKEN: sabit halkalar (animasyon yok).
        if (on) {
            Ripples(232.dp, p.accent, 1f)
        } else {
            Box(Modifier.size(200.dp).border(1.5.dp, p.line, CircleShape))
            Box(Modifier.size(176.dp).border(1.dp, p.line.copy(alpha = .6f), CircleShape))
        }
        // bloom (çekirdek arkası ışıma)
        Box(Modifier.size(200.dp).clip(CircleShape).background(
            Brush.radialGradient(
                if (on) listOf(p.accent.copy(alpha = .22f), p.accent.copy(alpha = .06f), Color.Transparent)
                else listOf(p.text.copy(alpha = .02f), Color.Transparent)
            )
        ))
        if (status == TunnelStatus.CONNECTING) {
            CircularProgressIndicator(Modifier.size(164.dp), color = p.accent, strokeWidth = 2.dp)
        }
        // çekirdek
        val core = if (on) Brush.radialGradient(listOf(p.accent2, p.accent, p.accent))
        else Brush.radialGradient(listOf(p.surface2, p.surface))
        Box(
            Modifier.size(138.dp).clip(CircleShape).background(core)
                .border(1.dp, if (on) Color.Transparent else p.line, CircleShape)
                .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) { onToggle() },
            contentAlignment = Alignment.Center
        ) {
            Image(painterResource(R.drawable.wolf), null, Modifier.size(70.dp),
                colorFilter = ColorFilter.tint(if (on) coreInk else p.muted))
        }
    }
}

@Composable
private fun Ripples(diameter: Dp, color: Color, intensity: Float) {
    val t = rememberInfiniteTransition(label = "ripple")
    val dur = 3200
    val count = 3
    for (i in 0 until count) {
        val prog by t.animateFloat(
            0f, 1f,
            infiniteRepeatable(tween(dur, easing = LinearEasing), initialStartOffset = StartOffset(i * dur / count)),
            label = "r$i"
        )
        Box(
            Modifier.size(diameter)
                .scale(0.60f + prog * 0.42f)   // içten dışa kademeli büyür
                .alpha((1f - prog) * 0.5f * intensity)
                .border(1.5.dp, color, CircleShape)
        )
    }
}

@Composable
private fun InfoCard(status: TunnelStatus) {
    val p = LocalPalette.current
    val s = LocalStrings.current
    val dl by StatsStore.downloadMbps.collectAsState()
    val ul by StatsStore.uploadMbps.collectAsState()
    val measuring by StatsStore.measuring.collectAsState()

    // ⟳ ölçerken döner
    val t = rememberInfiniteTransition(label = "spin")
    val spin by t.animateFloat(0f, 360f, infiniteRepeatable(tween(900, easing = LinearEasing)), label = "s")

    fun fmt(v: Double?) = v?.let { String.format(java.util.Locale.US, "%.1f", it) } ?: "—"

    // ölçüm bitince Knight Rider parlaması tetikle
    var sweepKey by remember { mutableIntStateOf(0) }
    LaunchedEffect(measuring) {
        if (!measuring && (dl != null || ul != null)) sweepKey++
    }

    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(20.dp)).background(p.surface)
            .border(1.dp, p.line, RoundedCornerShape(20.dp)).padding(horizontal = 18.dp, vertical = 4.dp)
    ) {
        // başlık: HIZ + ⟳ (ölçerken döner)
        Row(
            Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 2.dp),
            horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically
        ) {
            Text(s.speed.uppercase(), color = p.faint, fontFamily = mono, fontSize = 11.sp, letterSpacing = 1.5.sp)
            Icon(
                Icons.Filled.Refresh, "yenile",
                Modifier.size(19.dp).rotate(if (measuring) spin else 0f)
                    .clickable(enabled = !measuring) { StatsStore.measure() },
                tint = p.accentText
            )
        }
        StatRow(s.download, fmt(dl), "Mb/s", p.good, sweepKey)
        Divider()
        StatRow(s.upload, fmt(ul), "Mb/s", p.steel, sweepKey)
        Divider()
        SessionRow()
    }
}

@Composable
private fun StatRow(label: String, value: String, unit: String, valueColor: Color, sweepKey: Int) {
    val p = LocalPalette.current
    Row(
        Modifier.fillMaxWidth().padding(vertical = 13.dp),
        horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically
    ) {
        Text(label.uppercase(), color = p.faint, fontFamily = mono, fontSize = 11.sp, letterSpacing = 1.5.sp)
        Row(verticalAlignment = Alignment.Bottom) {
            Text(value, color = valueColor, fontFamily = mono, fontSize = 17.sp, fontWeight = FontWeight.Bold,
                modifier = Modifier.knightSweep(sweepKey))
            Text(" $unit", color = p.muted, fontFamily = mono, fontSize = 11.sp)
        }
    }
}

/** Knight Rider: ölçüm bitince sayının üzerinden soldan sağa beyaz parlama geçer. */
@Composable
private fun Modifier.knightSweep(trigger: Int): Modifier {
    val anim = remember { Animatable(1.8f) }   // 1.8 = sağda, görünmez (boşta)
    LaunchedEffect(trigger) {
        if (trigger > 0) { anim.snapTo(-0.4f); anim.animateTo(1.8f, tween(780, easing = FastOutSlowInEasing)) }
    }
    return drawWithContent {
        drawContent()
        val w = size.width
        val band = w * 0.85f
        val cx = anim.value * w
        drawRect(
            brush = Brush.horizontalGradient(
                0.0f to Color.Transparent,
                0.44f to Color.Transparent,
                0.5f to Color.White.copy(alpha = 0.95f),
                0.56f to Color.Transparent,
                1.0f to Color.Transparent,
                startX = cx - band, endX = cx + band
            ),
            blendMode = BlendMode.SrcAtop
        )
    }
}

@Composable
private fun SessionRow() {
    val p = LocalPalette.current
    val s = LocalStrings.current
    val domains by DomainStore.domains.collectAsState()
    val status by TunnelState.status.collectAsState()
    Row(
        Modifier.fillMaxWidth().padding(vertical = 13.dp),
        horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically
    ) {
        Text(s.session.uppercase(), color = p.faint, fontFamily = mono, fontSize = 11.sp, letterSpacing = 1.5.sp)
        Row {
            Text("${domains.size} ${s.siteUnit}", color = p.text, fontFamily = mono, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            if (status == TunnelStatus.ON) {
                Text(" · ${s.cloudflare}", color = p.good, fontFamily = mono, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun Divider() {
    val p = LocalPalette.current
    Box(Modifier.fillMaxWidth().height(1.dp).background(p.line))
}

/* ---------- Onboarding ---------- */

@Composable
private fun OnboardingScreen(registering: Boolean, error: String?, onRegister: () -> Unit) {
    val p = LocalPalette.current
    val s = LocalStrings.current
    Column(
        Modifier.fillMaxSize().padding(horizontal = 36.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center
    ) {
        Box(
            Modifier.size(140.dp).clip(CircleShape)
                .background(Brush.radialGradient(listOf(p.accent.copy(alpha = .22f), Color.Transparent))),
            contentAlignment = Alignment.Center
        ) { Image(painterResource(R.drawable.wolf), null, Modifier.size(76.dp), colorFilter = ColorFilter.tint(p.accentText)) }
        Spacer(Modifier.height(26.dp))
        Text("AsenaPlug", color = p.text, fontSize = 30.sp, fontWeight = FontWeight.ExtraBold)
        Spacer(Modifier.height(12.dp))
        Text(s.onboardDesc, color = p.muted, fontSize = 15.sp, textAlign = TextAlign.Center)
        Spacer(Modifier.height(34.dp))
        if (registering) {
            CircularProgressIndicator(Modifier.size(36.dp), color = p.accent, strokeWidth = 3.dp)
            Spacer(Modifier.height(16.dp))
            Text(s.creatingAccount, color = p.accentText, fontFamily = mono, fontSize = 13.sp)
        } else {
            Box(
                Modifier.clip(RoundedCornerShape(15.dp)).background(p.accent)
                    .clickable { onRegister() }.padding(horizontal = 52.dp, vertical = 16.dp)
            ) { Text(s.start, color = p.onAccent, fontSize = 16.sp, fontWeight = FontWeight.Black) }
            if (error != null) {
                Spacer(Modifier.height(16.dp))
                Text(error, color = Color(0xFFE5695B), fontFamily = mono, fontSize = 12.sp, textAlign = TextAlign.Center)
            }
        }
    }
}

/* ---------- Siteler ---------- */

@Composable
private fun SitesScreen() {
    val p = LocalPalette.current
    val s = LocalStrings.current
    val ctx = LocalContext.current
    val domains by DomainStore.domains.collectAsState()
    var query by remember { mutableStateOf("") }
    var showAdd by remember { mutableStateOf(false) }
    val expanded = remember { mutableStateMapOf<String, Boolean>() }

    // dosya seç -> içe aktar
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            runCatching {
                ctx.contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }
            }.getOrNull()?.let { DomainStore.addMany(ctx, it) }
        }
    }

    val q = query.trim().lowercase()
    val filtered = if (q.isEmpty()) domains else domains.filter { it.contains(q) }
    val groups = remember(filtered) { groupDomains(filtered) }

    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().padding(horizontal = 20.dp)) {
            Spacer(Modifier.height(10.dp))
            SearchField(query) { query = it }
            Spacer(Modifier.height(11.dp))

            // içe aktar = DOSYA SEÇ
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(p.accent.copy(alpha = .13f))
                    .border(1.dp, p.accent.copy(alpha = .34f), RoundedCornerShape(14.dp))
                    .clickable { picker.launch(arrayOf("text/plain", "text/*", "application/octet-stream")) }
                    .padding(horizontal = 14.dp, vertical = 13.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(Icons.Filled.Add, null, Modifier.size(17.dp), tint = p.accentText)
                Spacer(Modifier.width(9.dp))
                Text(s.importFile, color = p.accentText, fontFamily = mono, fontSize = 13.sp)
                Spacer(Modifier.weight(1f))
                Text(s.importHint, color = p.muted, fontFamily = mono, fontSize = 10.sp)
            }
            Spacer(Modifier.height(6.dp))

            if (groups.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(if (domains.isEmpty()) s.emptyList else s.noMatch, color = p.faint, fontFamily = mono, fontSize = 13.sp)
                }
            } else {
                LazyColumn(Modifier.fillMaxSize()) {
                    groups.forEach { g ->
                        val subs = g.members.filter { it != g.apex }
                        val apexIsMember = g.members.contains(g.apex)
                        if (subs.isEmpty()) {
                            item(key = g.apex) { SiteRow(g.apex, false) { DomainStore.remove(ctx, g.apex) } }
                        } else {
                            item(key = "grp:${g.apex}") {
                                GroupHeader(g.apex, subs.size, apexIsMember, expanded[g.apex] == true,
                                    onToggle = { expanded[g.apex] = !(expanded[g.apex] ?: false) },
                                    onDelete = { DomainStore.remove(ctx, g.apex) })
                            }
                            if (expanded[g.apex] == true) {
                                items(subs, key = { it }) { m -> SiteRow(m, true) { DomainStore.remove(ctx, m) } }
                            }
                        }
                    }
                    item { Spacer(Modifier.height(92.dp)) }
                }
            }
        }

        // FAB (+) = TEK site text girişi
        Box(
            Modifier.align(Alignment.BottomEnd).padding(20.dp).size(56.dp)
                .clip(RoundedCornerShape(18.dp)).background(p.accent).clickable { showAdd = true },
            contentAlignment = Alignment.Center
        ) { Icon(Icons.Filled.Add, null, Modifier.size(28.dp), tint = p.onAccent) }
    }

    if (showAdd) AddDialog(onDismiss = { showAdd = false }) { text ->
        DomainStore.add(ctx, text); showAdd = false
    }
}

@Composable
private fun GroupHeader(
    apex: String, subCount: Int, apexIsMember: Boolean, expanded: Boolean,
    onToggle: () -> Unit, onDelete: () -> Unit
) {
    val p = LocalPalette.current
    Row(
        Modifier.fillMaxWidth().clickable { onToggle() }.padding(vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(if (apexIsMember) p.accent else p.faint))
        Spacer(Modifier.width(12.dp))
        Text(apex, color = p.text, fontFamily = mono, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
        Box(Modifier.clip(RoundedCornerShape(7.dp)).background(p.accent.copy(alpha = .16f)).padding(horizontal = 8.dp, vertical = 3.dp)) {
            Text("+$subCount", color = p.accentText, fontFamily = mono, fontSize = 10.sp)
        }
        Spacer(Modifier.width(6.dp))
        Icon(Icons.Filled.KeyboardArrowDown, null, Modifier.size(20.dp).rotate(if (expanded) 180f else 0f), tint = p.muted)
        if (apexIsMember) {
            Spacer(Modifier.width(8.dp))
            Icon(Icons.Filled.Close, "sil", Modifier.size(16.dp).clickable { onDelete() }, tint = p.faint)
        }
    }
    Divider()
}

@Composable
private fun SiteRow(domain: String, indent: Boolean, onDelete: () -> Unit) {
    val p = LocalPalette.current
    val s = LocalStrings.current
    Row(
        Modifier.fillMaxWidth().padding(start = if (indent) 20.dp else 0.dp, top = 12.dp, bottom = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(Modifier.size(if (indent) 6.dp else 8.dp).clip(CircleShape).background(p.faint))
        Spacer(Modifier.width(12.dp))
        Text(domain, color = if (indent) p.muted else p.text, fontFamily = mono, fontSize = 13.sp, modifier = Modifier.weight(1f))
        Text(s.inList, color = p.muted, fontFamily = mono, fontSize = 10.sp, letterSpacing = 0.6.sp)
        Spacer(Modifier.width(12.dp))
        Icon(Icons.Filled.Close, "sil", Modifier.size(16.dp).clickable { onDelete() }, tint = p.faint)
    }
    Divider()
}

@Composable
private fun SearchField(value: String, onChange: (String) -> Unit) {
    val p = LocalPalette.current
    val s = LocalStrings.current
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(p.surface)
            .border(1.dp, p.line, RoundedCornerShape(14.dp)).padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(Icons.Filled.Search, null, Modifier.size(16.dp), tint = p.faint)
        Spacer(Modifier.width(9.dp))
        Box(Modifier.weight(1f)) {
            if (value.isEmpty()) Text(s.searchHint, color = p.faint, fontFamily = mono, fontSize = 13.sp)
            BasicTextField(
                value = value, onValueChange = onChange, singleLine = true,
                textStyle = TextStyle(color = p.text, fontFamily = mono, fontSize = 13.sp),
                cursorBrush = SolidColor(p.accent), modifier = Modifier.fillMaxWidth()
            )
        }
    }
}

@Composable
private fun AddDialog(onDismiss: () -> Unit, onAdd: (String) -> Unit) {
    val p = LocalPalette.current
    val s = LocalStrings.current
    var text by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = p.surface, titleContentColor = p.text, textContentColor = p.muted,
        title = { Text(s.addSiteTitle, fontWeight = FontWeight.ExtraBold) },
        text = {
            Column {
                Text(s.addSiteHint, color = p.muted, fontSize = 13.sp)
                Spacer(Modifier.height(12.dp))
                Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(p.surface2)
                        .border(1.dp, p.line, RoundedCornerShape(12.dp)).padding(horizontal = 13.dp, vertical = 13.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(Modifier.weight(1f)) {
                        if (text.isEmpty()) Text(s.addSitePlaceholder, color = p.faint, fontFamily = mono, fontSize = 14.sp)
                        BasicTextField(
                            value = text, onValueChange = { text = it }, singleLine = true,
                            textStyle = TextStyle(color = p.text, fontFamily = mono, fontSize = 14.sp),
                            cursorBrush = SolidColor(p.accent), modifier = Modifier.fillMaxWidth()
                        )
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = { onAdd(text) }) { Text(s.add, color = p.accentText, fontWeight = FontWeight.Bold) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(s.cancel, color = p.muted) } }
    )
}

/* ---------- Ayarlar ---------- */

@Composable
private fun SettingsScreen() {
    val p = LocalPalette.current
    val s = LocalStrings.current
    val ctx = LocalContext.current
    val mode by ThemeStore.mode.collectAsState()
    val accentIdx by ThemeStore.accentIndex.collectAsState()
    val lang by LangStore.lang.collectAsState()
    val boot by SettingsStore.connectOnBoot.collectAsState()
    val scroll = rememberScrollState()

    Column(Modifier.fillMaxSize()) {
        Column(Modifier.weight(1f).verticalScroll(scroll).padding(horizontal = 22.dp)) {
            Spacer(Modifier.height(18.dp))
            SegLabel(s.transport)
            Segmented(listOf("HTTP/2", "HTTP/3"), 0, null)
            Spacer(Modifier.height(18.dp))
            SegLabel(s.scope)
            Segmented(listOf(s.onlyBlacklist, s.everything), 1, null)

            Spacer(Modifier.height(18.dp))
            SegLabel(s.theme)
            Segmented(listOf(s.system, s.dark, s.light),
                when (mode) { ThemeMode.SYSTEM -> 0; ThemeMode.DARK -> 1; ThemeMode.LIGHT -> 2 }) { i ->
                ThemeStore.setMode(ctx, when (i) { 0 -> ThemeMode.SYSTEM; 1 -> ThemeMode.DARK; else -> ThemeMode.LIGHT })
            }

            Spacer(Modifier.height(18.dp))
            SegLabel(s.language)
            Segmented(listOf(s.system, "Türkçe", "English"),
                when (lang) { Lang.SYSTEM -> 0; Lang.TR -> 1; Lang.EN -> 2 }) { i ->
                LangStore.set(ctx, when (i) { 0 -> Lang.SYSTEM; 1 -> Lang.TR; else -> Lang.EN })
            }

            Spacer(Modifier.height(18.dp))
            SegLabel(s.color)
            Row(Modifier.fillMaxWidth().padding(top = 2.dp)) {
                ACCENTS.forEachIndexed { i, a ->
                    val sel = i == accentIdx
                    Box(
                        Modifier.padding(end = 14.dp).size(if (sel) 34.dp else 30.dp).clip(CircleShape).background(Color(a.c))
                            .border(if (sel) 2.dp else 0.dp, if (sel) p.text else Color.Transparent, CircleShape)
                            .clickable { ThemeStore.setAccent(ctx, i) }
                    )
                }
            }

            Spacer(Modifier.height(22.dp))
            ToggleRow(s.connectOnBoot, s.connectOnBootDesc, boot) { SettingsStore.setConnectOnBoot(ctx, it) }
            Spacer(Modifier.height(20.dp))
        }

        // en alta yapışık: sürüm + GitHub logosu (repo'yu açar)
        Row(
            Modifier.fillMaxWidth().padding(start = 22.dp, end = 22.dp, top = 6.dp, bottom = 12.dp),
            horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically
        ) {
            Text(s.version, color = p.faint, fontFamily = mono, fontSize = 11.sp)
            Icon(
                painterResource(R.drawable.github), "GitHub",
                Modifier.size(22.dp).clickable {
                    ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://github.com/KaanAlper/AsenaPlug")))
                },
                tint = p.muted
            )
        }
    }
}

@Composable
private fun SegLabel(t: String) {
    val p = LocalPalette.current
    Text(t.uppercase(), color = p.faint, fontFamily = mono, fontSize = 11.sp, letterSpacing = 1.5.sp)
    Spacer(Modifier.height(9.dp))
}

@Composable
private fun Segmented(items: List<String>, selected: Int, onSelect: ((Int) -> Unit)?) {
    val p = LocalPalette.current
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(13.dp)).background(p.surface2)
            .border(1.dp, p.line, RoundedCornerShape(13.dp)).padding(3.dp)
    ) {
        items.forEachIndexed { i, it ->
            val on = i == selected
            Box(
                Modifier.weight(1f).clip(RoundedCornerShape(10.dp)).background(if (on) p.accent else Color.Transparent)
                    .then(if (onSelect != null) Modifier.clickable { onSelect(i) } else Modifier)
                    .padding(vertical = 10.dp),
                contentAlignment = Alignment.Center
            ) {
                Text(it, color = if (on) p.onAccent else p.muted, fontFamily = mono, fontSize = 12.sp,
                    fontWeight = if (on) FontWeight.Bold else FontWeight.Medium)
            }
        }
    }
}

@Composable
private fun ToggleRow(title: String, desc: String, on: Boolean, onChange: (Boolean) -> Unit) {
    val p = LocalPalette.current
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, color = p.text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            Text(desc, color = p.muted, fontSize = 12.sp)
        }
        Box(
            Modifier.width(48.dp).height(28.dp).clip(RoundedCornerShape(999.dp))
                .background(if (on) p.accent.copy(alpha = .22f) else p.surface2)
                .border(1.dp, if (on) p.accent.copy(alpha = .5f) else p.line, RoundedCornerShape(999.dp))
                .clickable { onChange(!on) },
            contentAlignment = if (on) Alignment.CenterEnd else Alignment.CenterStart
        ) {
            Box(Modifier.padding(3.dp).size(22.dp).clip(CircleShape).background(if (on) p.accent else p.muted))
        }
    }
}

/* ---------- Alt nav ---------- */

@Composable
private fun BottomNav(selected: Int, onSelect: (Int) -> Unit) {
    val p = LocalPalette.current
    val s = LocalStrings.current
    Row(
        Modifier.fillMaxWidth().background(p.surface)
            .drawBehind { drawRect(p.line, size = Size(size.width, 1f)) }.padding(top = 1.dp)
    ) {
        NavItem(0, selected, s.navConnect, onSelect)
        NavItem(1, selected, s.navSites, onSelect)
        NavItem(2, selected, s.navSettings, onSelect)
    }
}

@Composable
private fun RowScope.NavItem(index: Int, selected: Int, label: String, onSelect: (Int) -> Unit) {
    val p = LocalPalette.current
    val on = index == selected
    val tint = if (on) p.accentText else p.faint
    Column(
        Modifier.weight(1f)
            .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) { onSelect(index) }
            .padding(top = 12.dp, bottom = 14.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        when (index) {
            0 -> Image(painterResource(R.drawable.wolf), null, Modifier.size(23.dp), colorFilter = ColorFilter.tint(tint))
            1 -> Icon(Icons.Filled.Menu, null, Modifier.size(23.dp), tint = tint)
            else -> Icon(Icons.Filled.Settings, null, Modifier.size(23.dp), tint = tint)
        }
        Spacer(Modifier.height(5.dp))
        Text(label, color = tint, fontFamily = mono, fontSize = 10.5.sp)
    }
}
