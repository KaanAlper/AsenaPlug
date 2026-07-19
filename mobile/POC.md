# AsenaPlug Mobil — PoC Planı (usque API'si doğrulanmış)

> Bu belge **gerçek usque kaynağı incelenerek** yazıldı. Ana risk (usque CLI-only mu?)
> **ÇÖZÜLDÜ**: usque'nun temiz, yeniden-kullanılabilir bir `api` paketi var.

---

## 1. Doğrulanan usque API'si (kanıt)

`cmd/socks.go`'nun yaptığı, birebir bizim ihtiyacımız:

```go
// gvisor sanal TUN + tünel netstack'i (tunNet = TÜNEL DIALER + RESOLVER)
tunDev, tunNet, err := netstack.CreateNetTUN(localAddresses, dnsAddrs, mtu)

// MASQUE tünelini kur + sürekli tut (arka planda)
go api.MaintainTunnel(ctx, api.MaintainTunnelConfig{
    TLSConfig:       tlsConfig,          // api.PrepareTlsConfig(...) ile
    Endpoint:        endpoint,           // config.json'dan
    Device:          api.NewNetstackAdapter(tunDev),
    MTU:             1280,
    UseHTTP2:        true,               // TR: HTTP/2 (UDP bloksa)
    AlwaysReconnect: true,
    KeepalivePeriod: 30 * time.Second,
})

// tunNet.DialContext(ctx,"tcp",addr) => MASQUE TÜNELİNDEN çıkar   ← selective'in kalbi
// tunNet.LookupContextHost(ctx,domain) => TÜNELDEN temiz DNS       ← zehirlenmez
```

**Elimizdeki hazır parçalar:**
| usque sembolü | ne verir |
|---|---|
| `api.PrepareTlsConfig` | MASQUE için TLS (cihaz anahtarından) |
| `api.MaintainTunnel` + `MaintainTunnelConfig` | tüneli kur + reconnect + keepalive |
| `api.NewNetstackAdapter(tunDev)` | gvisor TUN → tünel cihazı |
| `netstack.CreateNetTUN` → `tunNet` | **tünel dialer** (`DialContext`) + **resolver** (`LookupContextHost`) |
| `internal.TunnelDNSResolver` | tünelden DNS çözücü (istersek) |
| Android arm64 binary + gvisor + wireguard-go(`tun.CreateTUNFromFile`) | mobil temeller |

→ **usque'yu neredeyse hiç değiştirmeden** kütüphane olarak kullanabiliriz (belki sadece
`config.json`'ı dosya yerine bellek/reader'dan okuyan küçük bir yardımcı).

---

## 2. Selective router (mobil, gerçek API'yle)

```
VpnService TUN fd  ──►  Go tun2socks (Outline SDK)  ──►  her flow için KARAR:
                                                          ├─ dstIP ∈ blacklistSet →  tunNet.DialContext  (MASQUE tünel)
                                                          └─ değilse              →  directDial + protectFd()  (native, tünelsiz)

DNS sorgusu ──► domain blacklist'te mi?
               ├─ evet → tunNet.LookupContextHost (temiz) + ipSet.add(sonuç, ttl≥1h)
               └─ hayır → sistem/DoH (hızlı)
```

Masaüstündeki nftset/NRPT mantığının aynısı; sadece "nftset" → in-memory `ipSet`,
"tünel route" → `tunNet.DialContext`, "direkt" → `protect()`'li soket.

**Kurallar (masaüstünden taşınan):** conntrack kalıcılık (flow bir kez tünele atandıysa
biter bitmez), IPv6 fail-closed, HTTP/3→HTTP/2 fallback (`UseHTTP2` deneme), reconnect
(`AlwaysReconnect`).

---

## 3. Go çekirdek iskeleti (`core/asenacore.go`, gomobile-export)

```go
package asenacore

// gomobile bind bunu Kotlin'e AsenaCore olarak açar.
// Kotlin: val core = Asenacore.newCore(); core.start(tunFd, configJson, blacklistJson)

type Core struct {
    cancel   context.CancelFunc
    tunNet   *netstack.Net        // usque tünel dialer/resolver
    ipSet    *ipset.Set           // blacklist domainlerin çözülmüş IP'leri (timeout'lu)
    matcher  *domain.Matcher      // apex + *.subdomain eşleştirici
    protect  ProtectFunc          // Kotlin verir: VpnService.protect(fd)
}

// ProtectFunc: direkt soketlerin TUN'u BAYPAS etmesi için (Kotlin tarafı implement eder).
type ProtectFunc interface { Protect(fd int32) bool }

func (c *Core) Start(tunFd int, configJson string, blacklistJson string, p ProtectFunc) error {
    ctx, cancel := context.WithCancel(context.Background())
    c.cancel = cancel; c.protect = p
    c.matcher = domain.NewMatcher(parseBlacklist(blacklistJson))
    c.ipSet   = ipset.New()

    // (a) usque config (cihaz anahtarı) — dosya yerine bellek
    cfg := loadUsqueConfig(configJson)           // TODO: usque config loader'ını reader'a uyarla
    tls, _ := api.PrepareTlsConfig(cfg.PrivKey, cfg.PeerPubKey, cfg.Cert, cfg.SNI, false)

    // (b) usque tünelini kur (tunNet = TÜNEL DIALER)
    tunDev, tunNet, _ := netstack.CreateNetTUN(cfg.LocalAddrs, cfg.DNSAddrs, 1280)
    c.tunNet = tunNet
    go api.MaintainTunnel(ctx, api.MaintainTunnelConfig{
        TLSConfig: tls, Endpoint: cfg.Endpoint, Device: api.NewNetstackAdapter(tunDev),
        MTU: 1280, UseHTTP2: true, AlwaysReconnect: true, KeepalivePeriod: 30*time.Second,
    })

    // (c) VpnService fd üstünde OUR tun2socks (Outline SDK) — dialer'ımız selective
    tunOS, _ := tun.CreateTUNFromFile(os.NewFile(uintptr(tunFd), "tun"), 1280) // wireguard-go
    return runTun2Socks(ctx, tunOS, c.selectDialer, c.onDnsQuery)              // TODO: Outline network pkg
}

// selectDialer: her yeni bağlantıda çağrılır -> tünel mi direkt mi?
func (c *Core) selectDialer(ctx context.Context, dst netip.AddrPort) (net.Conn, error) {
    if c.ipSet.Contains(dst.Addr()) {                      // blacklist domainin IP'si
        return c.tunNet.DialContext(ctx, "tcp", dst.String())   // → MASQUE TÜNEL
    }
    return c.directDial(ctx, dst)                          // → DİREKT (protect'li), native hız
}

// onDnsQuery: blacklist domainleri tünelden çöz + IP'yi işaretle
func (c *Core) onDnsQuery(domain string) ([]netip.Addr, bool) {
    if !c.matcher.Match(domain) { return nil, false }      // false => sistem DNS'e bırak
    ips, _ := c.tunNet.LookupContextHost(context.Background(), domain) // TEMİZ, zehirlenmez
    c.ipSet.AddAll(ips, time.Hour)                         // conntrack-benzeri kalıcılık
    return ips, true
}

func (c *Core) Stop() { if c.cancel != nil { c.cancel() } }
```

> `runTun2Socks` + `directDial(protect)` = Outline SDK'nın `network`/`transport` paketleriyle
> doldurulacak (Apache-2). TODO işaretleri: usque config loader'ı reader'a uyarlama, Outline
> dialer arayüzü, UDP/DNS pompası. Hepsi mekanik — mimari sağlam.

---

## 4. Kotlin VpnService iskeleti (`android/AsenaVpnService.kt`)

```kotlin
class AsenaVpnService : VpnService() {
    private var core: Core? = null

    override fun onStartCommand(i: Intent?, f: Int, id: Int): Int {
        val tun = Builder()
            .setSession("AsenaPlug")
            .addAddress("10.111.0.2", 32)
            .addDnsServer("10.111.0.53")     // DNS'i kendi resolver'ımıza al
            .addRoute("0.0.0.0", 0)          // her paketi yakala (userspace'te ayrıştır)
            .setMtu(1280)
            .establish() ?: return START_NOT_STICKY

        core = Asenacore.newCore().apply {
            start(tun.fd, readConfigJson(), readBlacklistJson(),
                  object : ProtectFunc { override fun protect(fd: Int) = protect(fd) })
        }
        startForeground(1, buildNotification("Bağlı · HTTP/2 · Sadece blacklist"))
        return START_STICKY
    }

    override fun onDestroy() { core?.stop(); super.onDestroy() }
}
```

---

## 5. Build (gomobile + gradle)

```bash
# 1) Go çekirdeğini AAR'a derle (usque + Outline SDK + asenacore)
cd mobile/core
go get github.com/Diniboy1123/usque golang.zx2c4.com/wireguard \
       github.com/Jigsaw-Code/outline-sdk gvisor.dev/gvisor
gomobile bind -target=android -androidapi 26 -o ../android/app/libs/asenacore.aar .

# 2) Android Studio: app modülü asenacore.aar'ı import eder, VpnService + Compose UI
./gradlew assembleRelease   # -> AsenaPlug.apk (doğrudan dağıtım)
```

## 6. PoC adımları (sıra)
1. **Tünel MVP:** usque `api` ile tüneli kur, `tunNet.DialContext` ile TR'de sansürlü bir
   siteye bağlan (Go testi, VpnService'siz) → MASQUE'in mobilde çalıştığını KANITLA.
2. **VpnService full-tünel:** fd → tun2socks → hepsi `tunNet` (selective yok) → "bağlan,
   internet tünelden" doğrula.
3. **Selective:** `onDnsQuery` + `ipSet` + `selectDialer` → blacklist tünel, gerisi direkt.
4. **Compose UI** (mockup'a göre) + sağlamlaştırma (reconnect, IPv6 fail-closed, foreground).
5. **İmzalı APK + doğrudan dağıtım.**

## 7. Açık uçlar (build sırasında netleşir)
- usque `config.json` loader'ını dosya yerine string/reader'dan okutmak (küçük yardımcı ya
  da upstream'e PR).
- Outline SDK'nın tam dialer/packet-proxy arayüzü (per-flow custom dialer).
- UDP + DNS pompasının netstack ↔ VpnService fd köprüsü.
- Pil: foreground service + Doze whitelisting.
