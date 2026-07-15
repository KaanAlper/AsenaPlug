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
