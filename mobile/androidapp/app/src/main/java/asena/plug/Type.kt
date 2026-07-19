package asena.plug

import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight

/** Sora — modern geometrik sans (başlık/gövde). */
val Sora = FontFamily(
    Font(R.font.sora_regular, FontWeight.Normal),
    Font(R.font.sora_semibold, FontWeight.SemiBold),
    Font(R.font.sora_bold, FontWeight.Bold),
    Font(R.font.sora_extrabold, FontWeight.ExtraBold),
)

/** JetBrains Mono — teknik etiketler (mockup mono kimliği). Bold ağırlığı VAR (seçili segment bold). */
val Jet = FontFamily(
    Font(R.font.jet_regular, FontWeight.Normal),
    Font(R.font.jet_medium, FontWeight.Medium),
    Font(R.font.jet_bold, FontWeight.Bold),
)
