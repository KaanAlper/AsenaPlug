# AsenaPlug — Windows

**Selective DPI / DNS-censorship bypass over Cloudflare MASQUE (usque) — a Windows system-tray app with per-domain and full-tunnel modes.**

🇬🇧 [English](#english) · 🇹🇷 [Türkçe](#türkçe)

Original Linux project: [KaanAlper/AsenaPlug](https://github.com/KaanAlper/AsenaPlug) (Arch/Hyprland).

---

## English

### Two independent axes
Pick both from the tray menu:

| Axis | Options | Meaning |
|---|---|---|
| **Routing** | **Blacklist only** *(default)* | Physical internet stays default; only domains in `asena-blacklist.txt` go through the tunnel. |
| | **Everything** | All traffic through the tunnel (split-default + endpoint pin). |
| **Transport** | **HTTP/2** *(default)* | TCP+TLS; DPI-resistant (recommended in TR). |
| | **HTTP/3** | QUIC/UDP; lower latency but UDP 443 may be throttled. |

### Requirements
- Windows 10/11 x64 (setup needs admin / UAC)
- Python 3.10+ **only when running from source** (not needed for the PyInstaller exe)
- `PySide6`, `winotify` (pip) — bundled into the exe
- [Go](https://go.dev) **only to build the optional kill-switch helper** — omit it and everything else still builds; the kill-switch is just unavailable

`usque.exe`, `wintun.dll`, `dnsproxy.exe` **ship inside the repo** (`windows/bundled/`) — nothing is downloaded at runtime.

### Install
> **No `install.ps1`.** Setup runs automatically the first time the exe/`.pyw` starts.

**Option A — PyInstaller exe (recommended):**
```powershell
cd windows
.\build.ps1            # builds dist\AsenaPlug.exe (with the wolf icon)
.\dist\AsenaPlug.exe   # first run: UAC -> setup -> tray
```
On first run the exe **copies itself to `C:\Program Files\AsenaPlug\AsenaPlug.exe`**, makes a **desktop shortcut**, and auto-starts at logon from there — so you can delete `dist\`. Only one tray runs at a time.

> **Update:** quit the running tray (**Exit**), then run the new `dist\AsenaPlug.exe` (as admin) → it copies itself to Program Files. Your settings/blacklist/identity are **preserved** (setup runs once; only code is refreshed).

**Option B — from source (development):**
```powershell
cd windows
pip install PySide6 winotify
pythonw .\AsenaPlug.pyw
```

First run (admin) does:
1. `usque.exe` + `wintun.dll` + `dnsproxy.exe` → `C:\Program Files\AsenaPlug\`
2. PowerShell scripts → `C:\Program Files\AsenaPlug\scripts\`
3. ACL on `%ProgramData%\AsenaPlug` (shared data; `config.json` is locked down to Administrators + SYSTEM so the WARP device key isn't readable by other local users)
4. Task Scheduler tasks: `AsenaPlug_Tray` (elevated tray at logon), `AsenaPlug_RouteSync` (SYSTEM daemon), `AsenaPlug_Rescue` (boot/logon cleanup)
5. `usque register` → `%ProgramData%\AsenaPlug\config\config.json` (**back this up!**)

### The blue "Windows protected your PC" (SmartScreen) warning
This is **expected for any unsigned open-source exe** — it is not a bug and cannot be fixed in code. Windows Defender SmartScreen warns on executables that are **not code-signed** and have **no download reputation** yet. Users can run it via **More info → Run anyway**, or unblock the file first:
```powershell
Unblock-File "$env:USERPROFILE\Downloads\AsenaPlug.exe"
```
> Note: because the CI bumps the version and produces a fresh binary on every push, SmartScreen reputation never accumulates while the exe stays unsigned — so the warning is *permanent* without signing.

**To remove the warning for good, sign the exe** (ranked by cost):
- **[SignPath.io Foundation](https://about.signpath.io/product/open-source)** — *free* code signing for open-source projects (this repo qualifies: public + MIT). Removes "unknown publisher"; SmartScreen reputation then builds over time.
- **[Azure Trusted Signing](https://learn.microsoft.com/azure/trusted-signing/)** — ~$15/mo, Microsoft-backed, reputation builds faster.
- **EV certificate** — ~$300–600/yr + hardware token, but **zero warning from day one**.

**Free path — SignPath.io Foundation** (this is what the CI is wired for):
1. Apply for the free OSS program at [signpath.org/open-source](https://signpath.org/open-source) and get the project approved (they review — a brand-new/small repo may take time or be declined).
2. In the SignPath dashboard: create the project, set the *trusted build system* to GitHub Actions for this repo, add an artifact configuration + a signing policy.
3. Add a repo **secret** `SIGNPATH_API_TOKEN`, and repo **variables** `SIGNPATH_ORG_ID`, `SIGNPATH_PROJECT_SLUG`, `SIGNPATH_POLICY_SLUG`.
4. Push to `main` → the release is signed automatically. The workflow **skips signing when `SIGNPATH_API_TOKEN` is absent**, so nothing breaks meanwhile.

> SignPath issues an **OV**-class certificate, so "unknown publisher" goes away immediately but SmartScreen *reputation* still builds up over downloads/time (not instant like an EV cert).

If you instead have a local certificate (any OV/EV), local builds sign directly:
```powershell
.\build.ps1 -CertThumbprint <your-cert-thumbprint>
```
The build already embeds proper version/publisher metadata (CompanyName, ProductName, version) so the UAC prompt and file properties show **AsenaPlug** instead of a blank publisher — a smaller trust signal that works even while unsigned.

### How it works
- **Blacklist mode:** the system DNS is **not** touched. Only blacklisted domains are sent (via Windows **NRPT**) to a local `dnsproxy` whose upstream (`1.1.1.1`) is **routed through the tunnel** — so DNS answers can't be poisoned. Resolved IPs are routed through the tunnel (`route-sync`). Everything else uses your normal ISP DNS/route. IPv6 for blacklisted domains is **fail-closed** (firewall) so apps fall back to tunneled IPv4.
- **Everything mode:** split-default (`0.0.0.0/1`+`128.0.0.0/1`) through the tunnel, endpoint pinned on the physical link (no loop), global IPv6 blocked (no leak; usque is IPv4-only). **IPv4 is fail-*open* by default:** if usque crashes the split-default routes vanish with the TUN and traffic falls back to your ISP (internet stays up — the same philosophy as the rescue task).
- **Kill-switch (optional, Everything mode only):** enable it from the tray to flip IPv4 to fail-*closed*. It's a small Go helper (`asena-killswitch.exe`) that holds a **WFP dynamic session** — permit filters for the TUN, usque, the WARP endpoint, LAN and DHCP, then block everything else (*permit-above-block* via WFP weights — the same technique Mullvad/WireGuard use, which a plain Windows Firewall rule can't do since Block always wins there). If the tunnel drops, non-tunnel traffic stops instead of leaking to your ISP. Because it's a **dynamic** session, **every filter is removed automatically the moment the helper process exits** — kill, crash, or power-loss-then-reboot — so the kill-switch **cannot brick your internet**. **Off by default.** Building the helper needs [Go](https://go.dev) on the build machine (CI installs it automatically; if `go` is absent everything else still builds and the kill-switch is simply unavailable).
- **MTU/MSS** clamped (1260) so large packets fit the tunnel (otherwise pages load only partially).

### Architecture (Linux ↔ Windows)
| Feature | Linux | Windows (this port) |
|---|---|---|
| Tunnel | `usque` MASQUE | `usque.exe` (same) |
| Selective DNS | dnsmasq + nftset | NRPT → dnsproxy (DNS via tunnel) |
| Selective routing | fwmark + nftset | `/32` routes (route-sync) |
| Full tunnel | table + default | split-default `/1` routes |
| IPv6 leak | nft reject | firewall block (fail-closed) |
| **Per-app routing** | cgroup + fwmark | **N/A** (needs a kernel/WFP driver) |
| Admin commands | sudoers NOPASSWD | elevated tray (logon task, Highest) |
| State detection | `ip link` | ctypes `GetAdaptersAddresses` (no powershell) |

### Uninstall
**Admin PowerShell** (one command — first tears down cleanly: NRPT, IPv6 firewall, routes, DNS; then removes tasks/shortcut/files):
```powershell
& "C:\Program Files\AsenaPlug\scripts\asena-uninstall.ps1"
```
> Deleting the folder while connected is **wrong**: NRPT rules linger and blacklisted domains point at a dead `127.0.0.2` (won't resolve). The script prevents this.

Your identity (`config.json`) is kept. To remove everything (back it up first!):
```powershell
Remove-Item "C:\ProgramData\AsenaPlug" -Recurse -Force
```

### License
MIT — same as the original project.

---

## Türkçe

### İki bağımsız eksen
Tray menüsünden ikisini de seç:

| Eksen | Seçenekler | Anlamı |
|---|---|---|
| **Routing** | **Sadece blacklist** *(default)* | Fiziksel internet default; yalnız `asena-blacklist.txt`'teki domainler tünelden geçer. |
| | **Her şey** | Tüm trafik tünelden geçer (split-default + endpoint pin). |
| **Transport** | **HTTP/2** *(default)* | TCP+TLS; DPI'ya dayanıklı (TR'de önerilir). |
| | **HTTP/3** | QUIC/UDP; daha düşük gecikme ama UDP 443 throttle yiyebilir. |

### Gereksinimler
- Windows 10/11 x64 (kurulum admin / UAC ister)
- Python 3.10+ **yalnız kaynaktan çalıştırırken** (PyInstaller exe için gerekmez)
- `PySide6`, `winotify` (pip) — exe içine paketlenir
- [Go](https://go.dev) **yalnız opsiyonel kill-switch helper'ını derlemek için** — koymazsan gerisi yine build olur, sadece kill-switch kullanılamaz

`usque.exe`, `wintun.dll`, `dnsproxy.exe` **repo'da gömülü gelir** (`windows/bundled/`) — runtime'da hiçbir şey indirilmez.

### Kurulum
> **`install.ps1` YOK.** Kurulum, exe/`.pyw` ilk çalıştığında otomatik yapılır.

**Seçenek A — PyInstaller exe (önerilen):**
```powershell
cd windows
.\build.ps1            # dist\AsenaPlug.exe üretir (kurt ikonlu)
.\dist\AsenaPlug.exe   # ilk çalıştırma: UAC -> kurulum -> tray
```
İlk çalıştırmada exe **kendini `C:\Program Files\AsenaPlug\AsenaPlug.exe`'ye kopyalar**, **masaüstü kısayolu** yapar ve logon'da oradan otomatik başlar — `dist\`'i silebilirsin. Aynı anda tek tray çalışır.

> **Güncelleme:** çalışan tray'i **Çıkış**'tan kapat, sonra yeni `dist\AsenaPlug.exe`'yi (yönetici) çalıştır → kendini Program Files'a kopyalar. Ayarların/blacklist/kimliğin **korunur** (kurulum bir kez çalışır; sadece kod tazelenir).

**Seçenek B — kaynaktan (geliştirme):**
```powershell
cd windows
pip install PySide6 winotify
pythonw .\AsenaPlug.pyw
```

İlk çalıştırma (admin) şunları yapar:
1. `usque.exe` + `wintun.dll` + `dnsproxy.exe` → `C:\Program Files\AsenaPlug\`
2. PowerShell scriptleri → `C:\Program Files\AsenaPlug\scripts\`
3. `%ProgramData%\AsenaPlug`'a ACL (paylaşılan veri; `config.json` yalnız Administrators + SYSTEM'e kısıtlı — WARP cihaz anahtarı diğer yerel kullanıcılara okunmaz)
4. Task Scheduler: `AsenaPlug_Tray` (logon'da elevated tray), `AsenaPlug_RouteSync` (SYSTEM daemon), `AsenaPlug_Rescue` (boot/logon temizlik)
5. `usque register` → `%ProgramData%\AsenaPlug\config\config.json` (**YEDEKLE!**)

### Mavi "Windows bilgisayarınızı korudu" (SmartScreen) uyarısı
Bu, **imzasız her açık kaynak exe için normaldir** — kod hatası değildir ve kodda düzeltilemez. Windows Defender SmartScreen, **code-signing imzası olmayan** ve henüz **indirme itibarı bulunmayan** exe'lere uyarı verir. Kullanıcı **Ek bilgi → Yine de çalıştır** ile açabilir; ya da dosyanın engelini önce kaldırabilir:
```powershell
Unblock-File "$env:USERPROFILE\Downloads\AsenaPlug.exe"
```
> Not: CI her push'ta sürümü artırıp yeni binary ürettiği için, exe imzasız kaldıkça SmartScreen itibarı hiç birikmez — yani imzalamadan uyarı *kalıcıdır*.

**Uyarıyı tamamen kaldırmak için exe'yi imzala** (maliyete göre):
- **[SignPath.io Foundation](https://about.signpath.io/product/open-source)** — açık kaynak projelere *ücretsiz* code signing (bu repo uygun: public + MIT). "Bilinmeyen yayıncı"yı kaldırır; SmartScreen itibarı zamanla oluşur.
- **[Azure Trusted Signing](https://learn.microsoft.com/azure/trusted-signing/)** — ~15$/ay, Microsoft imzalı, itibar daha hızlı gelir.
- **EV sertifikası** — ~300-600$/yıl + donanım token, ama **ilk günden sıfır uyarı**.

**Ücretsiz yol — SignPath.io Foundation** (CI bunun için bağlı):
1. [signpath.org/open-source](https://signpath.org/open-source)'tan ücretsiz OSS programına başvur ve projeyi onaylat (inceliyorlar — yeni/küçük repo zaman alabilir ya da reddedilebilir).
2. SignPath panelinde: projeyi oluştur, bu repo için *trusted build system*'i GitHub Actions yap, bir artifact yapılandırması + signing policy ekle.
3. Repo'ya **secret** `SIGNPATH_API_TOKEN`, **variable** olarak `SIGNPATH_ORG_ID`, `SIGNPATH_PROJECT_SLUG`, `SIGNPATH_POLICY_SLUG` ekle.
4. `main`'e push → release otomatik imzalanır. `SIGNPATH_API_TOKEN` yoksa workflow **imzalamayı atlar**, bu sırada hiçbir şey bozulmaz.

> SignPath **OV** sınıfı sertifika verir; "bilinmeyen yayıncı" hemen kalkar ama SmartScreen *itibarı* yine indirmelerle/zamanla oluşur (EV gibi anında değil).

Elinde yerel bir sertifika (OV/EV) varsa yerel build doğrudan imzalar:
```powershell
.\build.ps1 -CertThumbprint <sertifika-thumbprint>
```
Build zaten düzgün sürüm/yayıncı metadata'sı (CompanyName, ProductName, sürüm) gömüyor; böylece UAC dialogu ve dosya özelliklerinde boş yayıncı yerine **AsenaPlug** görünür — imzasızken bile işe yarayan küçük bir güven sinyali.

### Nasıl çalışır
- **Blacklist modu:** sistem DNS'ine **dokunulmaz**. Sadece blacklist domainleri Windows **NRPT** ile yerel `dnsproxy`'ye gider; onun upstream'i (`1.1.1.1`) **tünelden** sorulur → DNS zehirlenemez. Çözülen IP'ler tünele route edilir (`route-sync`). Gerisi normal ISP DNS/route kullanır. Blacklist domainlerinin IPv6'sı **fail-closed** (firewall) → uygulama tünelli IPv4'e düşer.
- **Her şey modu:** split-default (`0.0.0.0/1`+`128.0.0.0/1`) tünelden, endpoint fiziksel'de pinli (loop yok), global IPv6 bloklu (leak yok; usque IPv4-only). **IPv4 varsayılan fail-*open*:** usque çökerse split-default route'lar TUN'la birlikte uçar ve trafik ISP'ne düşer (internet ayakta kalır — rescue göreviyle aynı felsefe).
- **Kill-switch (opsiyonel, sadece Her şey modu):** tepsiden aç → IPv4 fail-*closed* olur. Küçük bir Go helper'ı (`asena-killswitch.exe`) bir **WFP dynamic session** tutar: TUN / usque / WARP endpoint / LAN / DHCP'ye izin, gerisine blok (*permit-above-block* — WFP ağırlıklarıyla; Mullvad/WireGuard'ın yöntemi. Sıradan Windows Firewall bunu yapamaz çünkü orada Block hep kazanır). Tünel düşerse tünelsiz trafik ISP'ye sızmak yerine durur. **Dynamic** oturum olduğu için **helper süreci ölür ölmez tüm filtreler otomatik silinir** — kill, çökme veya güç kesintisi+reboot — yani kill-switch **internetini brick'leyemez**. **Varsayılan kapalı.** Helper'ı derlemek için build makinesinde [Go](https://go.dev) gerekir (CI otomatik kurar; `go` yoksa gerisi yine build olur, sadece kill-switch kullanılamaz).
- **MTU/MSS** clamp (1260) → büyük paketler tünele sığar (yoksa sayfalar yarım yüklenir).

### Mimari (Linux ↔ Windows)
| Özellik | Linux | Windows (bu port) |
|---|---|---|
| Tünel | `usque` MASQUE | `usque.exe` (aynı) |
| Selective DNS | dnsmasq + nftset | NRPT → dnsproxy (DNS tünelden) |
| Selective routing | fwmark + nftset | `/32` route (route-sync) |
| Full tunnel | tablo + default | split-default `/1` route |
| IPv6 leak | nft reject | firewall block (fail-closed) |
| **Per-app routing** | cgroup + fwmark | **YOK** (kernel/WFP sürücüsü gerekir) |
| Admin komut | sudoers NOPASSWD | elevated tray (logon görevi, Highest) |
| Durum tespiti | `ip link` | ctypes `GetAdaptersAddresses` (powershell yok) |

### Kaldırma
**Yönetici PowerShell** (tek komut — önce düzgün teardown: NRPT, IPv6 firewall, route, DNS; sonra görev/kısayol/dosya):
```powershell
& "C:\Program Files\AsenaPlug\scripts\asena-uninstall.ps1"
```
> Bağlıyken klasörü silmek **yanlış**: NRPT kalır, blacklist domainleri ölü `127.0.0.2`'ye yönlenir (çözülmez). Script bunu önler.

Kimliğin (`config.json`) korunur. Tamamen silmek için (yedekle!):
```powershell
Remove-Item "C:\ProgramData\AsenaPlug" -Recurse -Force
```

### Lisans
MIT — orijinal proje ile aynı.
