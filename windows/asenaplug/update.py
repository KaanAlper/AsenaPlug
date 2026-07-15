"""GitHub Releases üzerinden otomatik güncelleme: denetle → indir → uygula.

- Ağ: urllib (ek bağımlılık yok). Karşılaştırma: semver tuple.
- İş parçacığı: check/download arka planda (threading) → Qt Signal ile UI'ye döner
  (blocking urllib tray'i dondurmasın).
- UI: ekranın sağ-altında çerçevesiz "tatlı" ilerleme penceresi.
- Uygula: indirilen exe'yi çalıştır → mevcut install_self() onu Program Files'a
  kopyalar (çalışan tray kapanınca kilit kalkar; install_self retry ile bekler).
"""
import json
import re
import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget,
)

from .paths import APP_VERSION, GITHUB_REPO, DATA_DIR

API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
UPDATE_DIR = DATA_DIR / "update"
LAST_CHECK = UPDATE_DIR / "last_check"
AUTO_INTERVAL = 86400          # otomatik denetim en fazla günde 1
_UA = {"User-Agent": "AsenaPlug-Updater"}


# ---------------------------------------------------------------- saf mantık
def parse_version(s: str):
    """'v1.2.3' / '1.2.3' -> (1,2,3). Rakam yoksa (0,)."""
    nums = re.findall(r"\d+", s or "")
    return tuple(int(x) for x in nums) if nums else (0,)


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def check_latest(timeout: int = 8):
    """En son release'i denetle. Yeni + .exe asset'i varsa (tag, url, notes),
    yoksa/erişilemezse None döner."""
    try:
        req = urllib.request.Request(API_LATEST, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except Exception:
        return None
    tag = data.get("tag_name", "")
    if not tag or not is_newer(tag, APP_VERSION):
        return None
    for a in data.get("assets", []):
        if a.get("name", "").lower().endswith(".exe"):
            return tag, a.get("browser_download_url"), (data.get("body") or "").strip()
    return None


def download(url: str, dest: Path, progress_cb=None, timeout: int = 30) -> bool:
    """url -> dest (.part'a yaz, tamamlanınca taşı). progress_cb(pct 0-100)."""
    try:
        UPDATE_DIR.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            total = int(r.headers.get("Content-Length", 0))
            done = 0
            tmp = Path(dest).with_suffix(".part")
            with open(tmp, "wb") as f:
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress_cb and total:
                        progress_cb(min(99, int(done * 100 / total)))
            tmp.replace(dest)
        if progress_cb:
            progress_cb(100)
        return True
    except Exception:
        return False


def auto_due() -> bool:
    """Otomatik denetim vakti geldi mi (son denetimden AUTO_INTERVAL geçti mi)?"""
    try:
        import time
        last = float(LAST_CHECK.read_text(encoding="utf-8").strip())
        return (time.time() - last) >= AUTO_INTERVAL
    except (OSError, ValueError):
        return True


def mark_checked():
    try:
        import time
        UPDATE_DIR.mkdir(parents=True, exist_ok=True)
        LAST_CHECK.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------- arka plan worker'ları
class Checker(QObject):
    """check_latest'i arka planda koşar, sonucu Signal ile UI'ye verir."""
    result = Signal(object)          # (tag, url, notes) | None

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        self.result.emit(check_latest())


class Downloader(QObject):
    progress = Signal(int)           # 0-100
    finished = Signal(bool, str)     # (ok, dest)

    def __init__(self, url: str, dest: Path):
        super().__init__()
        self._url = url
        self._dest = dest

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        ok = download(self._url, self._dest, self.progress.emit)
        self.finished.emit(ok, str(self._dest))


# ------------------------------------------------------ sağ-alt ilerleme UI
class UpdateToast(QWidget):
    """Ekranın sağ-altında çerçevesiz, üstte kalan küçük ilerleme penceresi."""
    def __init__(self, header: str, sub: str):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QWidget(objectName="card")
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 15, 18, 15)
        lay.setSpacing(9)

        self._h = QLabel(header, objectName="h")
        self._s = QLabel(sub, objectName="s")
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        lay.addWidget(self._h)
        lay.addWidget(self._s)
        lay.addWidget(self._bar)

        self.setStyleSheet("""
            #card { background: #1e1e2e; border-radius: 14px; }
            #h { color: #ffffff; font-weight: 600; font-size: 13px; }
            #s { color: #a6adc8; font-size: 11px; }
            QProgressBar {
                background: #313244; border: none; border-radius: 7px;
                height: 14px; text-align: center; color: #ffffff; font-size: 10px;
            }
            QProgressBar::chunk { background: #89b4fa; border-radius: 7px; }
        """)
        self.resize(320, 116)

    def set_pct(self, pct: int):
        self._bar.setValue(pct)

    def set_sub(self, text: str):
        self._s.setText(text)

    def show_bottom_right(self):
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.right() - self.width() - 24, scr.bottom() - self.height() - 24)
        self.show()
