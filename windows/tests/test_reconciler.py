"""Reconciler karar mantığı (AsenaTray._decide) — saf, yan etkisiz birim testleri.

Yeni tasarım: asena-on DECLARATIVE (mod değişince usque'yu kendi restart eder),
o yüzden 'yanlış modda bağlı' -> 'on' (off->on dansı YOK). _decide(goal, cur):
'done' | 'on' | 'off'. Issue-once mantığı reconcile'da _issued ile.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from asenaplug.tray import AsenaTray  # noqa: E402

decide = AsenaTray._decide

H2S = ("http2", "selective")
H3S = ("http3", "selective")
H2F = ("http2", "full")


def _st(transport, scope):
    return {"transport": transport, "scope": scope}


# ---- boşta / kesme ----
def test_goal_none_is_done():
    assert decide(None, None) == "done"
    assert decide(None, _st(*H2S)) == "done"


def test_off_when_disconnected_is_done():
    assert decide("off", None) == "done"


def test_off_when_connected_issues_off():
    assert decide("off", _st(*H2S)) == "off"


# ---- bağlan ----
def test_connect_from_disconnected_issues_on():
    assert decide(H2S, None) == "on"


def test_connect_reached_is_done():
    assert decide(H2S, _st(*H2S)) == "done"


# ---- mod değiştir: yanlış modda bağlı -> 'on' (off DEĞİL; asena-on restart eder) ----
def test_transport_switch_issues_on_not_off():
    assert decide(H3S, _st(*H2S)) == "on"


def test_scope_switch_issues_on_not_off():
    assert decide(H2F, _st(*H2S)) == "on"


def test_full_reached_is_done():
    assert decide(H2F, _st(*H2F)) == "done"


# ---- h3->h2 fallback kabulü (issued param) ----
def test_h3_requested_h2_running_not_yet_issued_switches():
    # Henüz komut vermedik (issued=None): h3 istendi, h2 çalışıyor -> switch uygula
    assert decide(H3S, _st(*H2S), None) == "on"


def test_h3_requested_h2_running_already_issued_is_fallback_done():
    # Bu hedefi zaten issue ettik: h2, asena-on'un bilinçli fallback'ı -> done (kabul)
    assert decide(H3S, _st(*H2S), issued=H3S) == "done"


def test_scope_mismatch_still_on_even_if_issued():
    # scope tutmuyorsa fallback kabulü YOK -> yeniden uygula (scope her zaman kesin)
    assert decide(H2F, _st(*H2S), issued=H2F) == "on"


def test_different_issued_goal_still_switches():
    # issued başka bir hedefse (eski), yine transport switch uygula
    assert decide(H3S, _st(*H2S), issued=H2S) == "on"


# ---- usque-watchdog backoff (saf) ----
step = AsenaTray._watchdog_step


def test_watchdog_connected_resets():
    # tünel ayakta -> ateşleme yok, backoff sıfırlanır
    assert step(True, True, False, 5, 8) == (False, 1, 1)


def test_watchdog_user_disconnected_resets():
    # kullanıcı bağlı olmak İSTEMİYOR -> watchdog susar, sıfırlanır
    assert step(False, False, False, 3, 4) == (False, 1, 1)


def test_watchdog_busy_waits():
    # reconcile/update sürüyor -> hiçbir şey yapma (mevcut deneme devam etsin)
    assert step(False, True, True, 2, 4) == (False, 2, 4)


def test_watchdog_counts_down():
    # düşük değilse geri say, henüz ateşleme
    assert step(False, True, False, 3, 4) == (False, 2, 4)


def test_watchdog_fires_and_doubles_backoff():
    # süre doldu -> ateşle, backoff ikiye katla, bir sonraki bekleme = yeni backoff
    assert step(False, True, False, 0, 4) == (True, 8, 8)


def test_watchdog_backoff_capped():
    # backoff tavanı geçmez (spam yok)
    assert step(False, True, False, 0, 20, cap=20) == (True, 20, 20)
