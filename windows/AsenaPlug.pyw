#!/usr/bin/env python3
"""AsenaPlug — Windows giriş noktası (ince).

İlk çalıştırmada kurulum (admin gerekir), sonra tray olarak çalışır.
Tüm mantık `asenaplug/` paketinde. PyInstaller ile tek exe'ye paketlenir;
geliştirme için `pythonw AsenaPlug.pyw` ile de çalışır.
"""
import sys
from pathlib import Path

# Geliştirme modunda `asenaplug` paketini import edebilmek için
sys.path.insert(0, str(Path(__file__).resolve().parent))

from asenaplug import install, win  # noqa: E402
from asenaplug.tray import AsenaTray  # noqa: E402


def _msgbox_error(text: str):
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication(sys.argv)
    QMessageBox.critical(None, "AsenaPlug Kurulum Hatası", text)


def _run_setup_visible():
    """İlk kurulumu GÖRÜNÜR yap: ekranın sağ-altında 'Kuruluyor…' göstergesi +
    bitince 'Hazır — tepside' bildirimi. Sessiz devir/kaybolma hissi kalkar."""
    from PySide6.QtCore import QLocale
    from PySide6.QtWidgets import QApplication
    from asenaplug import i18n, update
    from asenaplug.i18n import t
    from asenaplug.paths import APP_NAME

    app = QApplication.instance() or QApplication(sys.argv)
    i18n.init(QLocale.system().name().split("_")[0])
    toast = update.UpdateToast(APP_NAME, t("setup_running"))
    toast.set_busy()
    toast.show_bottom_right()
    app.processEvents()
    try:
        install.run_setup()
    except Exception as e:
        toast.close()
        _msgbox_error(str(e))
        sys.exit(1)
    toast.close()
    win.notify(APP_NAME, t("setup_done"))


def main():
    # Tray her zaman YÖNETİCİ olmalı: asena-on/off admin ister, script/exe kopyalama
    # da öyle. Kurulu olsa bile (logon görevi dışı elle açılışta) yönetici değilsek
    # UAC ile yüksel — yoksa connect olmaz ve yeni scriptler kopyalanmaz.
    if not win.is_admin():
        win.relaunch_as_admin()  # UAC; yükseltilmiş kopya devam eder, bu süreç biter

    if install.needs_setup():
        _run_setup_visible()             # ilk kurulum — GÖRÜNÜR (toast + 'hazır' bildirimi)
    elif install.needs_upgrade() or install.installed_version() is None:
        # Kurulu ama exe sürümü daha yeni (ya da eski flag'li kurulum) → tazele + sürüm yaz
        install.apply_upgrade()
    else:
        # Sürüm güncel: sadece scriptleri senkronla + exe'yi yerinde tut (no-op'a yakın)
        install.refresh_scripts()
        install.install_self()

    # dist'ten çalışıyorsak Program Files'taki kurulu kopyaya DEVRET (aktif o olsun);
    # mutex'i tutmadan devret ki yeni süreç alabilsin.
    if not install.running_from_install() and install.APP_EXE.exists():
        install.launch_installed()
        sys.exit(0)

    # Aynı anda tek tray (logon görevi + elle açış iki tray açmasın)
    if not win.acquire_single_instance():
        sys.exit(0)
    AsenaTray().run()


if __name__ == "__main__":
    main()
