package asena.plug

import kotlinx.coroutines.flow.MutableStateFlow

enum class TunnelStatus { OFF, CONNECTING, ON }

/** Süreç-içi paylaşılan tünel durumu: AsenaVpnService yazar, Compose UI gözler. */
object TunnelState {
    val status = MutableStateFlow(TunnelStatus.OFF)
}
