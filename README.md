# AsenaPlug

**DPI / DNS censorship‑bypass over Cloudflare MASQUE (`usque`) — a system‑tray app for Windows and Linux, with per‑domain (blacklist) and full‑tunnel modes.**

Traffic looks like ordinary HTTPS (MASQUE over HTTP/2 or HTTP/3), so it survives Turkish ISP DPI/throttling where WireGuard gets shaped. **Physical internet stays the default** — only the domains you list are tunneled, unless you pick full‑tunnel.

🖥️ **Windows 10/11** · 🐧 **Linux — Arch & Debian families**  ·  🌍 5 languages (EN/DE/ES/FR/TR)  ·  🆓 MIT

🇬🇧 [English](#english) · 🇹🇷 [Türkçe](#türkçe)

---

## English

### What you get

- A clickable **system‑tray** indicator (PySide6, no theme dependency): green dot when connected, gray when off, live status while switching.
- **Two independent axes**, both chosen from the tray:
  - **Transport** — HTTP/2 *(default, DPI‑resistant)* or HTTP/3 *(QUIC, lower latency)*
  - **Routing** — Blacklist only *(default)* or Everything (full tunnel)
- **Blacklist** submenu — add a domain or edit the list; changes apply **live, without reconnecting** (hot DNS reload).
- **5‑language UI** — English, Deutsch, Español, Français, Türkçe; picks your OS language on first run (falls back to English), switchable from **Language ›**.
- **Windows only:** self‑updating (GitHub Releases), **Start on boot** toggle, one‑time auto‑setup (no installer), single‑instance, always‑elevated tray.
- **Linux only:** per‑app / per‑interface routing (**Force Asena** submenu), Hyprland autostart.

> AsenaPlug is a real tunnel, not just an SNI trick — it opens IP‑blocked sites too, and hides the traffic. In Turkey a clean, un‑poisoned DNS answer needs the query to travel *through* the tunnel; AsenaPlug does exactly that.

### Transport & Routing modes

| | HTTP/2 (TCP+TLS) | HTTP/3 (QUIC/UDP) |
|---|---|---|
| DPI resistance in TR | **High** — looks like normal HTTPS | Low — UDP 443 often throttled |
| Latency | 2–3 RTT | 0–1 RTT |
| Reliability under shaping | Better | Worse (UDP drops cascade) |

**Default is HTTP/2.** On Windows, if HTTP/3's tunnel doesn't come up in ~4 s (UDP blocked), AsenaPlug **automatically falls back to HTTP/2** in the same connect.

| Routing | Meaning |
|---|---|
| **Blacklist only** *(default)* | Physical internet stays default; only domains in your blacklist go through the tunnel. |
| **Everything** | All traffic through the tunnel (split‑default + endpoint pin), global IPv6 blocked to prevent leaks. |

---

### 🖥️ Windows

#### Install / Update

**Recommended — download the exe:**
1. Grab `AsenaPlug.exe` from the [latest release](https://github.com/KaanAlper/AsenaPlug/releases/latest).
2. Run it → **UAC** prompt → automatic first‑time setup → tray icon appears.

On first run the exe **copies itself to `C:\Program Files\AsenaPlug\`**, makes a **desktop shortcut**, and starts at logon from there — so you can delete the download. Only one tray runs at a time.

**Auto‑update:** the tray checks GitHub Releases (menu → *Check for updates*, plus a silent daily check). New versions download with a progress popup and self‑install — no manual steps. CI builds a fresh signed‑ready exe on every push to `main`.

> **SmartScreen** ("Windows protected your PC") is expected for any *unsigned* open‑source exe — not a bug, not fixable in code. Click **More info → Run anyway**, or `Unblock-File` the download. Free [SignPath OSS](https://signpath.org/open-source) signing is wired into the CI (skipped until you add the `SIGNPATH_*` secrets); a local certificate signs directly via `build.ps1 -CertThumbprint <thumbprint>`. The build already embeds proper version/publisher metadata so UAC shows **AsenaPlug** even while unsigned.

**From source (developers):**
```powershell
cd windows
pip install PySide6 winotify        # or: .\build.ps1  to produce dist\AsenaPlug.exe
pythonw .\AsenaPlug.pyw             # first run: UAC -> setup -> tray
```
`usque.exe`, `wintun.dll`, `dnsproxy.exe` **ship inside the repo** (`windows/bundled/`) — nothing is downloaded at runtime. Python is only needed when running from source.

First run (admin) sets up: binaries + PowerShell scripts → `C:\Program Files\AsenaPlug\`; ACL‑locked shared data → `%ProgramData%\AsenaPlug\` (your `config.json` device key is readable only by Administrators + SYSTEM); Task Scheduler jobs `AsenaPlug_Tray` (elevated tray at logon), `AsenaPlug_RouteSync` (SYSTEM daemon), `AsenaPlug_Rescue` (boot/logon cleanup); and `usque register` → `config.json` — **back this file up.**

#### Daily use (tray menu)

| Action | How |
|---|---|
| Connect / Disconnect | Left‑click the tray icon, or the **green Connect / red Disconnect** menu item |
| Change mode | Tick a Transport/Routing option, then click **Apply** — the menu stays open and shows *Connecting… / Switching…* live |
| Add a blacklist domain | **Blacklist › Add domain…** — applies live (no reconnect) |
| Edit the blacklist file | **Blacklist › Edit…** — changes are watched and applied automatically while you edit |
| Language | **Language ›** — switches instantly, menu stays open |
| Start on boot | Toggle **Start on boot** |
| Check for updates | **Check for updates** |

> ⚠️ **Conflicts with GoodbyeDPI / zapret / ByeDPI.** Those WinDivert tools lower packet TTL, which breaks the MASQUE tunnel (nothing opens). AsenaPlug detects a running one and warns you — **close it** and reconnect.

#### How it works (Windows)

- **Blacklist mode:** the system DNS is **not** touched. Only blacklisted domains are sent (via Windows **NRPT**) to a local `dnsproxy` whose upstream (`1.1.1.1`) is **routed through the tunnel** — answers can't be poisoned. Resolved IPs are pinned into the tunnel by `route-sync`; everything else uses your normal ISP DNS/route. IPv6 for those domains is **fail‑closed** so apps fall back to tunneled IPv4.
- **Everything mode:** split‑default (`0.0.0.0/1` + `128.0.0.0/1`) through the tunnel, endpoint pinned on the physical link (no loop), global IPv6 blocked. **IPv4 is fail‑open:** if `usque` crashes the split‑default routes vanish with the TUN and traffic falls back to your ISP — internet stays up.
- **MTU/MSS** clamped to 1260 so large packets fit the tunnel (otherwise pages load only partially).
- If a connect hangs or `usque` dies, a watchdog + the `AsenaPlug_Rescue` boot task clean up DNS/routes so you never end up stuck offline.
- **Kill‑switch:** a WFP prototype exists in `windows/killswitch/` (Go) but is **disabled** — its filter blocked tunneled traffic; kept for a future Windows‑verified version.

#### Uninstall (Windows)
Admin PowerShell — tears down cleanly (NRPT, IPv6 firewall, routes, DNS) then removes tasks/shortcut/files:
```powershell
& "C:\Program Files\AsenaPlug\scripts\asena-uninstall.ps1"
```
> Deleting the folder *while connected* is wrong — NRPT rules linger and blacklisted domains point at a dead `127.0.0.2`. The script prevents this. Your `config.json` identity is kept; `Remove-Item "C:\ProgramData\AsenaPlug" -Recurse -Force` wipes everything (back it up first).

---

### 🐧 Linux (Arch & Debian families)

One `install.sh` auto‑detects your package manager and installs accordingly:
**Arch family** (pacman — Arch, CachyOS, Manjaro, EndeavourOS…) and **Debian family**
(apt — Debian, Ubuntu, Linux Mint, Pop!_OS, elementary…). Developed/tested on
**CachyOS / Arch + Hyprland**; the Debian path is new (please report issues).

#### Install
```bash
# one‑liner (auto‑detects Arch vs Debian)
curl -fsSL https://raw.githubusercontent.com/KaanAlper/AsenaPlug/main/install.sh | sudo bash
# or from a clone
git clone https://github.com/KaanAlper/AsenaPlug.git && cd AsenaPlug && ./install.sh
```
You're prompted once for `sudo` (the script re‑launches as root) and once for `usque register` (creates `~/config.json`, your device identity — **back it up**).

`usque` comes from the AUR on Arch, and from GitHub Releases (prebuilt Linux binary) everywhere else — mirrored to this repo (`usque-latest`) so install still works if upstream disappears. **Autostart** uses a Hyprland `exec` on Hyprland, otherwise a standard XDG autostart entry (GNOME/KDE/…). The **Force Asena › Add running app** picker needs Hyprland's `hyprctl`; on other desktops use interface/domain routing (the core blacklist feature works everywhere).

The installer adds scoped `sudo` NOPASSWD commands (`asena-on`, `asena-off`, `asena-dns-reload`, …), the PySide6 tray (`~/.local/bin/asena-tray`), a Discord launcher that puts it in the `asena-only.slice` cgroup, config templates, and Hyprland autostart. Re‑running is safe (overwrite‑or‑skip).

#### Daily use

| Action | How |
|---|---|
| Toggle Asena | Left‑click the tray icon |
| Force an app through Asena | **Force Asena › Add running app** |
| Force an interface through Asena | **Force Asena › Add interface…** |
| Blacklist a domain / edit the list | **Blacklist › Add… / Edit…** |
| Terminal | `sudo -n asena-on` (`… http3`) / `sudo -n asena-off` |
| Diagnostics | `tail -f /var/log/usque.log` |

#### How selective routing works
```
physical default route  ─── browser, everything else
asena-only.slice cgroup ─── Discord & Force‑Asena apps (fwmark 0x43 → table 201 → tun0)
dnsmasq + nftables      ─── blacklist domains (asena_hosts IP set → same fwmark)
```
- **Apps** in `~/.config/asena-route.conf` are moved into the `asena-only.slice` cgroup; an nftables cgroup rule marks their packets.
- **Domains:** dnsmasq on `127.0.0.2:53` (upstream via tunnel) populates the `asena_hosts` nftables set from DNS answers; matching IPs get the same fwmark.
- **conntrack mark** keeps an established connection on Asena even if the set entry expires mid‑stream (no leak).
- **IPv6 fail‑closed** (nft `reject`) forces apps back to tunneled IPv4; `rp_filter` is loosened to `2` for the asymmetric routing and restored by `asena-off`.

#### Uninstall (Linux)
```bash
sudo asena-off 2>/dev/null || true
sudo rm /usr/local/bin/asena-{on,off,bypass-reload,dnsmasq-gen,dns-reload} \
        /etc/sudoers.d/asena /etc/dnsmasq-asena.conf
rm ~/.local/bin/asena-tray ~/.local/bin/discord
# remove the asena-tray autostart line from your Hyprland config manually
```
`~/config.json` is left alone — delete only if you don't need that identity.

---

### Architecture (Linux ↔ Windows)

| Feature | Linux | Windows |
|---|---|---|
| Tunnel | `usque` MASQUE | `usque.exe` (same) |
| Selective DNS | dnsmasq + nftset | NRPT → dnsproxy (DNS via tunnel) |
| Selective routing | fwmark + nftset | `/32` routes (route‑sync) |
| Full tunnel | table + default | split‑default `/1` routes |
| IPv6 leak | nft reject | firewall block (fail‑closed) |
| Per‑app routing | cgroup + fwmark | N/A (needs a kernel/WFP driver) |
| Admin commands | sudoers NOPASSWD | elevated tray (logon task, Highest) |
| State detection | `ip link` | ctypes `GetAdaptersAddresses` (no PowerShell) |
| Auto‑update | — | GitHub Releases self‑update |

### Why MASQUE, not WireGuard
Cloudflare's official client uses WireGuard, which is throttled by DPI in Turkey and brittle on Linux. `usque` speaks **MASQUE over HTTP/2 or HTTP/3** — traffic is indistinguishable from normal HTTPS, with a lighter DPI footprint and no background daemon.

### License
MIT — do whatever, no warranty.

---
---

## Türkçe

**Cloudflare MASQUE (`usque`) üzerinden DPI / DNS sansür‑bypass — Windows ve Linux için sistem‑tepsisi uygulaması; alan‑bazlı (blacklist) ve tam‑tünel modlarıyla.**

Trafik sıradan HTTPS gibi görünür (HTTP/2 ya da HTTP/3 üzerinden MASQUE), böylece WireGuard'ın throttle yediği TR DPI'sinde ayakta kalır. **Fiziksel internet varsayılan kalır** — tam‑tünel seçmedikçe yalnız listelediğin alan adları tünelden geçer.

### Neler var

- Tıklanabilir **sistem‑tepsisi** göstergesi (PySide6): bağlıyken yeşil nokta, kapalıyken gri, geçişte canlı durum.
- Tepsiden seçilen **iki bağımsız eksen**:
  - **Transport** — HTTP/2 *(varsayılan, DPI'ya dayanıklı)* veya HTTP/3 *(QUIC, düşük gecikme)*
  - **Yönlendirme** — Sadece blacklist *(varsayılan)* veya Her şey (tam tünel)
- **Blacklist** menüsü — alan ekle ya da listeyi düzenle; değişiklikler **bağlantıyı koparmadan, anında** uygulanır (sıcak DNS yenileme).
- **5 dilli arayüz** — İngilizce, Almanca, İspanyolca, Fransızca, Türkçe; ilk açılışta işletim sistemi dilini seçer (yoksa İngilizce), **Dil ›** menüsünden değişir.
- **Yalnız Windows:** kendini güncelleme (GitHub Releases), **PC başlangıcında başlat**, tek seferlik otomatik kurulum (installer yok), tek örnek, her zaman yönetici tepsi.
- **Yalnız Linux:** uygulama/arayüz bazlı yönlendirme (**Force Asena** menüsü), Hyprland autostart.

> AsenaPlug sadece bir SNI hilesi değil, **gerçek bir tünel** — IP‑bloklu siteleri de açar ve trafiği gizler. TR'de zehirsiz DNS cevabı için sorgunun tünelden geçmesi gerekir; AsenaPlug tam da bunu yapar.

### Transport & Yönlendirme modları

| | HTTP/2 (TCP+TLS) | HTTP/3 (QUIC/UDP) |
|---|---|---|
| TR'de DPI direnci | **Yüksek** — normal HTTPS gibi | Düşük — UDP 443 sık throttle yer |
| Gecikme | 2–3 RTT | 0–1 RTT |
| Baskı altında kararlılık | Daha iyi | Daha kötü (UDP düşmeleri çığ olur) |

**Varsayılan HTTP/2.** Windows'ta HTTP/3'ün tüneli ~4 sn'de gelmezse (UDP bloklu), AsenaPlug aynı bağlanmada **otomatik HTTP/2'ye düşer**.

| Yönlendirme | Anlamı |
|---|---|
| **Sadece blacklist** *(varsayılan)* | Fiziksel internet varsayılan; yalnız blacklist'teki alanlar tünelden geçer. |
| **Her şey** | Tüm trafik tünelden (split‑default + endpoint pin), sızıntıyı önlemek için global IPv6 bloklu. |

---

### 🖥️ Windows

#### Kurulum / Güncelleme

**Önerilen — exe'yi indir:**
1. [Son sürümden](https://github.com/KaanAlper/AsenaPlug/releases/latest) `AsenaPlug.exe`'yi indir.
2. Çalıştır → **UAC** → otomatik ilk kurulum → tepsi ikonu belirir.

İlk çalıştırmada exe **kendini `C:\Program Files\AsenaPlug\`'a kopyalar**, **masaüstü kısayolu** yapar ve logon'da oradan başlar — indirilen dosyayı silebilirsin. Aynı anda tek tray çalışır.

**Otomatik güncelleme:** tray GitHub Releases'i denetler (menü → *Güncellemeleri denetle* + sessiz günlük denetim). Yeni sürüm ilerleme penceresiyle iner ve kendini kurar — elle adım yok. CI, `main`'e her push'ta yeni exe üretir.

> **SmartScreen** ("Windows bilgisayarınızı korudu") *imzasız* her açık kaynak exe için normaldir — hata değil, kodda düzeltilemez. **Ek bilgi → Yine de çalıştır**, ya da indirilen dosyaya `Unblock-File`. Ücretsiz [SignPath OSS](https://signpath.org/open-source) imzası CI'a bağlı (`SIGNPATH_*` secret'ları eklenene kadar atlanır); yerel sertifika `build.ps1 -CertThumbprint <thumbprint>` ile doğrudan imzalar. Build zaten sürüm/yayıncı metadata'sı gömdüğü için UAC imzasızken bile **AsenaPlug** gösterir.

**Kaynaktan (geliştiriciler):**
```powershell
cd windows
pip install PySide6 winotify        # ya da: .\build.ps1  -> dist\AsenaPlug.exe üretir
pythonw .\AsenaPlug.pyw             # ilk çalıştırma: UAC -> kurulum -> tray
```
`usque.exe`, `wintun.dll`, `dnsproxy.exe` **repo'da gömülü** (`windows/bundled/`) — runtime'da hiçbir şey inmez. Python yalnız kaynaktan çalıştırırken gerekir.

İlk çalıştırma (admin): ikililer + PowerShell scriptleri → `C:\Program Files\AsenaPlug\`; ACL‑kilitli paylaşılan veri → `%ProgramData%\AsenaPlug\` (`config.json` cihaz anahtarını yalnız Administrators + SYSTEM okur); Task Scheduler görevleri `AsenaPlug_Tray`, `AsenaPlug_RouteSync`, `AsenaPlug_Rescue`; ve `usque register` → `config.json` — **bu dosyayı yedekle.**

#### Günlük kullanım (tray menüsü)

| İşlem | Nasıl |
|---|---|
| Bağlan / Kes | Tepsi ikonuna sol tık, ya da **yeşil Bağlan / kırmızı Kes** menü öğesi |
| Mod değiştir | Transport/Yönlendirme seçeneğini işaretle, **Değiştir**'e bas — menü açık kalır, *Bağlanıyor… / Değiştiriliyor…* canlı görünür |
| Blacklist'e alan ekle | **Blacklist › Domain ekle…** — anında uygulanır (kes/bağla yok) |
| Blacklist dosyasını düzenle | **Blacklist › Düzenle…** — düzenlerken değişiklikler izlenip otomatik uygulanır |
| Dil | **Dil ›** — anında değişir, menü açık kalır |
| PC başlangıcında başlat | **PC başlangıcında başlat**'ı aç/kapa |
| Güncelleme | **Güncellemeleri denetle** |

> ⚠️ **GoodbyeDPI / zapret / ByeDPI ile çakışır.** Bu WinDivert araçları paket TTL'ini düşürür, bu da MASQUE tünelini bozar (hiçbir şey açılmaz). AsenaPlug çalışanı algılayıp uyarır — **kapat** ve yeniden bağlan.

#### Nasıl çalışır (Windows)

- **Blacklist modu:** sistem DNS'ine **dokunulmaz.** Sadece blacklist alanları Windows **NRPT** ile yerel `dnsproxy`'ye gider; onun upstream'i (`1.1.1.1`) **tünelden** sorulur → cevap zehirlenemez. Çözülen IP'ler `route-sync` ile tünele pinlenir; gerisi normal ISP DNS/route. O alanların IPv6'sı **fail‑closed** → uygulama tünelli IPv4'e düşer.
- **Her şey modu:** split‑default (`0.0.0.0/1` + `128.0.0.0/1`) tünelden, endpoint fiziksel'de pinli (loop yok), global IPv6 bloklu. **IPv4 fail‑open:** usque çökerse split‑default route'lar TUN'la uçar, trafik ISP'ne düşer — internet ayakta kalır.
- **MTU/MSS** 1260'a clamp'lenir (yoksa sayfalar yarım yüklenir).
- Bağlanma asılırsa ya da usque ölürse; watchdog + `AsenaPlug_Rescue` boot görevi DNS/route'ları temizler, çevrimdışı takılı kalmazsın.
- **Kill‑switch:** `windows/killswitch/` altında WFP prototipi var ama **devre dışı** (tünel trafiğini blokluyordu); Windows'ta doğrulanmış bir sürüm için saklı.

#### Kaldırma (Windows)
Yönetici PowerShell — önce düzgün teardown (NRPT, IPv6 firewall, route, DNS), sonra görev/kısayol/dosya:
```powershell
& "C:\Program Files\AsenaPlug\scripts\asena-uninstall.ps1"
```
> Bağlıyken klasörü silmek yanlış — NRPT kalır, blacklist alanları ölü `127.0.0.2`'ye yönlenir. Script bunu önler. `config.json` kimliğin korunur; `Remove-Item "C:\ProgramData\AsenaPlug" -Recurse -Force` her şeyi siler (önce yedekle).

---

### 🐧 Linux (Arch & Debian aileleri)

Tek `install.sh` paket yöneticini otomatik algılar: **Arch ailesi** (pacman — Arch,
CachyOS, Manjaro, EndeavourOS…) ve **Debian ailesi** (apt — Debian, Ubuntu, Linux Mint,
Pop!_OS, elementary…). **CachyOS / Arch + Hyprland**'de geliştirildi/test edildi; Debian
yolu yeni (sorun görürsen bildir).

#### Kurulum
```bash
# tek satır (Arch mı Debian mı otomatik algılar)
curl -fsSL https://raw.githubusercontent.com/KaanAlper/AsenaPlug/main/install.sh | sudo bash
# ya da klondan
git clone https://github.com/KaanAlper/AsenaPlug.git && cd AsenaPlug && ./install.sh
```
Bir kez `sudo` (script kendini root olarak yeniden başlatır) ve bir kez `usque register` (`~/config.json` cihaz kimliğini oluşturur — **yedekle**) sorulur.

`usque` Arch'ta AUR'dan, diğer her yerde GitHub Releases'ten (prebuilt Linux binary) gelir — upstream kaybolsa bile kurulum çalışsın diye bu repoya (`usque-latest`) yedeklenir. **Otomatik başlatma** Hyprland'de `exec`, diğerlerinde standart XDG autostart (GNOME/KDE/…). **Force Asena › Çalışan uygulama ekle** seçicisi Hyprland `hyprctl` gerektirir; diğer masaüstlerinde arayüz/alan yönlendirmesi kullan (asıl blacklist özelliği her yerde çalışır).

Kurulum: kapsamı sınırlı `sudo` NOPASSWD komutları (`asena-on`, `asena-off`, `asena-dns-reload`, …), PySide6 tray (`~/.local/bin/asena-tray`), Discord'u `asena-only.slice` cgroup'una koyan başlatıcı, config şablonları ve Hyprland autostart. Tekrar çalıştırmak güvenli.

#### Günlük kullanım

| İşlem | Nasıl |
|---|---|
| Asena'yı aç/kapa | Tepsi ikonuna sol tık |
| Bir uygulamayı Asena'dan geçir | **Force Asena › Çalışan uygulama ekle** |
| Bir arayüzü Asena'dan geçir | **Force Asena › Arayüz ekle…** |
| Alan blacklist'le / listeyi düzenle | **Blacklist › Ekle… / Düzenle…** |
| Terminal | `sudo -n asena-on` (`… http3`) / `sudo -n asena-off` |
| Tanılama | `tail -f /var/log/usque.log` |

#### Selective yönlendirme nasıl çalışır
```
fiziksel default route  ─── tarayıcı, gerisi
asena-only.slice cgroup ─── Discord & Force‑Asena uygulamaları (fwmark 0x43 → tablo 201 → tun0)
dnsmasq + nftables      ─── blacklist alanları (asena_hosts IP set → aynı fwmark)
```
- `~/.config/asena-route.conf`'taki **uygulamalar** `asena-only.slice` cgroup'una taşınır; nftables cgroup kuralı paketlerini işaretler.
- **Alanlar:** `127.0.0.2:53`'teki dnsmasq (upstream tünelden) DNS cevaplarından `asena_hosts` nft set'ini doldurur; eşleşen IP'ler aynı fwmark'ı alır.
- **conntrack mark**, set girdisi akış ortasında düşse bile kurulu bağlantıyı Asena'da tutar (sızıntı yok).
- **IPv6 fail‑closed** (nft `reject`) uygulamayı tünelli IPv4'e döndürür; `rp_filter` asimetrik yönlendirme için `2`'ye gevşetilir ve `asena-off` geri yükler.

#### Kaldırma (Linux)
```bash
sudo asena-off 2>/dev/null || true
sudo rm /usr/local/bin/asena-{on,off,bypass-reload,dnsmasq-gen,dns-reload} \
        /etc/sudoers.d/asena /etc/dnsmasq-asena.conf
rm ~/.local/bin/asena-tray ~/.local/bin/discord
# asena-tray autostart satırını Hyprland config'inden elle sil
```
`~/config.json` korunur — o kimliğe ihtiyacın yoksa sil.

---

### Neden MASQUE, WireGuard değil
Cloudflare'in resmî istemcisi WireGuard kullanır; TR'de DPI throttle eder ve Linux'ta kırılgandır. `usque`, **HTTP/2 ya da HTTP/3 üzerinden MASQUE** konuşur — trafik normal HTTPS'ten ayırt edilemez, DPI izi hafiftir, arka plan daemon'u yoktur.

### Lisans
MIT — istediğini yap, garanti yok.
