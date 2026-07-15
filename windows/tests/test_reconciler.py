"""Reconciler karar mantığı (AsenaTray._decide) — saf, yan etkisiz birim testleri.

_decide, mode-switch thrashing'i önleyen level-triggered reconcile döngüsünün
çekirdeğidir: (hedef, mevcut durum, son faz) -> 'done'|'on'|'off'|'wait'.
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
    assert decide(None, None, None) == "done"
    assert decide(None, _st(*H2S), "on") == "done"


def test_off_when_already_disconnected_is_done():
    assert decide("off", None, None) == "done"


def test_off_when_connected_issues_off_then_waits():
    # faz henüz off değil -> off komutu ver
    assert decide("off", _st(*H2S), None) == "off"
    # off komutu verildi (faz off) -> bekle, tekrar verme
    assert decide("off", _st(*H2S), "off") == "wait"


# ---- bağlan ----
def test_connect_from_disconnected_issues_on_then_waits():
    assert decide(H2S, None, None) == "on"
    assert decide(H2S, None, "on") == "wait"   # asena-on verildi, gelmesini bekle


def test_connect_reached_is_done():
    assert decide(H2S, _st(*H2S), "on") == "done"


# ---- mod değiştir (yanlış modda bağlı) ----
def test_mode_switch_closes_first():
    # http2->http3: bağlıyken önce kapat
    assert decide(H3S, _st(*H2S), None) == "off"
    assert decide(H3S, _st(*H2S), "off") == "wait"      # off verildi, kapanmasını bekle


def test_mode_switch_reopens_after_close():
    # off tamamlandı (cur None) ama faz hâlâ 'off' -> hedefle aç
    assert decide(H3S, None, "off") == "on"
    assert decide(H3S, None, "on") == "wait"


def test_scope_switch_wrong_mode_closes_first():
    # selective->full: bağlıyken önce kapat
    assert decide(H2F, _st(*H2S), None) == "off"
    assert decide(H2F, _st(*H2S), "off") == "wait"


def test_full_reached_is_done():
    assert decide(H2F, _st(*H2F), "on") == "done"
