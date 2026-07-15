"""Sistem tepsisi arayüzü.

İki bağımsız seçici:
  Transport: HTTP/2 · HTTP/3   (exclusive)
  Routing:   Sadece blacklist · Her şey  (exclusive)

Durum tespiti ctypes ile (powershell yok) → 3sn poll bedava, menü anında açılır.
Mod geçişleri sihirli singleShot gecikmeleri yerine KOŞUL-BAZLI poll ile yapılır.
"""
import os
import sys
from pathlib import Path

from PySide6.QtCore import QLocale, QRect, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QBrush, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QInputDialog, QMenu, QSystemTrayIcon

from . import i18n, state, update, win
from .i18n import t
from .paths import BLACKLIST_PATH, APP_NAME

TRAY_REF = None  # win.notify fallback'ı için

_T_LABEL = {"http2": "HTTP/2", "http3": "HTTP/3"}  # teknik etiket — çevrilmez


def _detail(st) -> str:
    """Tray/tooltip alt satırı: 'HTTP/2 · Sadece blacklist' (scope dile göre)."""
    return f"{_T_LABEL[st['transport']]} · {t('scope_' + st['scope'])}"

ICON_SIZE = 64
_GREEN = QColor(76, 175, 80)
_GRAY = QColor(158, 158, 158)


def _asset(name: str) -> Path:
    """Bundle (PyInstaller _MEIPASS) veya repo'daki assets/."""
    base = getattr(sys, "_MEIPASS", str(Path(__file__).resolve().parent.parent))
    return Path(base) / "assets" / name


_WOLF = None


def _wolf_base() -> QPixmap:
    global _WOLF
    if _WOLF is None:
        p = _asset("AsenaPlug.png")
        _WOLF = QPixmap(str(p)) if p.exists() else QPixmap()
    return _WOLF


def make_icon(connected: bool) -> QIcon:
    """Asena kurt logosu + sağ altta durum noktası (yeşil=bağlı, gri=değil).
    Bağlı değilken kurt soluk gösterilir. Logo yoksa 'W' fallback'ı çizilir."""
    base = _wolf_base()
    if base.isNull():
        return _make_icon_fallback(connected)

    canvas = QPixmap(ICON_SIZE, ICON_SIZE)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    wolf = base.scaled(ICON_SIZE, ICON_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
    p.setOpacity(1.0 if connected else 0.45)  # kapalıyken soluk
    p.drawPixmap((ICON_SIZE - wolf.width()) // 2, (ICON_SIZE - wolf.height()) // 2, wolf)
    p.setOpacity(1.0)
    d = ICON_SIZE * 5 // 16  # durum noktası ~20px, sağ alt
    p.setPen(QPen(QColor(255, 255, 255), 2))
    p.setBrush(QBrush(_GREEN if connected else _GRAY))
    p.drawEllipse(QRect(ICON_SIZE - d - 1, ICON_SIZE - d - 1, d, d))
    p.end()
    return QIcon(canvas)


def _make_icon_fallback(connected: bool) -> QIcon:
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = _GREEN if connected else _GRAY
    margin = 6
    rect = QRect(margin, margin, ICON_SIZE - 2 * margin, ICON_SIZE - 2 * margin)
    if connected:
        p.setBrush(QBrush(color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(rect)
        p.setPen(QPen(QColor(255, 255, 255)))
    else:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(color, 4))
        p.drawEllipse(rect)
        p.setPen(QPen(color))
    font = QFont()
    font.setPointSize(28)
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRect(0, 0, ICON_SIZE, ICON_SIZE), Qt.AlignmentFlag.AlignCenter, "W")
    p.end()
    return QIcon(pixmap)


class AsenaTray:
    def __init__(self):
        global TRAY_REF
        self.app = QApplication.instance() or QApplication([])
        self.app.setQuitOnLastWindowClosed(False)

        # Dil: kayıtlı varsa onu; yoksa OS dilini (listede yoksa 'en') seç + kaydet
        i18n.init(QLocale.system().name().split("_")[0])

        _wp = _asset("AsenaPlug.png")  # dialog/taskbar ikonu
        if _wp.exists():
            self.app.setWindowIcon(QIcon(str(_wp)))

        self.icon_on = make_icon(True)
        self.icon_off = make_icon(False)

        # Tray'in seçili istediği (kullanıcı seçimi)
        d = state.read_desired()
        self._sel_transport = d["transport"]
        self._sel_scope = d["scope"]
        self._last_state: dict | None = None
        self._initialized = False
        # --- reconciler durumu (tek hedef, tek timer; thrashing yok) ---
        self._goal = None        # (transport, scope) = bağlan; "off" = kes; None = boşta
        self._phase = None       # en son verilen komut: "on" | "off" | None
        self._phase_ticks = 0
        self._reconciling = False

        self.tray = QSystemTrayIcon()
        TRAY_REF = self.tray
        self.tray.setIcon(self.icon_off)
        self.tray.activated.connect(self._on_click)

        self._build_menu()

        self.refresh()
        self.tray.setVisible(True)

        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)

        # Debounce: hızlı ardışık tıklamalar (transport+scope) tek işleme birleşsin
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._begin_reconcile)

        self.app.aboutToQuit.connect(self.emergency_cleanup)

        # Açılışta sessiz güncelleme denetimi (sadece kurulu exe; günde 1 kez)
        if getattr(sys, "frozen", False) and update.auto_due():
            QTimer.singleShot(4000, lambda: self.check_for_updates(silent=True))

    # ------------------------------------------------------------------ menu
    def _build_menu(self):
        self.menu = QMenu()

        # Connect/Disconnect — duruma göre metni değişen, HER ZAMAN tıklanabilir
        self.toggle_action = QAction(t("connect"))
        self.toggle_action.triggered.connect(self.toggle)
        self.menu.addAction(self.toggle_action)

        # Durum satırı (bilgi amaçlı, tıklanamaz)
        self.status_action = QAction(t("status_disconnected"))
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)
        self.menu.addSeparator()

        # Transport grubu (HTTP/2 · HTTP/3 teknik etiket — çevrilmez)
        hdr_t = self.menu.addAction(t("hdr_transport"))
        hdr_t.setEnabled(False)
        self.transport_group = QActionGroup(self.menu)
        self.transport_group.setExclusive(True)
        self.transport_actions = {}
        for tr in ("http2", "http3"):
            a = QAction(_T_LABEL[tr], self.menu)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, x=tr: self.choose_transport(x))
            self.transport_group.addAction(a)
            self.menu.addAction(a)
            self.transport_actions[tr] = a
        self.menu.addSeparator()

        # Routing scope grubu
        hdr_s = self.menu.addAction(t("hdr_routing"))
        hdr_s.setEnabled(False)
        self.scope_group = QActionGroup(self.menu)
        self.scope_group.setExclusive(True)
        self.scope_actions = {}
        for s in ("selective", "full"):
            a = QAction(t(f"scope_{s}"), self.menu)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, x=s: self.choose_scope(x))
            self.scope_group.addAction(a)
            self.menu.addAction(a)
            self.scope_actions[s] = a
        self.menu.addSeparator()

        self.blacklist_menu = QMenu(t("blacklist_menu"))
        self.menu.addMenu(self.blacklist_menu)
        self.menu.addSeparator()

        # Güncellemeleri denetle (GitHub release)
        self.update_action = QAction(t("check_updates"), self.menu)
        self.update_action.triggered.connect(lambda: self.check_for_updates(silent=False))
        self.menu.addAction(self.update_action)
        self.menu.addSeparator()

        # Dil alt menüsü (çıkışın hemen üstünde) — üzerine gelince diller açılır
        self.language_menu = QMenu(t("language"))
        self.language_group = QActionGroup(self.language_menu)
        self.language_group.setExclusive(True)
        cur = i18n.get_language()
        for code, native in i18n.available():
            a = QAction(native, self.language_menu)   # her dil kendi adıyla
            a.setCheckable(True)
            a.setChecked(code == cur)
            a.triggered.connect(lambda _=False, x=code: self.choose_language(x))
            self.language_group.addAction(a)
            self.language_menu.addAction(a)
        self.menu.addMenu(self.language_menu)
        self.menu.addSeparator()

        # parent=self.menu + self.* referansı: QAction GC'ye gidip menüden DÜŞMESİN
        self.quit_action = QAction(t("quit"), self.menu)
        self.quit_action.triggered.connect(self.app.quit)
        self.menu.addAction(self.quit_action)

        self.tray.setContextMenu(self.menu)
        # Sadece UCUZ blacklist menüsü her açılışta yenilenir (powershell yok)
        self.menu.aboutToShow.connect(self.rebuild_blacklist_menu)
        self.rebuild_blacklist_menu()

    def rebuild_blacklist_menu(self):
        self.blacklist_menu.clear()
        count = state.blacklist_count()
        info = self.blacklist_menu.addAction(t("bl_count", n=count))
        info.setEnabled(False)
        if self._sel_scope == "full":
            note = self.blacklist_menu.addAction(t("bl_full_note"))
            note.setEnabled(False)
        self.blacklist_menu.addSeparator()
        self.blacklist_menu.addAction(t("bl_edit")).triggered.connect(self.open_blacklist)
        self.blacklist_menu.addAction(t("bl_add")).triggered.connect(self.prompt_add_domain)
        self.blacklist_menu.addAction(t("bl_reload")).triggered.connect(self.reload_dns)

    # ------------------------------------------------------------------ events
    def toggle(self):
        """Bağlı değilse bağlan (seçili mod), bağlıysa kes."""
        if state.current_state() is None:
            self.set_target(self._sel_transport, self._sel_scope)
        else:
            self.disconnect()

    def _on_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle()

    def choose_language(self, code: str):
        """Dili değiştir, kalıcı yaz, menüyü YENİDEN kur (tüm etiketler güncellensin)."""
        if code == i18n.get_language():
            return
        i18n.set_language(code)
        i18n.save(code)
        self._build_menu()   # setContextMenu + tüm etiketleri yeniden üretir
        self.refresh()       # ikon/tooltip/durum satırını yeni dille güncelle

    # ------------------------------------------------------------------ update
    def check_for_updates(self, silent: bool = False):
        """GitHub release'i arka planda denetle. silent=True: açılıştaki otomatik
        denetim (sonuç yoksa sessiz); False: menüden manuel (her sonucu bildir)."""
        self._upd_silent = silent
        if not silent:
            win.notify(APP_NAME, t("upd_checking"))
        update.mark_checked()
        self._checker = update.Checker()          # self ref: sinyal boyunca yaşasın
        self._checker.result.connect(self._on_update_result)
        self._checker.start()

    def _on_update_result(self, res):
        if res is None:
            if not self._upd_silent:
                win.notify(APP_NAME, t("upd_none"))
            return
        tag, url, notes = res
        from PySide6.QtWidgets import QMessageBox
        text = t("upd_available", ver=tag)
        if notes:
            text += "\n\n" + notes[:500]
        box = QMessageBox()
        box.setWindowTitle(t("upd_available_title"))
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Information)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if box.exec() == QMessageBox.StandardButton.Yes:
            self._start_download(url)

    def _start_download(self, url: str):
        dest = update.UPDATE_DIR / f"{APP_NAME}.exe"
        self._toast = update.UpdateToast(t("upd_toast_header"), t("upd_downloading"))
        self._toast.show_bottom_right()
        self._downloader = update.Downloader(url, dest)   # self ref: yaşasın
        self._downloader.progress.connect(self._toast.set_pct)
        self._downloader.finished.connect(self._on_download_done)
        self._downloader.start()

    def _on_download_done(self, ok: bool, dest: str):
        if not ok:
            if getattr(self, "_toast", None):
                self._toast.close()
            win.notify(APP_NAME, t("upd_fail"))
            return
        self._toast.set_pct(100)
        self._toast.set_sub(t("upd_installing"))
        # Yeni exe'yi başlat: install_self() onu Program Files'a kopyalar (bu tray
        # kapanınca kilit kalkar; install_self retry ile bekler). Sonra bu tray'i kapat.
        import subprocess
        try:
            subprocess.Popen([dest])
        except Exception:
            win.notify(APP_NAME, t("upd_fail"))
            return
        QTimer.singleShot(1500, self.app.quit)

    def _connected_or_connecting(self) -> bool:
        """Bağlı, VEYA bağlanmaya çalışıyor (reconcile bir connect hedefine gidiyor).
        Geçişin 'off' penceresinde current_state() anlık None olsa da mod
        değişikliği hedefe yansısın — seçim düşmesin."""
        if state.current_state() is not None:
            return True
        return self._reconciling and self._goal not in (None, "off")

    def choose_transport(self, t: str):
        self._sel_transport = t
        state.write_desired(self._sel_transport, self._sel_scope)
        if self._connected_or_connecting():
            self.set_target(t, self._sel_scope)

    def choose_scope(self, s: str):
        self._sel_scope = s
        state.write_desired(self._sel_transport, self._sel_scope)
        self.rebuild_blacklist_menu()
        if self._connected_or_connecting():
            self.set_target(self._sel_transport, s)

    # ------------------------------------------------------------------ control
    # Reconciliation loop (Kubernetes controller / desired-vs-actual deseni):
    # tek HEDEF + tek timer + faz-kilidi. Eski "her tıkta ayrı QTimer zinciri"
    # yerine; çakışma/thrashing yok, en son hedef kazanır, kendini iyileştirir.
    def set_target(self, transport: str, scope: str):
        state.write_desired(transport, scope)          # kalıcılık (boot/route-sync)
        self._request((transport, scope))

    def disconnect(self):
        self._request("off")

    def _request(self, goal):
        """goal: (transport, scope) = bağlan; 'off' = kes. En son istek kazanır."""
        self._goal = goal
        if self._reconciling:
            return                       # loop çalışıyor; sonraki tik en son hedefi alır
        self._debounce.start(350)        # debounce: hızlı ardışık tıklamaları birleştir

    def _begin_reconcile(self):
        if not self._reconciling:
            self._reconciling = True
            self._phase = None
            self._phase_ticks = 0
            self._reconcile()

    @staticmethod
    def _decide(goal, cur, phase):
        """Saf karar: (hedef, mevcut durum, son faz) -> eylem. Yan etkisiz => test edilebilir.
          goal: (transport, scope) | 'off' | None ;  cur: state dict | None
        Döner:
          'done' — hedefe ulaşıldı
          'on'   — asena-on ver (kapalı, hedefe aç)
          'off'  — asena-off ver (kapatılmalı: kesme ya da yanlış modda bağlı)
          'wait' — komut zaten verildi (phase eşleşiyor), gelmesini bekle"""
        if goal is None:
            return "done"
        connected = cur is not None
        if goal == "off":
            if not connected:
                return "done"
            return "wait" if phase == "off" else "off"
        # goal = (transport, scope)
        if connected and (cur["transport"], cur["scope"]) == goal:
            return "done"
        if connected:                    # yanlış modda bağlı -> önce kapat
            return "wait" if phase == "off" else "off"
        return "wait" if phase == "on" else "on"   # kapalı -> hedefle aç

    def _reconcile(self):
        self.refresh()
        goal = self._goal
        action = self._decide(goal, state.current_state(), self._phase)

        if action == "done":
            self._reconciling = False
            self._phase = None
            self.refresh()               # son durumu bildir (reconcile bitti)
            return

        # Komut SADECE faz değişiminde verilir ('wait' => tekrar verme, thrashing yok)
        if action == "on":
            win.run_script("asena-on.ps1", args=["-Transport", goal[0], "-Scope", goal[1]])
            self._phase = "on"
            self._phase_ticks = 0
        elif action == "off":
            win.run_script("asena-off.ps1")
            self._phase = "off"
            self._phase_ticks = 0

        # Timeout: faz takılırsa vazgeç (asena-on/off gelmedi). "on" daha uzun:
        # asena-on artık eager warm-up (blacklist'i çöz+route) yapıyor, connect
        # meşru olarak ~10-25sn sürebilir -> erken timeout vermesin.
        self._phase_ticks += 1
        limit = 60 if self._phase == "on" else 24     # ~30s / ~12s (500ms tik)
        if self._phase_ticks > limit:
            self._reconciling = False
            self._phase = None
            win.notify(APP_NAME, t("notify_timeout"))
            self.refresh()
            return

        QTimer.singleShot(500, self._reconcile)

    # ------------------------------------------------------------------ blacklist
    def open_blacklist(self):
        BLACKLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        BLACKLIST_PATH.touch(exist_ok=True)
        os.startfile(str(BLACKLIST_PATH))

    def prompt_add_domain(self):
        domain, ok = QInputDialog.getText(None, t("dlg_add_title"), t("dlg_add_label"))
        if not ok:
            return
        title = t("notify_title_blacklist")
        if state.add_domain(domain):
            win.notify(title, t("notify_added", domain=domain.strip()))
        else:
            win.notify(title, t("notify_not_added"))
        self.rebuild_blacklist_menu()

    def reload_dns(self):
        title = f"{APP_NAME} {t('notify_title_blacklist')}"
        if state.current_state() is None:
            win.notify(title, t("notify_open_first", app=APP_NAME))
            return
        win.run_script("asena-dns-reload.ps1")
        win.notify(title, t("notify_dns_reloading"))

    # ------------------------------------------------------------------ poll
    def refresh(self):
        st = state.current_state()
        active = st is not None
        self.tray.setIcon(self.icon_on if active else self.icon_off)

        if active:
            detail = _detail(st)
            self.tray.setToolTip(t("tip_connected", app=APP_NAME, detail=detail))
            self.toggle_action.setText(t("disconnect"))
            self.status_action.setText(t("status_connected", detail=detail))
        else:
            self.tray.setToolTip(t("tip_disconnected", app=APP_NAME))
            self.toggle_action.setText(t("connect"))
            self.status_action.setText(t("status_disconnected"))

        # Checkmark: bağlıysa gerçek durum, değilse seçili istek
        # (döngü değişkeni 'tk'/'sk' — global t() çevirmenini gölgelememek için)
        shown_t = st["transport"] if active else self._sel_transport
        shown_s = st["scope"] if active else self._sel_scope
        for tk, a in self.transport_actions.items():
            a.setChecked(tk == shown_t)
        for sk, a in self.scope_actions.items():
            a.setChecked(sk == shown_s)

        # Reconcile sürerken ARA durumları bildirme; _last_state'i de dondur ki
        # geçiş bitince (reconcile kapanınca) tek "Connected/Disconnected" gelsin.
        if not self._reconciling:
            if self._initialized and st != self._last_state:
                if active:
                    win.notify(APP_NAME, t("notify_connected", detail=_detail(st)))
                else:
                    win.notify(APP_NAME, t("notify_disconnected"))
            self._last_state = st
            self._initialized = True

    def emergency_cleanup(self):
        """Kapanırken Asena açıksa SENKRON kapat ki DNS/route teardown tamamlansın.

        Tray elevated olduğundan asena-off.ps1 doğrudan admin olarak koşar;
        wait=True ile bitmesini bekleriz (fire-and-forget'te yarıda kalmaz)."""
        if state.current_state() is None:
            return
        try:
            win.run_script("asena-off.ps1", wait=True, timeout=20)
        except Exception:
            win.run_script("asena-off.ps1")

    def run(self):
        import sys
        sys.exit(self.app.exec())
