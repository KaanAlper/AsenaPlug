"""Windows'a özgü düşük seviye yardımcılar.

Tasarım notu: adapter tespiti ve listeleme için POWERSHELL SPAWN ETMİYORUZ.
Eski kod her durum kontrolünde / her menü açılışında `powershell.exe` başlatıyordu
(~0.5-1.5sn soğuk başlatma, UI thread'inde) → menü donuyordu. Bunun yerine yerel
IP Helper API'si (iphlpapi.GetAdaptersAddresses) ctypes ile çağrılır → anlık.

ctypes importu Linux'ta da çalışır; `ctypes.windll`/`iphlpapi` yalnızca fonksiyon
içinde kullanılır, böylece bu modül Linux'ta (test için) import edilebilir.
"""
import ctypes
import subprocess
import sys

from .paths import SCRIPTS_DIR, APP_NAME

CREATE_NO_WINDOW = 0x08000000


# --- Yönetici / yükseltme ---
def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def acquire_single_instance(name: str = "Global\\AsenaPlug_SingleInstance") -> bool:
    """Aynı anda tek tray çalışsın (logon görevi + elle açış çakışmasın).
    Mutex bu process ömrü boyunca tutulur. Başka örnek varsa False döner.
    'Global\\' öneki: hızlı kullanıcı değişiminde iki oturumun iki tray + iki usque
    ile aynı sistemi yönetmesini önler (session-local mutex bunu kaçırırdı). Tray
    elevated olduğundan Global namespace'e yazma izni var."""
    try:
        ERROR_ALREADY_EXISTS = 183
        ctypes.windll.kernel32.CreateMutexW(None, False, name)
        return ctypes.windll.kernel32.GetLastError() != ERROR_ALREADY_EXISTS
    except Exception:
        return True  # mutex kurulamadıysa engelleme


def relaunch_as_admin():
    """UAC ile kendini yönetici olarak yeniden başlat. UAC reddedilirse SESSİZCE
    ölme — kullanıcıya neden gerektiğini söyle (yoksa uygulama iz bırakmadan kaybolur)."""
    # frozen: lpFile zaten exe -> argv[0]'ı tekrar geçme. dev: script'i (argv[0]) geç.
    argv = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
    params = " ".join(f'"{a}"' for a in argv)
    # ShellExecuteW: başarı > 32; <=32 = kullanıcı UAC'yi reddetti / yükseltme hatası
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    try:
        if int(rc) <= 32:
            ctypes.windll.user32.MessageBoxW(
                None,
                "AsenaPlug needs administrator rights (UAC) to set up the tunnel and "
                "manage connections.\n\n"
                "AsenaPlug, tüneli kurmak ve bağlantıları yönetmek için yönetici "
                "izni (UAC) gerektirir.",
                "AsenaPlug", 0x10,  # MB_ICONERROR
            )
            sys.exit(1)
    except Exception:
        pass
    sys.exit(0)


# --- Privilege'li script çalıştırma ---
# Tray zaten elevated (logon görevi Highest ile başlatır) → asena-*.ps1 doğrudan
# admin olarak çalışır. Ayrı SYSTEM tetik görevine gerek yok.
def run_script(name: str, args: list[str] | None = None,
               wait: bool = False, timeout: int | None = None):
    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
           "-NonInteractive", "-File", str(SCRIPTS_DIR / name)]
    if args:
        cmd += list(args)
    if wait:
        subprocess.run(cmd, timeout=timeout, capture_output=True,
                       creationflags=CREATE_NO_WINDOW)
    else:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=CREATE_NO_WINDOW)


# --- Adapter tespiti (ctypes, powershell yok) ---
def list_adapters() -> list[str]:
    """Tüm ağ adapterlerinin friendly name listesi (iphlpapi)."""
    from ctypes import wintypes

    AF_UNSPEC = 0
    GAA_FLAG_SKIP_ANYCAST    = 0x0002
    GAA_FLAG_SKIP_MULTICAST  = 0x0004
    GAA_FLAG_SKIP_DNS_SERVER = 0x0008
    ERROR_BUFFER_OVERFLOW = 111
    flags = GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_SKIP_MULTICAST | GAA_FLAG_SKIP_DNS_SERVER

    class IP_ADAPTER_ADDRESSES(ctypes.Structure):
        pass

    # Yalnızca FriendlyName'e kadar olan prefix alanları tanımlıyoruz; API tam
    # struct'ı yazar, biz prefix'i okuruz (x64'te Length+IfIndex = ULONGLONG hizası).
    IP_ADAPTER_ADDRESSES._fields_ = [
        ("Length",                wintypes.ULONG),
        ("IfIndex",               wintypes.DWORD),
        ("Next",                  ctypes.POINTER(IP_ADAPTER_ADDRESSES)),
        ("AdapterName",           ctypes.c_char_p),
        ("FirstUnicastAddress",   ctypes.c_void_p),
        ("FirstAnycastAddress",   ctypes.c_void_p),
        ("FirstMulticastAddress", ctypes.c_void_p),
        ("FirstDnsServerAddress", ctypes.c_void_p),
        ("DnsSuffix",             ctypes.c_wchar_p),
        ("Description",           ctypes.c_wchar_p),
        ("FriendlyName",          ctypes.c_wchar_p),
    ]

    get = ctypes.windll.iphlpapi.GetAdaptersAddresses
    size = wintypes.ULONG(0)
    # 1. çağrı: gerekli buffer boyutunu öğren
    get(AF_UNSPEC, flags, None, None, ctypes.byref(size))
    if size.value == 0:
        return []
    buf = ctypes.create_string_buffer(size.value)
    rc = get(AF_UNSPEC, flags, None,
             ctypes.cast(buf, ctypes.POINTER(IP_ADAPTER_ADDRESSES)),
             ctypes.byref(size))
    if rc != 0:
        return []

    names: list[str] = []
    p = ctypes.cast(buf, ctypes.POINTER(IP_ADAPTER_ADDRESSES))
    while p:
        a = p.contents
        if a.FriendlyName:
            names.append(a.FriendlyName)
        p = a.Next
    return names


def adapter_exists(name: str) -> bool:
    try:
        target = name.lower()
        return any(n.lower() == target for n in list_adapters())
    except Exception:
        return False


def current_default_gateway() -> str | None:
    """FİZİKSEL default gateway'in NextHop IP'si (TUN hariç). Ağ değişince (WiFi
    switch, dock, hotspot) bu değer değişir; tray bunu state.json'daki gwIP ile
    karşılaştırıp route'ları tazeler. powershell spawn eder -> UI thread'inde ASLA
    çağırma, sadece arka plan thread'inden. Bulunamazsa None.
    NOT: full modda fiziksel 0.0.0.0/0 route'u silinmez (split-default /1 ile ezilir),
    bu yüzden Get-NetRoute 0.0.0.0/0 hâlâ fiziksel gateway'i verir."""
    ps = ("$r = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | "
          "Where-Object { $_.NextHop -ne '0.0.0.0' -and $_.InterfaceAlias -ne 'usque' } | "
          "Sort-Object RouteMetric | Select-Object -First 1; "
          "if ($r) { $r.NextHop }")
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=8, creationflags=CREATE_NO_WINDOW,
        )
        gw = (out.stdout or "").strip()
        return gw or None
    except Exception:
        return None


# --- Bildirim ---
def notify(title: str, body: str):
    try:
        from winotify import Notification
        Notification(app_id=APP_NAME, title=title, msg=body, duration="short").show()
    except Exception:
        # winotify yoksa tray fallback'ı tray modülünden gelir
        from . import tray
        if tray.TRAY_REF is not None:
            from PySide6.QtWidgets import QSystemTrayIcon
            tray.TRAY_REF.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 2500)
