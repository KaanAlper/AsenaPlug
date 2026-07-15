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

from . import endpoint, i18n, install, state, update, win
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


class _EndpointWorker(QObject):
    """endpoint.optimize()'ı arka planda koşar (bloklayan TCP taraması UI'yi
    dondurmasın), sonucu Signal ile UI thread'ine verir."""
    done = Signal(object)            # (ip, ms) | None

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self.done.emit(endpoint.optimize())
        except Exception:
            self.done.emit(None)


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
        self._sel_killswitch = d["killswitch"]
        self._last_state: dict | None = None
        self._initialized = False
        # --- reconciler durumu (tek hedef, tek timer; thrashing yok) ---
        self._goal = None        # (transport, scope) = bağlan; "off" = kes; None = boşta
        self._issued = None      # bu hedef için komut verildi mi (issue-once)
        self._phase_ticks = 0
        self._reconciling = False
        self._register_thread = None  # connect öncesi cihaz kaydı (arka plan)
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

        # Debounce: hızlı ardışık tıklamalar (transport+scope) tek işleme birleşsin
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._begin_reconcile)

        self.app.aboutToQuit.connect(self.emergency_cleanup)

        # Açılışta sessiz güncelleme denetimi (sadece kurulu exe; günde 1 kez)
        if getattr(sys, "frozen", False) and update.auto_due():
            QTimer.singleShot(4000, lambda: self.check_for_updates(silent=True))

        # Oto-reconnect: son durumda BAĞLI idiysek (update/restart/logon öncesi) ve
        # şu an bağlı değilsek, kalan mod ile otomatik geri bağlan (durumu hatırla).
        if d["connected"] and state.current_state() is None:
            QTimer.singleShot(3500, self._auto_reconnect)

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

        # Kill-switch (opsiyonel; sadece full modda etkili): tünel düşerse trafiği kes
        self.killswitch_action = QAction(t("killswitch"), self.menu)
        self.killswitch_action.setCheckable(True)
        self.killswitch_action.setChecked(self._sel_killswitch)
        self.killswitch_action.triggered.connect(self.toggle_killswitch)
        self.menu.addAction(self.killswitch_action)
        self.menu.addSeparator()

        # Bağlantıyı hızlandır: en yakın WARP endpoint'ini LOKAL ölç + uygula
        self.speed_action = QAction(t("optimize_endpoint"), self.menu)
        self.speed_action.triggered.connect(self.optimize_endpoint)
        self.menu.addAction(self.speed_action)
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

    # ------------------------------------------------------------ endpoint hızı
    def optimize_endpoint(self):
        """En yakın WARP endpoint'ini LOKAL ölç + config.json'a uygula. Ölçüm
        arka planda; menü/UI donmaz. Etki bir sonraki bağlanışta görünür."""
        if getattr(self, "_ep_worker", None) is not None:
            return                                  # zaten sürüyor
        win.notify(APP_NAME, t("opt_scanning"))
        self._ep_worker = _EndpointWorker()         # self ref: sinyal boyunca yaşasın
        self._ep_worker.done.connect(self._on_optimize_done)
        self._ep_worker.start()

    def _on_optimize_done(self, res):
        self._ep_worker = None
        if not res:
            win.notify(APP_NAME, t("opt_fail"))
            return
        ip, ms = res
        # Bağlıysak yeni endpoint ancak yeniden bağlanınca etkin olur — kullanıcıya söyle
        key = "opt_done_reconnect" if state.current_state() is not None else "opt_done"
        win.notify(APP_NAME, t(key, ip=ip, ms=int(ms)))

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

    def toggle_killswitch(self, checked: bool):
        """Kill-switch tercihini KALICI kaydet. Yalnız full modda etkili (asena-on
        desired.json'dan okur). Full modda BAĞLIYKEN açıp/kapatırsan firewall'u hemen
        güncellemek için route'ları yeniden uygula; değilsen sonraki full connect'te
        uygulanır."""
        self._sel_killswitch = checked
        state.write_desired(self._sel_transport, self._sel_scope, killswitch=checked)
        cur = state.current_state()
        if cur is not None and cur["scope"] == "full":
            win.run_script("asena-on.ps1", args=["-Transport", cur["transport"], "-Scope", cur["scope"]])

    # ------------------------------------------------------------------ control
    # Reconciliation loop (Kubernetes controller / desired-vs-actual deseni):
    # tek HEDEF + tek timer + faz-kilidi. Eski "her tıkta ayrı QTimer zinciri"
    # yerine; çakışma/thrashing yok, en son hedef kazanır, kendini iyileştirir.
    def set_target(self, transport: str, scope: str):
        state.write_desired(transport, scope, connected=True)   # niyet: BAĞLI (oto-reconnect)
        self._request((transport, scope))

    def disconnect(self):
        state.write_desired(self._sel_transport, self._sel_scope, connected=False)  # niyet: KESİK
        self._request("off")

    def _auto_reconnect(self):
        """Autostart/update sonrası: niyet 'bağlı' + hâlâ değilsek son modla bağlan.
        (Gecikme içinde kullanıcı elle bağlandıysa / reconcile başladıysa atla.)"""
        d = state.read_desired()
        if d["connected"] and state.current_state() is None and not self._reconciling:
            self.set_target(d["transport"], d["scope"])

    def _request(self, goal):
        """goal: (transport, scope) = bağlan; 'off' = kes. En son istek kazanır."""
        self._goal = goal
        if self._reconciling:
            return                       # loop çalışıyor; sonraki tik en son hedefi alır
        self._debounce.start(350)        # debounce: hızlı ardışık tıklamaları birleştir

    def _begin_reconcile(self):
        if not self._reconciling:
            self._reconciling = True
            self._issued = None
            self._phase_ticks = 0
            self._reconcile()

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

    @staticmethod
    def _decide(goal, cur, issued=None):
        """Saf karar: hedefe ulaşıldı mı, değilse hangi komut? Yan etkisiz (test edilebilir).
        asena-on DECLARATIVE — mod değişince usque'yu kendi içinde restart eder
        (clean slate). Bu yüzden 'yanlış modda bağlı' -> yine 'on' (off->on DANSI YOK).
          goal: (transport, scope) | 'off' | None ;  cur: state dict | None
          issued: bu hedef için asena-on zaten çağrıldı mı (h3->h2 fallback kabulü)
        Döner: 'done' | 'on' | 'off'."""
        if goal is None:
            return "done"
        if goal == "off":
            return "done" if cur is None else "off"
        if cur is None:
            return "on"
        if cur["scope"] != goal[1]:
            return "on"                       # scope tutmuyor -> (yeniden) uygula
        if cur["transport"] == goal[0]:
            return "done"
        # transport farklı: hedefi ZATEN issue ettiysek, fark asena-on'un bilinçli
        # h3->h2 fallback'ıdır (UDP bloklu ağ) -> kabul et. Aksi halde transport switch uygula.
        return "done" if issued == goal else "on"

    def _reconcile(self):
        self.refresh()
        goal = self._goal
        action = self._decide(goal, state.current_state(), self._issued)

        if action == "done":
            self._reconciling = False
            was = self._issued
            self._issued = None
            # h3 istendi ama h2'ye düşüldüyse (UDP 443 bloklu ağ) kullanıcıya söyle
            cur = state.current_state()
            if isinstance(was, tuple) and cur and cur["transport"] != was[0]:
                win.notify(APP_NAME, t("notify_transport_fallback",
                                       got=_T_LABEL.get(cur["transport"], cur["transport"])))
            self.refresh()               # son durumu bildir (reconcile bitti)
            return

        # Cihaz kaydı yoksa asena-on'u boşuna çağırma ('config.json yok' ile ölür,
        # kullanıcıya 30sn sonra anlamsız 'zaman aşımı' görünürdü). Kaydı arka
        # planda dene (blocking ağ çağrısı — UI thread'i dondurmasın), bitene dek
        # bu döngüde bekle; başarısızsa AÇIKÇA bildir ve vazgeç.
        if action == "on" and not CONFIG_JSON.exists():
            if self._register_thread is None:
                win.notify(APP_NAME, t("registering"))
                self._register_thread = threading.Thread(
                    target=install.ensure_registered, daemon=True)
                self._register_thread.start()
            elif not self._register_thread.is_alive():
                # thread bitti ama config hâlâ yok -> kayıt başarısız
                self._register_thread = None
                self._reconciling = False
                self._issued = None
                win.notify(APP_NAME, t("register_fail"))
                self.refresh()
                return
            QTimer.singleShot(500, self._reconcile)
            return
        if self._register_thread is not None and not self._register_thread.is_alive():
            self._register_thread = None

        # ISSUE-ONCE: her HEDEF için komut BİR kez verilir. Aynı hedefe tekrar
        # asena-on/off gönderilmez -> thrashing imkânsız. Hedef değişirse
        # (_issued != goal) yeni komut verilir. Mod değişimini asena-on kendi
        # içinde atomik yapar (usque restart + clean slate), o yüzden off->on yok.
        if self._issued != goal:
            if action == "off":
                win.run_script("asena-off.ps1")
            else:
                win.run_script("asena-on.ps1", args=["-Transport", goal[0], "-Scope", goal[1]])
            self._issued = goal
            self._phase_ticks = 0

        # Timeout: asena-on/off beklenen sürede sonuç vermezse vazgeç. asena-on mod
        # değişince clean-slate usque restart yapabilir -> ~30sn'ye kadar meşru.
        self._phase_ticks += 1
        limit = 60 if goal != "off" else 30     # ~30s / ~15s (500ms tik)
        if self._phase_ticks > limit:
            # REVERT-ON-FAILURE: taranmış endpoint tünel açamadıysa (yanlış/ölü IP),
            # register'ın verdiği bilinen-iyi endpoint'e TEK sefer dön ve baştan dene.
            if goal != "off" and endpoint.was_applied():
                endpoint.restore_endpoint()
                win.notify(APP_NAME, t("opt_reverted"))
                win.run_script("asena-off.ps1")       # temiz zemin (varsa yarım usque)
                self._issued = None
                self._phase_ticks = 0
                QTimer.singleShot(1500, self._reconcile)
                return
            self._reconciling = False
            self._issued = None
            tail = _log_tail()
            msg = t("notify_timeout") + (f"\n{tail}" if tail else "")
            win.notify(APP_NAME, msg)
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

        # Ağ-değişimi izleme: bağlıyken ~15s'te bir fiziksel gateway'i kontrol et.
        # state.json'daki gwIP'den farklıysa (WiFi switch / uykudan dönüş / hotspot)
        # endpoint pin + route'lar bayatlar -> arka planda asena-on ile yeniden pinle.
        if active and not self._reconciling and not self._updating:
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
        busy = self._reconciling or self._updating or self._register_thread is not None
        fire, self._wd_wait, self._wd_backoff = self._watchdog_step(
            active, state.read_desired()["connected"], busy, self._wd_wait, self._wd_backoff)
        if fire:
            d = state.read_desired()
            self.set_target(d["transport"], d["scope"])

    def _on_netwatch(self, live_gw):
        self._netwatch_worker = None
        if not live_gw or self._reconciling or self._updating:
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
        win.run_script("asena-on.ps1", args=["-Transport", cur["transport"], "-Scope", cur["scope"]])
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
