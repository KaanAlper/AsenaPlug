#!/usr/bin/env python3
"""
warp-tray — Windows standalone exe.
İlk çalıştırmada kurulum yapar, sonra tray olarak çalışır.

Bundle içeriği (PyInstaller --add-data ile eklenir):
  bundled/usque.exe    — MASQUE tünel (sen build edersin)
  bundled/wintun.dll   — TUN kernel driver
  scripts/*.ps1        — warp-on/off/bypass-reload/dns-reload/route-sync
"""

import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox, QSystemTrayIcon, QMenu

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
INSTALL_DIR    = Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "usque"
SCRIPTS_DIR    = INSTALL_DIR / "scripts"
APPDATA_DIR    = Path(os.environ.get("APPDATA", "")) / "warp-tray"
PROGRAMDATA    = Path(os.environ.get("ProgramData", "C:\\ProgramData")) / "usque"
RUN_DIR        = PROGRAMDATA / "run"
LOG_FILE       = PROGRAMDATA / "usque.log"
CONFIG_JSON    = Path(os.environ.get("USERPROFILE", "")) / "config.json"
CONF_PATH      = APPDATA_DIR / "warp-route.conf"
BLACKLIST_PATH = APPDATA_DIR / "warp-blacklist.txt"
TUN_NAME       = "usque"

# Task Scheduler görev isimleri
TASKS = {
    "on_http2":      "WarpTray_On_HTTP2",
    "on_http3":      "WarpTray_On_HTTP3",
    "off":           "WarpTray_Off",
    "bypass_reload": "WarpTray_BypassReload",
    "dns_reload":    "WarpTray_DnsReload",
    "route_sync":    "WarpTray_RouteSync",
    "rescue":        "WarpTray_Rescue",
}

# ---------------------------------------------------------------------------
# PyInstaller bundle path helper
# ---------------------------------------------------------------------------
def bundle_path(relative: str) -> Path:
    """PyInstaller _MEIPASS veya script dizini."""
    base = getattr(sys, "_MEIPASS", Path(__file__).parent)
    return Path(base) / relative

# ---------------------------------------------------------------------------
# Admin check & self-elevation
# ---------------------------------------------------------------------------
def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def relaunch_as_admin():
    """UAC ile kendini yönetici olarak yeniden başlat."""
    exe = sys.executable
    args = " ".join(f'"{a}"' for a in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 1)
    sys.exit(0)

# ---------------------------------------------------------------------------
# Kurulum (ilk çalıştırma)
# ---------------------------------------------------------------------------
SETUP_FLAG = PROGRAMDATA / "installed.flag"

def needs_setup() -> bool:
    return not SETUP_FLAG.exists()

def run_setup():
    """
    Bundle'daki dosyaları kur, Task Scheduler görevlerini oluştur.
    Admin yetkisi gerektirir.
    """
    if not is_admin():
        # Kurulum için admin gerekli — UAC iste
        msg = (
            "warp-tray ilk kurulum için yönetici yetkisi gerektirir.\n"
            "Devam etmek istiyor musun?"
        )
        app_tmp = QApplication.instance() or QApplication(sys.argv)
        ret = QMessageBox.question(None, "warp-tray Kurulum", msg)
        if ret != QMessageBox.StandardButton.Yes:
            sys.exit(0)
        relaunch_as_admin()

    # Dizinleri oluştur
    for d in [INSTALL_DIR, SCRIPTS_DIR, PROGRAMDATA, RUN_DIR, APPDATA_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # usque.exe + wintun.dll → Program Files\usque\
    for fname in ["usque.exe", "wintun.dll"]:
        src = bundle_path(f"bundled/{fname}")
        dst = INSTALL_DIR / fname
        if src.exists() and src.stat().st_size > 0:
            shutil.copy2(src, dst)
        else:
            raise FileNotFoundError(
                f"{fname} bundle içinde bulunamadı!\n"
                f"Beklenen konum: {src}\n"
                "bundled/ klasörüne usque.exe ve wintun.dll koy, sonra tekrar build al."
            )

    # PS scriptleri → Program Files\usque\scripts\
    for ps in ["warp-on.ps1", "warp-off.ps1", "warp-bypass-reload.ps1",
               "warp-dns-reload.ps1", "warp-route-sync.ps1"]:
        src = bundle_path(f"scripts/{ps}")
        if src.exists():
            shutil.copy2(src, SCRIPTS_DIR / ps)

    # dnsproxy.exe — runtime'da indir (küçük, ~8MB)
    _download_dnsproxy()

    # Task Scheduler görevleri
    _register_tasks()

    # Config template'leri
    _write_config_templates()

    # usque register (config.json yoksa)
    if not CONFIG_JSON.exists():
        _run_usque_register()

    # Startup VBS
    _add_startup()

    # Kurulum tamamlandı flag
    SETUP_FLAG.touch()

def _download_dnsproxy():
    dst = INSTALL_DIR / "dnsproxy.exe"
    if dst.exists():
        return
    url = "https://github.com/AdguardTeam/dnsproxy/releases/download/v0.71.2/dnsproxy-windows-amd64-v0.71.2.zip"
    import urllib.request, zipfile, io
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = r.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if name.endswith("dnsproxy.exe"):
                    with z.open(name) as src, open(dst, "wb") as out:
                        out.write(src.read())
                    break
    except Exception as e:
        # Kritik değil, domain blacklist çalışmaz ama tünel çalışır
        log(f"dnsproxy indirilmedi: {e} — domain blacklist devre dışı.")

def _register_tasks():
    """Task Scheduler görevleri — SYSTEM olarak çalışır."""
    
    # --- YENİ: Kurtarma (Rescue) scriptini oluştur ---
    rescue_ps1 = SCRIPTS_DIR / "warp-rescue.ps1"
    if not rescue_ps1.exists():
        rescue_ps1.write_text(
            "# Elektrik kesintisi veya çökme sonrası DNS'i otomatiğe alır\n"
            "Get-NetAdapter | Where-Object { $_.Status -eq 'Up' } | ForEach-Object {\n"
            "    Set-DnsClientServerAddress -InterfaceAlias $_.Name -ResetServerAddresses -ErrorAction SilentlyContinue\n"
            "}\n",
            encoding="utf-8"
        )

    task_defs = [
        (TASKS["on_http2"],      f'"{SCRIPTS_DIR}\\warp-on.ps1" -Mode http2'),
        (TASKS["on_http3"],      f'"{SCRIPTS_DIR}\\warp-on.ps1" -Mode http3'),
        (TASKS["off"],           f'"{SCRIPTS_DIR}\\warp-off.ps1"'),
        (TASKS["bypass_reload"], f'"{SCRIPTS_DIR}\\warp-bypass-reload.ps1"'),
        (TASKS["dns_reload"],    f'"{SCRIPTS_DIR}\\warp-dns-reload.ps1"'),
    ]

    ps_register = []
    for name, args in task_defs:
        ps_register.append(f"""
Unregister-ScheduledTask -TaskName '{name}' -Confirm:$false -ErrorAction SilentlyContinue
$a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File {args}'
$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$p = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName '{name}' -Action $a -Settings $s -Principal $p | Out-Null
""")

    # --- GÜNCELLENDİ: Route sync (Watchdog Modu - Tetikleyicisiz, sonsuz süre) ---
    ps_register.append(f"""
Unregister-ScheduledTask -TaskName '{TASKS["route_sync"]}' -Confirm:$false -ErrorAction SilentlyContinue
$a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File "{SCRIPTS_DIR}\\warp-route-sync.ps1"'
$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Days 365)
$p = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName '{TASKS["route_sync"]}' -Action $a -Settings $s -Principal $p | Out-Null
""")

    # --- YENİ: Rescue Task (Sistem açıldığında ve login olunduğunda tetiklenir) ---
    ps_register.append(f"""
Unregister-ScheduledTask -TaskName '{TASKS["rescue"]}' -Confirm:$false -ErrorAction SilentlyContinue
$a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File "{rescue_ps1}"'
$t1 = New-ScheduledTaskTrigger -AtStartup
$t2 = New-ScheduledTaskTrigger -AtLogOn
$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
$p = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName '{TASKS["rescue"]}' -Action $a -Trigger @($t1, $t2) -Settings $s -Principal $p | Out-Null
""")

    ps_code = "\n".join(ps_register)
    subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-NonInteractive", "-Command", ps_code],
        check=True, capture_output=True,
    )

def _write_config_templates():
    if not CONF_PATH.exists():
        CONF_PATH.write_text(
            "# WARP route list.\n"
            "# iface <adapter-adı>  — bu adapter WARP'tan geçer\n"
            "# Örnek:\n"
            "#   iface Wi-Fi 2\n"
            "#   iface vEthernet (WSL)\n",
            encoding="utf-8"
        )
    if not BLACKLIST_PATH.exists():
        BLACKLIST_PATH.write_text(
            "# Domain blacklist — satır başına bir domain\n"
            "# Örnek:\n"
            "# nhentai.net\n"
            "# twitter.com\n",
            encoding="utf-8"
        )

def _run_usque_register():
    try:
        subprocess.run(
            [str(INSTALL_DIR / "usque.exe"), "register"],
            cwd=str(Path(os.environ.get("USERPROFILE", ""))),
            check=True,
        )
    except Exception as e:
        log(f"usque register başarısız: {e} — manuel çalıştır: usque register")

def _add_startup():
    startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    vbs = startup / "warp-tray.vbs"
    exe = sys.executable
    script = str(Path(sys.argv[0]).resolve())
    vbs.write_text(
        f'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.Run """{exe}"" ""{script}""", 0, False\n',
        encoding="ascii"
    )

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def log(msg: str):
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{ts}  {msg}\n")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Task Scheduler ile elevated komut çalıştır
# ---------------------------------------------------------------------------
def run_task(task_key: str):
    subprocess.Popen(
        ["schtasks", "/Run", "/TN", TASKS[task_key]],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

# ---------------------------------------------------------------------------
# WARP durum tespiti
# ---------------------------------------------------------------------------
def tun_exists() -> bool:
    r = subprocess.run(
        ["powershell", "-NonInteractive", "-Command",
         f"(Get-NetAdapter -Name '{TUN_NAME}' -ErrorAction SilentlyContinue) -ne $null"],
        capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return r.stdout.strip().lower() == "true"

def current_mode() -> str | None:
    # PID dosyasının varlığına ve usque'nin gerçekten çalışıp çalışmadığına bak
    pid_file = Path(r"C:\ProgramData\usque\run\usque.pid")
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text())
            if psutil.pid_exists(pid): # psutil kütüphanen varsa
                return "http2"
        except:
            pass
    return None

# ---------------------------------------------------------------------------
# Conf
# ---------------------------------------------------------------------------
def read_conf() -> dict:
    out = {"iface": [], "app": []}
    if not CONF_PATH.exists():
        return out
    for raw in CONF_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].lower() in out:
            out[parts[0].lower()].append(parts[1].strip())
    return out

def write_conf(data: dict):
    header = (
        "# WARP route list.\n"
        "# iface <adapter-adı>  — bu adapter WARP'tan geçer\n\n"
    )
    body = [f"{k} {v}" for k in ("iface", "app") for v in data.get(k, [])]
    CONF_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONF_PATH.write_text(header + "\n".join(body) + "\n", encoding="utf-8")

# ---------------------------------------------------------------------------
# Network adapterleri
# ---------------------------------------------------------------------------
def get_net_adapters() -> list[dict]:
    r = subprocess.run(
        ["powershell", "-NonInteractive", "-Command",
         "Get-NetAdapter | Select-Object Name,InterfaceDescription | ConvertTo-Json"],
        capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        raw = json.loads(r.stdout)
        if isinstance(raw, dict):
            raw = [raw]
        return [{"name": a["Name"], "desc": a.get("InterfaceDescription", "")}
                for a in raw if a.get("Name") and a["Name"] != TUN_NAME]
    except Exception:
        return []

# ---------------------------------------------------------------------------
# Bildirimler
# ---------------------------------------------------------------------------
_tray_ref = None

def notify(title: str, body: str):
    try:
        from winotify import Notification
        Notification(app_id="warp-tray", title=title, msg=body, duration="short").show()
    except Exception:
        if _tray_ref:
            _tray_ref.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 2000)

# ---------------------------------------------------------------------------
# İkon
# ---------------------------------------------------------------------------
ICON_SIZE = 64

def make_icon(connected: bool) -> QIcon:
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(76, 175, 80) if connected else QColor(158, 158, 158)
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

# ---------------------------------------------------------------------------
# Tray
# ---------------------------------------------------------------------------
class WarpTray:
    def __init__(self):
        global _tray_ref
        APPDATA_DIR.mkdir(parents=True, exist_ok=True)

        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.icon_on  = make_icon(True)
        self.icon_off = make_icon(False)

        self.tray = QSystemTrayIcon()
        _tray_ref = self.tray
        self.tray.setIcon(self.icon_off)
        self.tray.activated.connect(self._on_click)

        # Menü
        self.menu = QMenu()

        self.disconnect_action = QAction("Disconnect")
        self.disconnect_action.triggered.connect(self.disconnect)

        self.http2_action = QAction("HTTP/2")
        self.http2_action.setCheckable(True)
        self.http2_action.triggered.connect(lambda: self.set_mode("http2"))

        self.http3_action = QAction("HTTP/3")
        self.http3_action.setCheckable(True)
        self.http3_action.triggered.connect(lambda: self.set_mode("http3"))

        self.bypass_menu    = QMenu("Force WARP")
        self.blacklist_menu = QMenu("Blacklist")

        self.quit_action = QAction("Çıkış")
        self.quit_action.triggered.connect(self.app.quit)

        self.menu.addAction(self.disconnect_action)
        self.menu.addSeparator()
        self.menu.addAction(self.http2_action)
        self.menu.addAction(self.http3_action)
        self.menu.addSeparator()
        self.menu.addMenu(self.bypass_menu)
        self.menu.addMenu(self.blacklist_menu)
        self.menu.addSeparator()
        
        self.menu.addAction(self.quit_action)

        self.tray.setContextMenu(self.menu)
        self.menu.aboutToShow.connect(self._rebuild_menus)

        self._last_mode: str | None = None
        self._initialized = False

        self._rebuild_menus()
        self.refresh()
        self.tray.setVisible(True)

        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)
        self.app.aboutToQuit.connect(self.emergency_cleanup)

    # --- toggle
    def _on_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if current_mode() is None:
                self.set_mode("http2")
            else:
                self.disconnect()

    def disconnect(self):
        run_task("off")
        QTimer.singleShot(2000, self.refresh)

    def set_mode(self, target: str):
        cur = current_mode()
        if cur == target:
            return
        task_key = "on_http2" if target == "http2" else "on_http3"
        if cur is not None:
            run_task("off")
            QTimer.singleShot(2000, lambda: run_task(task_key))
        else:
            run_task(task_key)
        QTimer.singleShot(5000, self.refresh)

    # --- iface
    def add_iface(self, name: str):
        name = name.strip()
        if not name:
            return
        conf = read_conf()
        if name in conf["iface"]:
            notify("Force WARP", f"{name} zaten listede.")
            return
        conf["iface"].append(name)
        write_conf(conf)
        run_task("bypass_reload")
        notify(f"WARP'a eklendi: {name}", "Bu adapter WARP'tan gececek.")
        QTimer.singleShot(300, self.rebuild_bypass_menu)

    def remove_iface(self, name: str):
        conf = read_conf()
        if name not in conf["iface"]:
            return
        conf["iface"].remove(name)
        write_conf(conf)
        run_task("bypass_reload")
        notify(f"WARP'tan cikarildi: {name}", "Adapter artik normal internete gidiyor.")
        QTimer.singleShot(300, self.rebuild_bypass_menu)

    # --- Force WARP menü
    def rebuild_bypass_menu(self):
        self.bypass_menu.clear()
        conf = read_conf()

        if conf["iface"]:
            hdr = self.bypass_menu.addAction("Through WARP:")
            hdr.setEnabled(False)
            for name in conf["iface"]:
                a = self.bypass_menu.addAction(f"  ✓ {name}")
                a.triggered.connect(lambda _=False, n=name: self.remove_iface(n))
            self.bypass_menu.addSeparator()

        add_if = self.bypass_menu.addAction("Add interface…")
        add_if.triggered.connect(self.prompt_add_iface)

        adapters_menu = self.bypass_menu.addMenu("Add adapter ▸")
        conf_ifaces = set(conf.get("iface", []))
        added_any = False
        for a in get_net_adapters():
            if a["name"] in conf_ifaces:
                continue
            act = adapters_menu.addAction(f"{a['name']}  ({a['desc']})")
            act.triggered.connect(lambda _=False, n=a["name"]: self.add_iface(n))
            added_any = True
        if not added_any:
            e = adapters_menu.addAction("(tümü eklendi)")
            e.setEnabled(False)

        note = self.bypass_menu.addAction("ℹ Per-app routing Windows'ta yok")
        note.setEnabled(False)

        self.bypass_menu.addAction("Refresh").triggered.connect(self.rebuild_bypass_menu)

    def prompt_add_iface(self):
        name, ok = QInputDialog.getText(None, "Force WARP — Interface ekle",
                                         "Adapter adı (örn: Wi-Fi 2):")
        if ok and name.strip():
            self.add_iface(name.strip())

    # --- Blacklist menü
    def _rebuild_menus(self):
        self.rebuild_bypass_menu()
        self.rebuild_blacklist_menu()

    def rebuild_blacklist_menu(self):
        self.blacklist_menu.clear()
        count = 0
        if BLACKLIST_PATH.exists():
            lines = [l.strip() for l in BLACKLIST_PATH.read_text(encoding="utf-8").splitlines()
                     if l.strip() and not l.strip().startswith("#")]
            count = len(lines)
        info = self.blacklist_menu.addAction(f"{count} domain kayıtlı")
        info.setEnabled(False)
        self.blacklist_menu.addSeparator()
        self.blacklist_menu.addAction("Düzenle…").triggered.connect(self.open_blacklist)
        self.blacklist_menu.addAction("Domain ekle…").triggered.connect(self.prompt_add_domain)
        self.blacklist_menu.addAction("DNS yenile").triggered.connect(self.reload_dns)

    def open_blacklist(self):
        BLACKLIST_PATH.touch(exist_ok=True)
        os.startfile(str(BLACKLIST_PATH))

    def prompt_add_domain(self):
        domain, ok = QInputDialog.getText(None, "Blacklist — Domain ekle", "Domain:")
        if not ok or not domain.strip():
            return
        domain = domain.strip().lstrip("*.").strip(".")
        if not domain:
            return
        BLACKLIST_PATH.touch(exist_ok=True)
        existing = BLACKLIST_PATH.read_text(encoding="utf-8")
        if domain in existing.splitlines():
            notify("Blacklist", f"{domain} zaten mevcut.")
            return
        with BLACKLIST_PATH.open("a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(domain + "\n")
        notify("Blacklist", f"{domain} eklendi. DNS yenile ile aktif et.")
        self.rebuild_blacklist_menu()

    def reload_dns(self):
        if current_mode() is None:
            notify("WARP Blacklist", "Önce WARP'ı aç.")
            return
        run_task("dns_reload")
        notify("WARP Blacklist", "DNS yenileniyor…")

    # --- Poll
    def refresh(self):
        mode   = current_mode()
        active = mode is not None

        self.tray.setIcon(self.icon_on if active else self.icon_off)
        self.tray.setToolTip(
            f"WARP: Connected ({mode.upper().replace('HTTP','HTTP/')})" if active
            else "WARP: Disconnected"
        )
        self.disconnect_action.setEnabled(active)
        self.http2_action.setChecked(mode == "http2")
        self.http3_action.setChecked(mode == "http3")

        if self._initialized and mode != self._last_mode:
            notify("WARP",
                   f"Connected ({mode.upper().replace('HTTP','HTTP/')})" if mode else "Disconnected")

        self._last_mode   = mode
        self._initialized = True

    def emergency_cleanup(self):
        """Uygulama kapanırken ağ adaptörlerini güvenli duruma getirir."""
        if current_mode() is not None:
            run_task("off")


    def run(self):
        sys.exit(self.app.exec())

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    if needs_setup():
        try:
            run_setup()
        except Exception as e:
            # Kurulum hatası — kullanıcıya göster
            app_tmp = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "warp-tray Kurulum Hatası", str(e))
            sys.exit(1)

    WarpTray().run()

if __name__ == "__main__":
    main()