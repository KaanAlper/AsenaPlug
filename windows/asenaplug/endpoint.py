"""WARP MASQUE endpoint seçimi — HER KULLANICI İÇİN LOKAL hesaplanır.

usque `config.json`'daki `endpoint_v4`, hangi Cloudflare anycast IP'sine
bağlanılacağını belirler. En düşük gecikmeli endpoint kullanıcının ISP'sine ve
coğrafyasına göre DEĞİŞİR — bu yüzden sabit bir "en iyi IP" GÖMMEYİZ; kurulumda
ve kullanıcı istediğinde LOKAL ölçüp seçeriz.

Ölçüm: her adaya TCP 443 connect süresini (birkaç deneme, medyan) ölç. ICMP çoğu
ağda bloklu; TCP-connect RTT'si PoP yakınlığının güvenilir vekilidir. `measure_*`
dışındaki her şey (pick_best, apply/restore/backup) saf/dosya-tabanlıdır ve
Linux'ta unit-test edilebilir.

Not (throughput tavanı): usque'nun QUIC congestion control'ü `reno` — asıl hız
sınırı orada ve dışarıdan ayarlanamaz. endpoint seçimi, o tavanın ALTINDA elde
edilebilecek en büyük ayarlanabilir kazançtır (daha yakın/az yüklü PoP).

GÜVENLİK: seçilen IP MASQUE'ı gerçekten servis etmezse tünel açılmaz. Bu yüzden:
  - adaylar bilinen WARP anycast /24'lerinden seçilir (çoğunlukla MASQUE-capable),
  - config.json'a yazmadan ÖNCE mevcut endpoint `endpoint.bak`'a yedeklenir,
  - uygulanan IP `endpoint.applied` ile işaretlenir; tray connect timeout'unda
    bunu görüp eski endpoint'i geri yükler (revert-on-failure → kendini iyileştirir).
"""
import json
import socket
import statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .paths import CONFIG_JSON, CONFIG_DIR

# Yedek + "uygulandı" işaretçileri (config.json ile aynı dizinde)
BACKUP_FILE  = CONFIG_DIR / "endpoint.bak"       # orijinal endpoint_v4 (register'ın verdiği)
APPLIED_FILE = CONFIG_DIR / "endpoint.applied"   # {"chosen": ip, "original": ip}

ENDPOINT_PORT = 443   # MASQUE (h3/QUIC ve h2/TCP+TLS) 443'te

# Bilinen Cloudflare WARP anycast /24'leri. Dokümante MASQUE default'ları
# 162.159.198.1 (h3) / .2 (h2) burada; aynı prefix'teki komşular da büyük olasılıkla
# MASQUE servis eder. Ulaşılamayan aday zaten ölçümde elenir; yanlış seçim
# revert-on-failure ile kendini iyileştirir. Bu liste TEK düzenleme noktasıdır ve
# gerçek doğrulama Windows'ta bir tarama turuyla yapılmalıdır.
_WARP_SUBNETS = ("162.159.198", "162.159.192", "162.159.195", "162.159.204")
_HOST_SAMPLES = (1, 2, 3, 4, 5, 6, 7, 8)


def candidates() -> list[str]:
    """Ölçülecek aday endpoint IP'leri (tekrarsız, sıralı)."""
    seen: set[str] = set()
    out: list[str] = []
    for net in _WARP_SUBNETS:
        for h in _HOST_SAMPLES:
            ip = f"{net}.{h}"
            if ip not in seen:
                seen.add(ip)
                out.append(ip)
    return out


# ---------------------------------------------------------------- ölçüm (impure)
def measure_tcp(ip: str, port: int = ENDPOINT_PORT, timeout: float = 0.7) -> float | None:
    """Tek TCP connect süresini ms cinsinden döner; ulaşılamazsa None.
    (statistics/perf yerine socket zamanlaması — harici araç yok.)"""
    import time
    start = time.perf_counter()
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return (time.perf_counter() - start) * 1000.0
    except OSError:
        return None


def measure_median(ip: str, tries: int = 2, **kw) -> float | None:
    """Birkaç deneme -> medyan ms (tek sapan ölçümü yumuşatır). Hepsi düşerse None."""
    samples = [m for m in (measure_tcp(ip, **kw) for _ in range(max(1, tries))) if m is not None]
    return statistics.median(samples) if samples else None


def scan(ips: list[str] | None = None, workers: int = 20, **kw) -> list[tuple[str, float]]:
    """Adayları PARALEL ölç, (ip, ms) listesini artan gecikmeyle döner
    (ulaşılamayanlar hariç)."""
    ips = ips or candidates()
    results: list[tuple[str, float]] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for ip, ms in zip(ips, ex.map(lambda x: measure_median(x, **kw), ips)):
            if ms is not None:
                results.append((ip, ms))
    results.sort(key=lambda r: r[1])
    return results


# ---------------------------------------------------------------- seçim (pure)
def pick_best(results: list[tuple[str, float]]) -> str | None:
    """En düşük gecikmeli IP; liste boşsa None. (scan zaten sıralı döner ama
    çağıranın sıralamasına güvenme -> min ile her durumda doğru.)"""
    return min(results, key=lambda r: r[1])[0] if results else None


# ---------------------------------------------------------- config.json r/w (safe)
def _read_endpoint_v4(config_path: Path) -> str | None:
    try:
        return json.loads(Path(config_path).read_text(encoding="utf-8-sig")).get("endpoint_v4") or None
    except (OSError, ValueError):
        return None


def apply_endpoint(chosen: str, config_path: Path = CONFIG_JSON) -> bool:
    """Seçilen IP'yi config.json'daki endpoint_v4'e YAZ (yalnız o alanı; diğer tüm
    anahtarlar -private_key/PEM dahil- json round-trip ile korunur). Yazmadan önce
    orijinali endpoint.bak'a yedekler ve endpoint.applied işaretini bırakır.
    Zaten seçili IP ise no-op (True). Başarı: True."""
    config_path = Path(config_path)
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    original = cfg.get("endpoint_v4") or ""
    if original == chosen:
        return True
    # ilk uygulamada register'ın verdiği orijinali kalıcı yedekle (üzerine yazma)
    if not BACKUP_FILE.exists() and original:
        BACKUP_FILE.parent.mkdir(parents=True, exist_ok=True)
        BACKUP_FILE.write_text(original, encoding="utf-8")
    cfg["endpoint_v4"] = chosen
    try:
        config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except OSError:
        return False
    APPLIED_FILE.parent.mkdir(parents=True, exist_ok=True)
    APPLIED_FILE.write_text(
        json.dumps({"chosen": chosen, "original": original}), encoding="utf-8")
    return True


def was_applied() -> bool:
    """Taranmış bir endpoint uygulanmış mı (revert-on-failure için)?"""
    return APPLIED_FILE.exists()


def clear_applied():
    APPLIED_FILE.unlink(missing_ok=True)


def restore_endpoint(config_path: Path = CONFIG_JSON) -> bool:
    """endpoint.bak'taki orijinal (register) endpoint'i geri yaz. Taranmış endpoint
    tünel açamazsa tray bunu çağırır -> bir sonraki bağlanış bilinen-iyi IP'yi
    kullanır. İşaret temizlenir (tek seferlik geri dönüş, sonsuz döngü olmaz)."""
    config_path = Path(config_path)
    try:
        original = BACKUP_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        clear_applied()
        return False
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
        if original:
            cfg["endpoint_v4"] = original
            config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except (OSError, ValueError):
        clear_applied()
        return False
    clear_applied()
    return True


def optimize(config_path: Path = CONFIG_JSON, **kw) -> tuple[str, float] | None:
    """LOKAL tarama + en iyi endpoint'i uygula. (ip, ms) döner; hiçbir aday
    ulaşılamazsa None (config'e dokunulmaz). Ağ çağrısı içerir — çağıran ARKA
    PLANDA (thread) koşmalı ki UI donmasın. Etki bir sonraki bağlanışta görünür."""
    results = scan(**kw)
    best = pick_best(results)
    if best is None:
        return None
    if apply_endpoint(best, config_path):
        return best, next(ms for ip, ms in results if ip == best)
    return None
