"""usque-watchdog backoff kararı (AsenaTray._watchdog_step) — saf, yan etkisiz testler.

NOT: Mode-switch artık SÜREÇ-TAMAMLANMA modeli (reconciler/_decide kaldırıldı):
asena-on'u başlat -> sürecin bitmesini bekle -> state.json'u BİR KEZ oku. Karar
döngüsü olmadığı için _decide birim testi de yok. Test edilebilir saf mantık:
watchdog backoff.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from asenaplug.tray import AsenaTray  # noqa: E402

step = AsenaTray._watchdog_step


def test_watchdog_connected_resets():
    # tünel ayakta -> ateşleme yok, backoff sıfırlanır
    assert step(True, True, False, 5, 8) == (False, 1, 1)


def test_watchdog_user_disconnected_resets():
    # kullanıcı bağlı olmak İSTEMİYOR -> watchdog susar, sıfırlanır
    assert step(False, False, False, 3, 4) == (False, 1, 1)


def test_watchdog_busy_waits():
    # bir işlem/güncelleme sürüyor -> hiçbir şey yapma (mevcut deneme devam etsin)
    assert step(False, True, True, 2, 4) == (False, 2, 4)


def test_watchdog_counts_down():
    # düşük değilse geri say, henüz ateşleme yok
    assert step(False, True, False, 3, 4) == (False, 2, 4)


def test_watchdog_fires_and_doubles_backoff():
    # süre doldu -> ateşle, backoff ikiye katla, bir sonraki bekleme = yeni backoff
    assert step(False, True, False, 0, 4) == (True, 8, 8)


def test_watchdog_backoff_capped():
    # backoff tavanı geçmez (spam yok)
    assert step(False, True, False, 0, 20, cap=20) == (True, 20, 20)
