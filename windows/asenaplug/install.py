"""İlk kurulum: binary kopyala, ACL ayarla, Task Scheduler görevlerini kur
(tray logon + route_sync + rescue), blacklist şablonu yaz, usque register.

Tüm binary'ler bundle'dan (PyInstaller _MEIPASS veya repo) kopyalanır —
RUNTIME İNDİRME YOK (eski koddaki dnsproxy indirme + sessiz hata kaldırıldı;
dnsproxy.exe artık bundled/ içinde gelir).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import win
from .paths import (
    INSTALL_DIR, SCRIPTS_DIR, USQUE_EXE, WINTUN_DLL, DNSPROXY_EXE, KILLSWITCH_EXE,
    DATA_DIR, CONFIG_DIR, RUN_DIR, CONFIG_JSON, BLACKLIST_PATH, SETUP_FLAG, LOG_FILE,
    TASKS, APP_NAME,
)

APP_EXE = INSTALL_DIR / f"{APP_NAME}.exe"

CREATE_NO_WINDOW = 0x08000000

SCRIPT_NAMES = [
    "asena-common.ps1",   # ortak fonksiyonlar — diğerleri dot-source eder, İLK kopyalanmalı
    "asena-on.ps1", "asena-off.ps1", "asena-dns-reload.ps1",
    "asena-route-sync.ps1", "asena-rescue.ps1", "asena-uninstall.ps1",
]


def log(msg: str):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        import time
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "  [install] " + msg + "\n")
    except Exception:
        pass


def bundle_path(relative: str) -> Path:
    """PyInstaller _MEIPASS, yoksa repo'daki windows/ dizini."""
    base = getattr(sys, "_MEIPASS", str(Path(__file__).resolve().parent.parent))
    return Path(base) / relative


def needs_setup() -> bool:
    """İlk kurulum mu? SETUP_FLAG (installed.flag) yoksa first-run."""
    return not SETUP_FLAG.exists()


def sync_installed():
    """Kurulu; exe FARKLI yerden çalışıyorsa (dist/update = yeni sürüm geldi)
    kendini + scriptleri + eksik binary'leri Program Files'a tazele + kısayol.
    Program Files'tan çalışıyorsak (autostart) NO-OP -> hızlı açılış.

    version.txt YOK: sürüm zaten exe'de gömülü (APP_VERSION, update denetimi).
    'exe farklı yerden mi çalışıyor' = 'yeni sürüm mü kuruluyor' bilgisi upgrade
    tespiti için yeterli — ayrı bir kurulu-sürüm dosyasına gerek yok."""
    if not getattr(sys, "frozen", False):
        return  # dev (.pyw)
    try:
        if Path(sys.executable).resolve() == APP_EXE.resolve():
            return  # zaten kurulu exe'den (autostart) -> hiçbir şey yapma (hızlı)
    except Exception:
        return
    refresh_scripts()   # script + eksik binary tazele
    install_self()      # yeni exe -> Program Files + kısayol


def refresh_scripts():
    """Her açılışta scriptleri bundle'dan TEKRAR kopyala — Program Files'taki
    scriptler her zaman çalışan kod ile senkron kalsın. (Kurulum bir kez çalıştığı
    için yoksa eski scriptler kalır → seçimler işlenmez.) Eksik binary'leri de
    tamamlar. Elevated gerektirir; değilse sessizce atlar."""
    try:
        SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        for ps in SCRIPT_NAMES:
            src = bundle_path(f"scripts/{ps}")
            if src.exists():
                shutil.copy2(src, SCRIPTS_DIR / ps)
        for fname, dst in (("usque.exe", USQUE_EXE),
                           ("wintun.dll", WINTUN_DLL),
                           ("dnsproxy.exe", DNSPROXY_EXE),
                           ("asena-killswitch.exe", KILLSWITCH_EXE)):  # opsiyonel (Go derlemesi)
            if not dst.exists():
                src = bundle_path(f"bundled/{fname}")
                if src.exists():
                    shutil.copy2(src, dst)
    except Exception as e:
        log(f"refresh_scripts atlandı (admin gerekebilir): {e}")


def run_setup():
    """Admin gerektirir. Tüm kurulum adımlarını sırayla yapar."""
    # 1. Dizinler
    for d in (INSTALL_DIR, SCRIPTS_DIR, DATA_DIR, CONFIG_DIR, RUN_DIR):
        d.mkdir(parents=True, exist_ok=True)

    # 2. Binary'ler (bundled'dan kopya — indirme yok)
    for fname, dst in (("usque.exe", USQUE_EXE),
                       ("wintun.dll", WINTUN_DLL),
                       ("dnsproxy.exe", DNSPROXY_EXE)):
        src = bundle_path(f"bundled/{fname}")
        if not (src.exists() and src.stat().st_size > 0):
            raise FileNotFoundError(
                f"{fname} bundle içinde yok!\nBeklenen: {src}\n"
                "windows/bundled/ içine koy ve tekrar build al."
            )
        shutil.copy2(src, dst)

    # 2b. Kill-switch helper (OPSİYONEL): Go ile derlenmişse gelir. Yoksa kurulum
    #     sürer, sadece kill-switch kullanılamaz (asena-common Enable-KillSwitch
    #     'exe yok' loglar). Böylece Go olmadan da build/kurulum çalışır.
    ks_src = bundle_path("bundled/asena-killswitch.exe")
    if ks_src.exists() and ks_src.stat().st_size > 0:
        shutil.copy2(ks_src, KILLSWITCH_EXE)

    # 3. Scriptler
    for ps in SCRIPT_NAMES:
        src = bundle_path(f"scripts/{ps}")
        if src.exists():
            shutil.copy2(src, SCRIPTS_DIR / ps)

    # 3b. exe'yi Program Files'a kur + masaüstü kısayolu (frozen exe modunda)
    install_self()

    # 4. Paylaşılan veri dizinine ACL: Authenticated Users (S-1-5-11) Modify.
    #    Böylece normal-kullanıcı tray desired.json/blacklist yazar, SYSTEM okur.
    _grant_users_modify(DATA_DIR)

    # 5. Task Scheduler görevleri (SYSTEM)
    _register_tasks()

    # 6. Blacklist şablonu
    if not BLACKLIST_PATH.exists():
        BLACKLIST_PATH.write_text(
            "# Domain blacklist — satır başına bir domain.\n"
            "# Sadece 'Sadece blacklist' (selective) modunda Asena'tan geçer.\n"
            "# Örnek:\n"
            "# nhentai.net\n"
            "# twitter.com\n",
            encoding="utf-8",
        )

    # 7. usque register (cihaz kimliği yoksa). Başarısızlık kurulumu DURDURMAZ:
    #    tray connect öncesi ensure_registered() ile yeniden dener + bildirir.
    if not CONFIG_JSON.exists():
        _run_usque_register()

    # 7b. Cihaz kimliğini (config.json) diğer yerel kullanıcılara kapat (adım 4'teki
    #     geniş grant'i miras yoluyla düzeltir).
    if CONFIG_JSON.exists():
        _protect_identity(CONFIG_JSON)

    # 8. Tamamlandı (autostart = AsenaPlug_Tray logon görevi, adım 5'te kuruldu)
    SETUP_FLAG.touch()


def _grant_users_modify(path: Path):
    try:
        subprocess.run(
            ["icacls", str(path), "/grant", "*S-1-5-11:(OI)(CI)M", "/T", "/C"],
            check=False, capture_output=True, creationflags=CREATE_NO_WINDOW,
        )
    except Exception as e:
        log(f"icacls başarısız: {e}")


def _protect_identity(path: Path):
    """config.json WARP cihaz kimliği + özel anahtarı taşır. DATA_DIR'a verilen
    Authenticated Users:Modify grant'i miras yoluyla bunu da her yerel kullanıcıya
    okunur/yazılır yapıyordu. Tray HER ZAMAN elevated (Administrators) + SYSTEM
    erişir; başka kimseye gerek yok. Mirası kes, yalnız Administrators+SYSTEM bırak."""
    try:
        subprocess.run(
            ["icacls", str(path), "/inheritance:r",
             "/grant:r", "*S-1-5-32-544:F",   # Administrators (elevated tray)
             "/grant:r", "*S-1-5-18:F"],       # SYSTEM (scriptler)
            check=False, capture_output=True, creationflags=CREATE_NO_WINDOW,
        )
    except Exception as e:
        log(f"config.json ACL sertleştirilemedi: {e}")


def trim_log(max_bytes: int = 2_000_000, keep_lines: int = 500):
    """usque.log append-only ve rotasyonsuz -> sınırsız büyür. Açılışta boyut
    eşiğini aşarsa son satırları tutup kırp (best-effort)."""
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > max_bytes:
            lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-keep_lines:]
            LOG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass


def heal_scanned_endpoint():
    """KALDIRILAN endpoint scanner ('Bağlantıyı hızlandır') config.json'daki
    endpoint_v4'ü bozuk bir IP yapıp http3'ü (ve bazen bağlantıyı) kırıyordu.
    Etkilenen kullanıcı bu sürüme güncelleyince ONARILSIN: endpoint.applied işareti
    varsa endpoint.bak'taki orijinal (register) endpoint_v4'ü geri koy — yalnız o
    alanı (regex), private_key'e dokunma. İşaret dosyalarını temizle. Best-effort."""
    applied = CONFIG_DIR / "endpoint.applied"
    bak = CONFIG_DIR / "endpoint.bak"
    if not applied.exists():
        return
    try:
        if bak.exists() and CONFIG_JSON.exists():
            original = bak.read_text(encoding="utf-8").strip()
            if original:
                import re
                text = CONFIG_JSON.read_text(encoding="utf-8-sig")
                text = re.sub(r'("endpoint_v4"\s*:\s*)"[^"]*"',
                              lambda m: m.group(1) + '"' + original + '"', text, count=1)
                CONFIG_JSON.write_text(text, encoding="utf-8")
                log(f"endpoint scanner artığı onarıldı: endpoint_v4 -> {original}")
    except Exception as e:
        log(f"endpoint onarımı atlandı: {e}")
    finally:
        applied.unlink(missing_ok=True)
        bak.unlink(missing_ok=True)


def install_self():
    """Frozen exe'yi Program Files'a kopyala + masaüstü kısayolu (release).
    Dev modunda (.pyw) atlanır. Çalışan kopya kilitliyse sessiz geçer."""
    if not getattr(sys, "frozen", False):
        return
    try:
        src = Path(sys.executable)
        if src.resolve() != APP_EXE.resolve():
            INSTALL_DIR.mkdir(parents=True, exist_ok=True)
            _copy_with_retry(src, APP_EXE)
    except Exception as e:
        log(f"exe Program Files'a kopyalanamadı (çalışan örnek olabilir): {e}")
    _create_desktop_shortcut()


def _copy_with_retry(src: Path, dst: Path, attempts: int = 60, delay: float = 0.5):
    """Güncellemede Program Files exe'yi çalışan (eski) tray kilitler. Yeni exe
    kopyayı, eski tray kapanıp kilit kalkana dek birkaç kez dener. Pencere ~30sn:
    eski tray'in teardown süresinden (asena-off ~20sn) UZUN olmalı, yoksa kopya
    başarısız olup güncelleme sessizce iptal olur (launch_installed eski exe'yi açar)."""
    import time
    last = None
    for _ in range(attempts):
        try:
            shutil.copy2(src, dst)
            return
        except (PermissionError, OSError) as e:
            last = e
            time.sleep(delay)
    if last:
        raise last


def _create_desktop_shortcut():
    try:
        desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
        lnk = desktop / f"{APP_NAME}.lnk"
        ps = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}'); "
              f"$s.TargetPath = '{APP_EXE}'; $s.IconLocation = '{APP_EXE},0'; "
              f"$s.WorkingDirectory = '{INSTALL_DIR}'; $s.Save()")
        subprocess.run(["powershell", "-NonInteractive", "-Command", ps],
                       check=False, capture_output=True, creationflags=CREATE_NO_WINDOW)
    except Exception as e:
        log(f"kısayol oluşturulamadı: {e}")


def running_from_install() -> bool:
    """Çalışan süreç zaten Program Files'taki kurulu exe mi? (dev/.pyw -> True)."""
    if not getattr(sys, "frozen", False):
        return True
    try:
        return Path(sys.executable).resolve() == APP_EXE.resolve()
    except Exception:
        return True


def launch_installed():
    """dist'ten çalışıyorsak Program Files'taki kurulu exe'ye devret (aktif o olsun)."""
    try:
        subprocess.Popen([str(APP_EXE)])
    except Exception as e:
        log(f"kurulu exe başlatılamadı: {e}")


def _tray_launch():
    """(Execute, Argument) — frozen ise Program Files'taki kurulu exe; değilse pythonw + .pyw."""
    if getattr(sys, "frozen", False):
        return str(APP_EXE), ""
    pyw = Path(sys.executable).with_name("pythonw.exe")
    runner = str(pyw if pyw.exists() else sys.executable)
    return runner, f'\"{Path(sys.argv[0]).resolve()}\"'


def _register_tasks():
    # SYSTEM görevleri: route_sync (daemon, asena-on tetikler), rescue (boot+logon)
    sys_defs = [
        (TASKS["route_sync"], "asena-route-sync.ps1", "(New-TimeSpan -Days 3650)", None),
        (TASKS["rescue"],     "asena-rescue.ps1",     "(New-TimeSpan -Minutes 1)", "rescue"),
    ]
    blocks = []
    for name, script, limit, trig in sys_defs:
        trigger_line = ""
        register_trigger = ""
        if trig == "rescue":
            trigger_line = (
                "$t1 = New-ScheduledTaskTrigger -AtStartup\n"
                "$t2 = New-ScheduledTaskTrigger -AtLogOn\n"
            )
            register_trigger = "-Trigger @($t1,$t2) "
        # route_sync bir daemon: çökerse blacklist bakımı reconnect'e kadar durur.
        # Task Scheduler'a otomatik yeniden başlatma ver (rescue kısa ömürlü, gerekmez).
        restart = ""
        if name == TASKS["route_sync"]:
            restart = "-RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) "
        target = SCRIPTS_DIR / script
        blocks.append(f"""
Unregister-ScheduledTask -TaskName '{name}' -Confirm:$false -ErrorAction SilentlyContinue
$a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File "{target}"'
{trigger_line}$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit {limit} {restart}-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$p = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName '{name}' -Action $a {register_trigger}-Settings $s -Principal $p | Out-Null
""")

    # Tray görevi: logon'da YÜKSELTİLMİŞ (Highest) tray, oturum açan kullanıcı olarak.
    # Kullanıcı yerel admin ise UAC promptu olmadan elevated başlar (autostart + privilege).
    exe, arg = _tray_launch()
    arg_part = f"-Argument '{arg}' " if arg else ""
    blocks.append(f"""
Unregister-ScheduledTask -TaskName '{TASKS["tray"]}' -Confirm:$false -ErrorAction SilentlyContinue
$me = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$a = New-ScheduledTaskAction -Execute '{exe}' {arg_part}
$t = New-ScheduledTaskTrigger -AtLogOn -User $me
$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Days 3650) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$s.Priority = 4   # default 7 (below-normal) -> 4: logon kalabalığında daha erken başlar
$p = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName '{TASKS["tray"]}' -Action $a -Trigger $t -Settings $s -Principal $p | Out-Null
""")

    ps_code = "\n".join(blocks)
    subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-NonInteractive", "-Command", ps_code],
        check=True, capture_output=True, creationflags=CREATE_NO_WINDOW,
    )


def _run_usque_register():
    try:
        # config.json'ı paylaşılan CONFIG_DIR'a yaz (SYSTEM task buradan okur).
        # stdin'e "y": register ToS onayı sorar; pencereli exe'de konsol yok,
        # cevapsız kalırsa prompt EOF'la 'no' sayılıp sessizce başarısız oluyordu.
        r = subprocess.run(
            [str(USQUE_EXE), "register"], cwd=str(CONFIG_DIR),
            input="y\n", text=True, capture_output=True, timeout=90,
            creationflags=CREATE_NO_WINDOW,
        )
        if r.returncode != 0 or not CONFIG_JSON.exists():
            out = ((r.stderr or "") + (r.stdout or "")).strip()[-400:]
            log(f"usque register başarısız (exit {r.returncode}): {out}")
    except Exception as e:
        log(f"usque register başarısız: {e} — elle: cd \"{CONFIG_DIR}\" && usque register")


def ensure_registered() -> bool:
    """Cihaz kimliği (config.json) yoksa kaydı dene. İlk kurulumda register
    başarısız kalmış olabilir (ağ yok vb.) — SETUP_FLAG atıldığı için bir daha
    denenmiyordu ve her connect 'config.json yok' ile sessizce timeout'a düşüyordu.
    Tray, connect öncesi bunu çağırır; başarı = dosya gerçekten var."""
    if CONFIG_JSON.exists():
        return True
    _run_usque_register()
    return CONFIG_JSON.exists()
