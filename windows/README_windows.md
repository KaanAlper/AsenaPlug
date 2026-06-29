# warp-tray — Windows Port

Windows 10/11 portu. Orijinal: [KaanAlper/warp-tray](https://github.com/KaanAlper/warp-tray) (Arch/Hyprland).

**Fiziksel internet default'tur.** Sadece `warp-route.conf`'taki interfaceler ve `warp-blacklist.txt`'teki domainler WARP'tan geçer.

---

## Gereksinimler

| Gereksinim | Açıklama |
|---|---|
| Windows 10/11 x64 | Admin yetkisi gerekli |
| Python 3.10+ | [python.org](https://python.org) |
| Go 1.22+ | usque build için — [go.dev](https://go.dev/dl/) |
| Git | usque clone için |

---

## Kurulum

**Yönetici PowerShell'de:**

```powershell
# Repoyu clone et
git clone https://github.com/KaanAlper/warp-tray.git
cd warp-tray\windows

# Kurulumu başlat (admin gerekli)
.\install.ps1
```

Installer şunları yapar:
1. `usque.exe` — Go ile source'dan build eder (MASQUE/HTTP2 tüneli)
2. `wintun.dll` — TUN adapter driver (Cloudflare/WireGuard kullanan)
3. `dnsproxy.exe` — Domain blacklist için DNS interceptor
4. PowerShell scriptleri kopyalar
5. Task Scheduler görevleri oluşturur (sudoers NOPASSWD eşdeğeri)
6. Python bağımlılıklarını kurar (`PySide6`, `winotify`)
7. `usque register` çalıştırır (`config.json` oluşturur — **YEDEKLE!**)
8. Windows Startup'a ekler

---

## Manuel kurulum (usque.exe build)

Installer build edemediyse kendi makinende:

```bash
# Linux/WSL2'de cross-compile
git clone https://github.com/Diniboy1123/usque.git
cd usque
GOOS=windows GOARCH=amd64 go build -o usque.exe .
```

Sonra `usque.exe` + `wintun.dll`'i `C:\Program Files\usque\` klasörüne koy.

`wintun.dll` için: [wintun.net](https://www.wintun.net/) → `wintun/bin/amd64/wintun.dll`

---

## Linux ↔ Windows karşılaştırması

| Özellik | Linux (orijinal) | Windows (bu port) |
|---|---|---|
| Tünel | `usque` (MASQUE/HTTP2) | `usque.exe` (aynı — Windows build var) |
| Routing | `nftables` + `iproute2` | `netsh` + `New-NetRoute` |
| Domain blacklist | `dnsmasq` + nftset | `dnsproxy` + /32 route tablosu |
| Per-app routing | `systemd cgroup` + fwmark | **YOK** — Windows'ta kernel driver gerekir |
| Interface routing | nftables PREROUTING | route metric manipülasyonu |
| Yönetici komutları | `sudoers NOPASSWD` | Task Scheduler (SYSTEM olarak çalışır) |
| Bildirimler | `notify-send` | `winotify` (Win10 toast) |
| Autostart | Hyprland `exec-once` | Windows Startup klasörü |
| Tünel check | `ip link show tun0` | `Get-NetAdapter 'usque'` |
| Mode detection | `pgrep -af usque` | `Get-WmiObject Win32_Process` |

---

## Kullanım

Tray ikonu sistem tepsisinde görünür (beyaz/gri "W" kapalı, yeşil "W" açık).

| İşlem | Nasıl |
|---|---|
| WARP toggle | Sol tık |
| HTTP/2 bağlan | Sağ tık → HTTP/2 |
| HTTP/3 bağlan | Sağ tık → HTTP/3 |
| Bağlantıyı kes | Sağ tık → Disconnect |
| Interface WARP'a ekle | Sağ tık → Force WARP → Add adapter |
| Domain ekle | Sağ tık → Blacklist → Domain ekle… |
| DNS yenile | Sağ tık → Blacklist → DNS yenile |

### HTTP/2 vs HTTP/3

| | HTTP/2 (TCP+TLS) | HTTP/3 (QUIC/UDP) |
|---|---|---|
| DPI direnci (TR) | Yüksek — normal HTTPS gibi görünür | Düşük — UDP 443 throttle yiyor |
| Gecikme | 2–3 RTT | 0–1 RTT |
| Default | ✓ | |

---

## Domain blacklist

`%APPDATA%\warp-tray\warp-blacklist.txt` — satır başına bir domain:

```
nhentai.net
twitter.com
reddit.com
```

DNS yenile tıklayınca bu domainler `/32` route olarak TUN'a eklenir.  
(Linux'taki nftset gibi gerçek zamanlı değil — her 5 dakikada + manuel yenile.)

---

## Dosyalar

| Yol | Açıklama |
|---|---|
| `C:\Program Files\usque\usque.exe` | MASQUE tünel |
| `C:\Program Files\usque\wintun.dll` | TUN driver |
| `C:\Program Files\usque\dnsproxy.exe` | DNS interceptor |
| `C:\Program Files\usque\scripts\warp-on.ps1` | Tüneli başlat |
| `C:\Program Files\usque\scripts\warp-off.ps1` | Tüneli durdur |
| `C:\Program Files\usque\scripts\warp-bypass-reload.ps1` | Interface routing yenile |
| `C:\Program Files\usque\scripts\warp-dns-reload.ps1` | DNS + route yenile |
| `C:\Program Files\usque\scripts\warp-route-sync.ps1` | Domain IP'lerini route et (5 dk'da bir) |
| `C:\Program Files\usque\warp-tray.pyw` | Tray uygulaması |
| `%APPDATA%\warp-tray\warp-route.conf` | Interface routing config |
| `%APPDATA%\warp-tray\warp-blacklist.txt` | Domain blacklist |
| `%USERPROFILE%\config.json` | usque cihaz kimliği — **YEDEKLE!** |
| `%ProgramData%\usque\usque.log` | Tünel logları |

---

## Kaldırma

```powershell
# Task Scheduler görevleri
"WarpTray_On_HTTP2","WarpTray_On_HTTP3","WarpTray_Off",
"WarpTray_BypassReload","WarpTray_DnsReload","WarpTray_RouteSync" |
    ForEach-Object { Unregister-ScheduledTask -TaskName $_ -Confirm:$false }

# Startup
Remove-Item "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\warp-tray.vbs"

# Program dosyaları
Remove-Item "C:\Program Files\usque" -Recurse
```

`%USERPROFILE%\config.json` silinmez — WARP kimliğin orada.

---

## Lisans

MIT — orijinal proje ile aynı.
