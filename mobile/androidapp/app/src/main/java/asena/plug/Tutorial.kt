package asena.plug

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.boundsInRoot
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Tutorial hedeflerinin ekran koordinatlarını toplar (vurgulanacak öğeler kendini bildirir). */
class TutorialController {
    val targets = mutableStateMapOf<String, Rect>()
}

val LocalTutorial = staticCompositionLocalOf<TutorialController?> { null }

/** Vurgulanacak öğeye eklenir: konumunu tutorial'a bildirir. */
@Composable
fun Modifier.tutorialTarget(key: String): Modifier {
    val ctrl = LocalTutorial.current ?: return this
    return this.onGloballyPositioned { ctrl.targets[key] = it.boundsInRoot() }
}

/** (sekme, hedefKey) — sıra: Ayarlar(taşıma,kapsam) -> Siteler(ekle,içe-aktar) -> Bağlan(hız,orb). */
val TUTORIAL_STEPS = listOf(
    2 to "transport",
    2 to "scope",
    1 to "fab",
    1 to "import",
    0 to "speed",
    0 to "orb",
)

/**
 * Spotlight overlay (animasyonlu): karartır, hedefi açık bırakır + ring, açıklama kartı KAYARAK geçer,
 * spotlight yumuşak kayar. Son adım: buton YOK — sadece gerçek Bağlan (orb) tuşuna dokununca tamamlanır.
 */
@Composable
fun TutorialOverlay(
    target: Rect?, steps: List<Pair<String, String>>, stepIndex: Int,
    skipLabel: String, tapHint: String, p: Palette, onNext: () -> Unit, onSkip: () -> Unit
) {
    val density = LocalDensity.current
    val padPx = with(density) { 10.dp.toPx() }
    val stepCount = steps.size
    val isLast = stepIndex == stepCount - 1

    // hedef null olabiliyor (sekme geçişinde 1 kare) -> son geçerli hedefi tut. Highlight ANLIK
    // (animasyonsuz) -> her-kare recompose yok -> fps drop yok. Sadece info box slide olur.
    var lastRect by remember { mutableStateOf<Rect?>(null) }
    LaunchedEffect(target) { if (target != null) lastRect = target }
    val shown = target ?: lastRect

    BoxWithConstraints(Modifier.fillMaxSize()) {
        val hPx = with(density) { maxHeight.toPx() }

        Canvas(Modifier.fillMaxSize()) {
            val dim = Color.Black.copy(alpha = 0.76f)
            if (shown == null) {
                drawRect(dim)
            } else {
                val l = (shown.left - padPx).coerceAtLeast(0f)
                val tp = (shown.top - padPx).coerceAtLeast(0f)
                val r = (shown.right + padPx).coerceAtMost(size.width)
                val b = (shown.bottom + padPx).coerceAtMost(size.height)
                drawRect(dim, Offset(0f, 0f), Size(size.width, tp))
                drawRect(dim, Offset(0f, b), Size(size.width, size.height - b))
                drawRect(dim, Offset(0f, tp), Size(l, b - tp))
                drawRect(dim, Offset(r, tp), Size(size.width - r, b - tp))
                drawRoundRect(
                    color = p.accent, topLeft = Offset(l, tp), size = Size(r - l, b - tp),
                    cornerRadius = CornerRadius(18f, 18f), style = Stroke(width = 3.5f)
                )
            }
        }

        // tap-catcher (caption'ın ALTINDA): GERÇEK hedefe dokununca ilerle (animasyonlu değil, kesin konum)
        Box(Modifier.fillMaxSize().pointerInput(target, stepIndex) {
            detectTapGestures { o ->
                val t = target
                if (t != null &&
                    o.x in (t.left - padPx)..(t.right + padPx) &&
                    o.y in (t.top - padPx)..(t.bottom + padPx)
                ) onNext()
            }
        })

        // açıklama kartı — hedefin altına/üstüne, YUMUŞAK kayar (animasyonlu Y)
        val below = shown == null || (shown.top + shown.bottom) / 2f < hPx * 0.52f
        val targetY = if (shown == null) hPx * 0.5f
        else if (below) shown.bottom + padPx + with(density) { 18.dp.toPx() }
        else (shown.top - padPx - with(density) { 210.dp.toPx() }).coerceAtLeast(with(density) { 60.dp.toPx() })

        Column(
            Modifier
                .offset { IntOffset(0, targetY.toInt()) }
                .padding(horizontal = 22.dp)
                .clip(RoundedCornerShape(18.dp))
                .background(p.surface)
                .border(1.dp, p.accent.copy(alpha = .35f), RoundedCornerShape(18.dp))
                .padding(18.dp)
        ) {
            // metin: adım değişince SLIDE + FADE
            AnimatedContent(
                targetState = stepIndex,
                transitionSpec = {
                    // slide DEĞİL: fade + hafif pop (scale)
                    (fadeIn(tween(300)) + scaleIn(tween(300), initialScale = 0.92f)) togetherWith
                        (fadeOut(tween(160)) + scaleOut(tween(160), targetScale = 0.96f))
                },
                label = "tutText"
            ) { si ->
                val (title, desc) = steps.getOrElse(si) { "" to "" }
                Column {
                    Text("${si + 1}/$stepCount", color = p.accentText, fontFamily = Jet, fontSize = 11.sp)
                    Spacer(Modifier.height(6.dp))
                    Text(title, color = p.text, fontFamily = Sora, fontSize = 18.sp, fontWeight = FontWeight.ExtraBold)
                    Spacer(Modifier.height(6.dp))
                    Text(desc, color = p.muted, fontFamily = Sora, fontSize = 14.sp)
                }
            }

            Spacer(Modifier.height(14.dp))
            if (isLast) {
                // son adım: buton YOK — sadece orb'a dokunulmalı
                Text(tapHint, color = p.accentText, fontFamily = Jet, fontSize = 12.sp)
            } else {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(skipLabel, color = p.faint, fontFamily = Jet, fontSize = 12.sp,
                        modifier = Modifier.clip(RoundedCornerShape(8.dp)).clickable { onSkip() }.padding(8.dp))
                    Spacer(Modifier.weight(1f))
                    Text(tapHint, color = p.faint, fontFamily = Jet, fontSize = 10.sp)
                    Spacer(Modifier.width(12.dp))
                    Box(
                        Modifier.clip(RoundedCornerShape(11.dp)).background(p.accent)
                            .clickable { onNext() }.padding(horizontal = 18.dp, vertical = 9.dp)
                    ) { Text("→", color = p.onAccent, fontFamily = Sora, fontSize = 15.sp, fontWeight = FontWeight.Black) }
                }
            }
        }
    }
}
