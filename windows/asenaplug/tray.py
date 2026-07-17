"""Sistem tepsisi arayüzü.

İki bağımsız seçici:
  Transport: HTTP/2 · HTTP/3   (exclusive)
  Routing:   Sadece blacklist · Her şey  (exclusive)

Durum tespiti ctypes ile (powershell yok) → 3sn poll bedava, menü anında açılır.
Mod geçişleri sihirli singleShot gecikmeleri yerine KOŞUL-BAZLI poll ile yapılır.
"""
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QLocale, QObject, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QBrush, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QInputDialog, QMenu, QSystemTrayIcon

from . import i18n, install, state, update, win
from .i18n import t
from .paths import BLACKLIST_PATH, CONFIG_JSON, LOG_FILE, APP_NAME

TRAY_REF = None  # win.notify fallback'ı için


def _log_tail(limit: int = 160) -> str:
    """usque.log'un son boş-olmayan satırı (teşhis için timeout bildirimine eklenir).
    Script'ler fire-and-forget koştuğu için hata mesajı başka türlü kullanıcıya
    ulaşmıyordu; jenerik 'zaman aşımı' yerine gerçek sebebi gösterir."""
    try:
        for ln in reversed(LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()):
            if ln.strip():
                return ln.strip()[-limit:]
    except OSError:
        pass
    return ""

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


class _StayMenu(QMenu):
    """Checkable öğe (transport/scope/autostart) tıklanınca menü KAPANMASIN — kullanıcı
    birden çok seçim yapıp sonra AYNI menüde 'Değiştir'e basabilsin. Tıklanabilir
    eylemler (Connect/Değiştir/Quit) normal davranır (kapanır)."""
    def mouseReleaseEvent(self, e):
        act = self.activeAction()
        if act is not None and act.isCheckable() and act.isEnabled():
            act.trigger()          # toggle + triggered (choose_*); super ÇAĞRILMAZ -> açık kalır
            return
        super().mouseReleaseEvent(e)


class _NetWatchWorker(QObject):
    """Fiziksel default gateway'i arka planda okur (powershell -> UI donmasın),
    sonucu Signal ile UI thread'ine verir."""
    done = Signal(object)            # gateway ip str | None

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self.done.emit(win.current_default_gateway())
        except Exception:
            self.done.emit(None)


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
        # --- işlem durumu (süreç-tamamlanma modeli; reconciler/karar-döngüsü YOK) ---
        self._op = None          # süren işlem: ("on",transport,scope) | ("off",) | None
        self._op_ticks = 0       # işlem timeout sayacı (500ms/tik, ~45s)
        self._script_proc = None      # çalışan asena-on/off süreci (single-flight)
        self._register_thread = None  # connect öncesi cihaz kaydı (arka plan)
        self._autostart_enabled = True  # gerçek durum açılışta asenkron okunur (_refresh_autostart)
        self._updating = False        # güncelleme için çıkışta teardown'ı atla (tünel açık kalsın)
        self._netwatch_worker = None  # ağ-değişimi izleyici (arka plan gateway kontrolü)
        self._net_tick = 0
        self._wd_wait = 1             # usque-watchdog: kaç tik sonra yeniden dene
        self._wd_backoff = 1          # üstel geri çekilme (tik cinsinden, ~60s tavan)

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

        self.app.aboutToQuit.connect(self.emergency_cleanup)

        # Açılışta sessiz güncelleme denetimi (sadece kurulu exe; günde 1 kez)
        if getattr(sys, "frozen", False) and update.auto_due():
            QTimer.singleShot(4000, lambda: self.check_for_updates(silent=True))

        # Oto-reconnect: son durumda BAĞLI idiysek (update/restart/logon öncesi) ve
        # şu an bağlı değilsek, kalan mod ile otomatik geri bağlan (durumu hatırla).
        if d["connected"] and state.current_state() is None:
            QTimer.singleShot(3500, self._auto_reconnect)

        # Autostart görevinin GERÇEK durumunu asenkron oku (powershell; tray'i bloklamaz)
        if getattr(sys, "frozen", False):
            QTimer.singleShot(2500, self._refresh_autostart)

    # ------------------------------------------------------------------ menu
    def _build_menu(self):
        self.menu = _StayMenu()   # checkable seçimlerde menü açık kalır (seç-seç-Değiştir)

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
        self.menu.addSeparator()   # Yönlendirme ile "Değiştir" arasına ayraç

        # DEĞİŞTİR (apply) tuşu: seçim aktif moddan farklıysa belirir. Checkbox'lar
        # SADECE seçim yapar (anında uygulamaz) -> hızlı-tıklama yarışı YOK; değişikliği
        # tek bilinçli "Değiştir" ile uygularsın. İşlem sürerken "Değiştiriliyor…" (kapalı).
        self.apply_action = QAction("", self.menu)
        self.apply_action.triggered.connect(self._apply_selection)
        self.menu.addAction(self.apply_action)
        self.menu.addSeparator()

        self.blacklist_menu = QMenu(t("blacklist_menu"))
        self.menu.addMenu(self.blacklist_menu)
        self.menu.addSeparator()

        # Güncellemeleri denetle (GitHub release)
        self.update_action = QAction(t("check_updates"), self.menu)
        self.update_action.triggered.connect(lambda: self.check_for_updates(silent=False))
        self.menu.addAction(self.update_action)

        # PC başlangıcında başlat (AsenaPlug_Tray logon görevini aç/kapa)
        self.autostart_action = QAction(t("autostart_boot"), self.menu)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(self._autostart_enabled)
        self.autostart_action.triggered.connect(self.toggle_autostart)
        self.menu.addAction(self.autostart_action)
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
        """Bağlı/bağlanıyorsa kes; değilse bağlan. (Geçiş sırasında da 'kes' -> UI'daki
        Disconnect ile tutarlı; current=None anına aldanıp yeniden connect denemez.)"""
        if self._connected_or_connecting():
            self.disconnect()
        else:
            self.set_target(self._sel_transport, self._sel_scope)

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

    # ------------------------------------------------------------------ autostart
    def _refresh_autostart(self):
        """Autostart görevinin GERÇEK durumunu oku (arka plan powershell) + checkbox."""
        self._autostart_enabled = win.autostart_enabled()
        if hasattr(self, "autostart_action"):
            self.autostart_action.setChecked(self._autostart_enabled)

    def toggle_autostart(self, checked: bool):
        """PC başlangıcında başlat: AsenaPlug_Tray logon görevini aç/kapa (silmez)."""
        if win.set_autostart(checked):
            self._autostart_enabled = checked
        else:
            self.autostart_action.setChecked(self._autostart_enabled)  # başarısız -> geri al

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
            # AĞ HATASI (bağlıyken erişilemedi) — 'en güncel' DEĞİL 'denetlenemedi'
            if not self._upd_silent:
                win.notify(APP_NAME, t("upd_check_fail"))
            return
        if res == update.UP_TO_DATE:
            if not self._upd_silent:
                win.notify(APP_NAME, t("upd_none"))
            return
        tag, url, notes, sha_url = res
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
            self._start_download(url, sha_url)

    def _start_download(self, url: str, sha_url: str | None = None):
        dest = update.UPDATE_DIR / f"{APP_NAME}.exe"
        self._toast = update.UpdateToast(t("upd_toast_header"), t("upd_downloading"))
        self._toast.show_bottom_right()
        self._downloader = update.Downloader(url, dest, sha_url)   # self ref: yaşasın
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
        # _updating: emergency_cleanup asena-off ETMESİN — tünel açık kalsın, yeni tray
        # zaten çalışan tüneli görüp devam eder (gereksiz kesinti + teardown/copy yarışı
        # yok; teardown 20sn sürüp kopyayı bloklayıp güncellemeyi sessizce iptal ettiriyordu).
        self._updating = True
        import subprocess
        try:
            subprocess.Popen([dest])
        except Exception:
            self._updating = False
            win.notify(APP_NAME, t("upd_fail"))
            return
        QTimer.singleShot(1500, self.app.quit)

    def _connected_or_connecting(self) -> bool:
        """Bağlı, VEYA bağlanmaya çalışıyor (reconcile bir connect hedefine gidiyor).
        Geçişin 'off' penceresinde current_state() anlık None olsa da mod
        değişikliği hedefe yansısın — seçim düşmesin."""
        if state.current_state() is not None:
            return True
        return self._op is not None and self._op[0] == "on"   # bağlanma işlemi sürüyor

    def choose_transport(self, t: str):
        # SADECE seçim (anında uygulama YOK). Bağlıyken 'Değiştir' tuşu belirir;
        # kapalıyken 'Connect' uygular. Böylece hızlı-tıklama yarışı olmaz.
        self._sel_transport = t
        state.write_desired(self._sel_transport, self._sel_scope)
        self.refresh()

    def choose_scope(self, s: str):
        self._sel_scope = s
        state.write_desired(self._sel_transport, self._sel_scope)
        self.rebuild_blacklist_menu()
        self.refresh()

    def _apply_selection(self):
        """'Değiştir' tuşu: seçili modu uygula. Bağlıyken çalışır (kapalıyken Connect
        kullanılır). İşlem sürerken tuş kapalı olduğundan tekrar tetiklenmez."""
        if state.current_state() is None or self._busy():
            return
        self.set_target(self._sel_transport, self._sel_scope)

    # ------------------------------------------------------------------ control
    # Reconciliation loop (Kubernetes controller / desired-vs-actual deseni):
    # tek HEDEF + tek timer + faz-kilidi. Eski "her tıkta ayrı QTimer zinciri"
    # yerine; çakışma/thrashing yok, en son hedef kazanır, kendini iyileştirir.
    def set_target(self, transport: str, scope: str):
        """Modu UYGULA (bağlan/değiştir). İşlem sürerken yok sayılır (tek anda tek iş)."""
        if self._busy():
            return
        state.write_desired(transport, scope, connected=True)   # niyet: BAĞLI (oto-reconnect)
        self._warn_dpi_conflict()                               # GoodbyeDPI vs açıksa uyar
        self._start_op(("on", transport, scope))

    def _warn_dpi_conflict(self):
        """Bağlanırken çakışan WinDivert-DPI aracı (GoodbyeDPI/zapret/ByeDPI) açıksa
        uyar — o araç TTL'i bozup tüneli çalışmaz kılar. Arka planda (powershell),
        connect'i BLOKLAMAZ."""
        import threading

        def check():
            tool = win.conflicting_dpi_tool()
            if tool:
                win.notify(APP_NAME, t("notify_dpi_conflict", tool=tool))
        threading.Thread(target=check, daemon=True).start()

    def disconnect(self):
        if self._busy():
            return
        state.write_desired(self._sel_transport, self._sel_scope, connected=False)  # niyet: KESİK
        self._start_op(("off",))

    def _auto_reconnect(self):
        """Autostart/update sonrası: niyet 'bağlı' + hâlâ değilsek son modla bağlan."""
        d = state.read_desired()
        if d["connected"] and state.current_state() is None and not self._busy():
            self.set_target(d["transport"], d["scope"])

    # --- İŞLEM (süreç-tamamlanma modeli) ---------------------------------------
    # asena-on/off'u BAŞLAT -> sürecin bitmesini BEKLE -> state.json'u BİR KEZ oku.
    # Karar döngüsü / goal karşılaştırma YOK -> re-issue, oscillation, çift-switch
    # imkânsız. Tek anda tek işlem (single-flight, _busy ile korunur).
    def _busy(self) -> bool:
        if self._op is not None:
            return True
        return self._script_proc is not None and self._script_proc.poll() is None

    def _start_op(self, op):
        """op: ('on',transport,scope) | ('off',). Register gerekiyorsa önce onu halleder."""
        self._op = op
        self._op_ticks = 0
        self.refresh()                       # UI hemen 'Değiştiriliyor…' göstersin
        if op[0] == "on" and not CONFIG_JSON.exists():
            win.notify(APP_NAME, t("registering"))
            self._register_thread = threading.Thread(
                target=install.ensure_registered, daemon=True)
            self._register_thread.start()
            QTimer.singleShot(500, self._await_register)
            return
        self._launch_script(op)

    def _await_register(self):
        if self._register_thread is not None and self._register_thread.is_alive():
            QTimer.singleShot(500, self._await_register)
            return
        self._register_thread = None
        if not CONFIG_JSON.exists():         # kayıt başarısız -> vazgeç
            self._op = None
            win.notify(APP_NAME, t("register_fail"))
            self.refresh()
            return
        self._launch_script(self._op)

    def _launch_script(self, op):
        if op[0] == "off":
            self._script_proc = win.run_script("asena-off.ps1")
        else:
            self._script_proc = win.run_script(
                "asena-on.ps1", args=["-Transport", op[1], "-Scope", op[2]])
        self._op_ticks = 0
        QTimer.singleShot(500, self._poll_op)

    @staticmethod
    def _watchdog_step(active, desired_connected, busy, wait, backoff, cap=20):
        """usque-watchdog backoff kararı (SAF, test edilebilir).
          active           — tünel gerçekten ayakta mı
          desired_connected— kullanıcı bağlı OLMAK istiyor mu (desired.json)
          busy             — reconcile/update/register sürüyor mu
        Döner: (fire, new_wait, new_backoff). fire=True -> yeniden bağlan.
        Bağlıysa ya da kullanıcı kapattıysa sıfırla; deneme sürüyorsa bekle; değilse
        geri sayıp süresi dolunca ateşle ve backoff'u ikiye katla (tavan=cap tik)."""
        if active or not desired_connected:
            return False, 1, 1
        if busy:
            return False, wait, backoff
        if wait > 0:
            return False, wait - 1, backoff
        new_backoff = min(backoff * 2, cap)
        return True, new_backoff, new_backoff

    def _poll_op(self):
        """Çalışan asena-on/off SÜRECİNİ bekle. Bitince state.json'u BİR KEZ oku
        (fallback http2 olabilir), UI'yi gerçek duruma getir. Zaman aşımı ~45s.
        Sürekli state.json okuyup KARŞILAŞTIRMA/RE-ISSUE yok -> oscillation imkânsız."""
        if self._script_proc is None:
            self._op = None
            return
        if self._script_proc.poll() is None:      # süreç HÂLÂ çalışıyor
            self._op_ticks += 1
            if self._op_ticks > 90:               # ~45s -> vazgeç
                self._script_proc = None
                self._op = None
                tail = _log_tail()
                win.notify(APP_NAME, t("notify_timeout") + (f"\n{tail}" if tail else ""))
                self.refresh()
                return
            QTimer.singleShot(500, self._poll_op)
            return
        # SÜREÇ BİTTİ -> sonucu BİR KEZ oku (asena-on state.json'u en sonda yazar)
        self._script_proc = None
        op = self._op
        self._op = None
        cur = state.current_state()
        # h3->h2 fallback (UDP bloklu ağ): seçili transport'u GERÇEĞE eşitle + bildir
        if op and op[0] == "on" and cur is not None and cur["transport"] != op[1]:
            self._sel_transport = cur["transport"]
            state.write_desired(cur["transport"], cur["scope"])
            win.notify(APP_NAME, t("notify_transport_fallback",
                                   got=_T_LABEL.get(cur["transport"], cur["transport"])))
        self.refresh()                            # gerçek durumu göster + bildir

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
            # Bağlıysa 'DNS yenile ile aktif et'; kapalıysa bağlanınca zaten alınır
            key = "notify_added" if state.current_state() is not None else "notify_added_offline"
            win.notify(title, t(key, domain=domain.strip()))
        else:
            win.notify(title, t("notify_not_added"))
        self.rebuild_blacklist_menu()

    def reload_dns(self):
        title = f"{APP_NAME} {t('notify_title_blacklist')}"
        if state.current_state() is None:
            # Kapalıyken yenilemeye GEREK YOK — connect (asena-on) zaten blacklist'i
            # okuyup NRPT + warm-up ile hepsini alır. Sadece bilgilendir.
            win.notify(title, t("notify_apply_on_connect"))
            return
        win.run_script("asena-dns-reload.ps1")
        win.notify(title, t("notify_dns_reloading"))

    # ------------------------------------------------------------------ poll
    def refresh(self):
        st = state.current_state()
        active = st is not None
        # Bir bağlanma/değiştirme işlemi sürüyor mu (op = ('on', transport, scope))?
        switching = self._op is not None and self._op[0] == "on"

        if active:
            self.tray.setIcon(self.icon_on)
            detail = _detail(st)
            self.tray.setToolTip(t("tip_connected", app=APP_NAME, detail=detail))
            self.toggle_action.setText(t("disconnect"))
            self.status_action.setText(t("status_connected", detail=detail))
        elif switching:
            # GEÇİŞ sürüyor (usque restart -> anlık current=None): ikon "on" KALSIN,
            # griye dönüp 'disconnect' GÖSTERMESİN -> kullanıcıya tek akıcı işlem gibi.
            gd = f"{_T_LABEL.get(self._op[1], self._op[1])} · {t('scope_' + self._op[2])}"
            self.tray.setIcon(self.icon_on)
            self.tray.setToolTip(t("tip_switching", app=APP_NAME, detail=gd))
            self.toggle_action.setText(t("disconnect"))
            self.status_action.setText(t("status_switching", detail=gd))
        else:
            # Kapalı: durum satırı SEÇİLİ modu gösterir -> "Bağlan"ın ne uygulayacağı
            # baştan belli (tuş sade "Bağlan" kalır; işlem şeffaflığı durum satırında).
            sd = f"{_T_LABEL.get(self._sel_transport, self._sel_transport)} · {t('scope_' + self._sel_scope)}"
            self.tray.setIcon(self.icon_off)
            self.tray.setToolTip(t("tip_disconnected", app=APP_NAME))
            self.toggle_action.setText(t("connect"))
            self.status_action.setText(t("status_ready", detail=sd))

        # Checkmark = SEÇİM (her zaman). İşlem SÜRERKEN checkbox'lar KİLİTLİ -> geçiş
        # ortasında mod seçilip "http3 işaretli ama http2 uygulanıyor" karışıklığı olmaz.
        # (Döngü değişkeni 'tk'/'sk' — global t()'yi gölgeleme.)
        locked = self._busy()
        for tk, a in self.transport_actions.items():
            a.setChecked(tk == self._sel_transport)
            a.setEnabled(not locked)
        for sk, a in self.scope_actions.items():
            a.setChecked(sk == self._sel_scope)
            a.setEnabled(not locked)

        # DEĞİŞTİR tuşu: bir işlem sürerken (switch VEYA arka-plan asena-on)
        # "Değiştiriliyor…" (kapalı); bağlı+seçim aktif moddan farklıysa
        # "Değiştir → {hedef}" (tıklanabilir); yoksa gizli.
        if switching or self._busy():
            self.apply_action.setText(t("switching_btn"))
            self.apply_action.setEnabled(False)
            self.apply_action.setVisible(True)
        elif active and (self._sel_transport, self._sel_scope) != (st["transport"], st["scope"]):
            gd = f"{_T_LABEL.get(self._sel_transport, self._sel_transport)} · {t('scope_' + self._sel_scope)}"
            self.apply_action.setText(t("apply_btn", detail=gd))
            self.apply_action.setEnabled(True)
            self.apply_action.setVisible(True)
        else:
            self.apply_action.setVisible(False)   # kapalı VEYA değişiklik yok

        # İşlem sürerken ARA durumları bildirme; _last_state'i de dondur ki işlem
        # bitince (op temizlenince) tek "Connected/Disconnected" gelsin.
        if self._op is None:
            if self._initialized and st != self._last_state:
                if active:
                    win.notify(APP_NAME, t("notify_connected", detail=_detail(st)))
                else:
                    win.notify(APP_NAME, t("notify_disconnected"))
            self._last_state = st
            self._initialized = True

        # Ağ-değişimi izleme: bağlıyken ~15s'te bir fiziksel gateway'i kontrol et.
        # state.json'daki gwIP'den farklıysa (WiFi switch / uykudan dönüş / hotspot)
        # endpoint pin + route'lar bayatlar -> arka planda asena-on ile yeniden pinle.
        if active and not self._busy() and not self._updating:
            self._net_tick += 1
            if self._net_tick >= 5 and self._netwatch_worker is None:
                self._net_tick = 0
                self._netwatch_worker = _NetWatchWorker()
                self._netwatch_worker.done.connect(self._on_netwatch)
                self._netwatch_worker.start()
        else:
            self._net_tick = 0

        # usque-watchdog: kullanıcı bağlı olmak isterken (desired.connected) tünel
        # BEKLENMEDİK düştüyse (usque süreç çökmesi — --always-reconnect ağ blip'ini
        # kapsar ama süreç ölümünü değil) BACKOFF'lu yeniden bağlan. Elle kesme
        # (desired.connected=False) tetiklemez; connect denemesi sürerken bekler.
        busy = self._busy() or self._updating
        fire, self._wd_wait, self._wd_backoff = self._watchdog_step(
            active, state.read_desired()["connected"], busy, self._wd_wait, self._wd_backoff)
        if fire:
            d = state.read_desired()
            self.set_target(d["transport"], d["scope"])

    def _on_netwatch(self, live_gw):
        self._netwatch_worker = None
        # SINGLE-FLIGHT: bir işlem (op) veya başka asena-on koşuyorsa DOKUNMA —
        # net-watch'ın asena-on'u kullanıcı işlemiyle çakışıp bozmasın.
        if not live_gw or self._busy() or self._updating:
            return
        cur = state.current_state()
        if cur is None:
            return                       # bu arada bağlantı kesildi
        st = state.read_state()
        base = st.get("gwIP") if st else None
        if not base or live_gw == base:
            return                       # gateway değişmedi (ya da baz bilinmiyor)
        # Ağ değişti -> mevcut mod için route'ları yeniden uygula. usque çalıştığından
        # asena-on RESTART ETMEZ; sadece endpoint pin/MTU/DNS'i yeni gateway'e göre
        # tazeler ve state.json'daki gwIP'yi günceller (bir sonraki kontrol eşleşir).
        win.notify(APP_NAME, t("notify_net_reapply"))
        self._script_proc = win.run_script(
            "asena-on.ps1", args=["-Transport", cur["transport"], "-Scope", cur["scope"]])
        self._net_tick = -10   # asena-on bitip state.json'u güncelleyene dek (~45s) tekrar tetikleme

    def emergency_cleanup(self):
        """Kapanırken Asena açıksa SENKRON kapat ki DNS/route teardown tamamlansın.

        Tray elevated olduğundan asena-off.ps1 doğrudan admin olarak koşar;
        wait=True ile bitmesini bekleriz (fire-and-forget'te yarıda kalmaz).

        GÜNCELLEME İSTİSNASI: _updating iken teardown ATLANIR — tünel açık kalır,
        yeni tray onu devralır (kesintisiz güncelleme + copy-lock yarışı yok)."""
        if self._updating or state.current_state() is None:
            return
        try:
            win.run_script("asena-off.ps1", wait=True, timeout=20)
        except Exception:
            win.run_script("asena-off.ps1")

    def run(self):
        import sys
        sys.exit(self.app.exec())
