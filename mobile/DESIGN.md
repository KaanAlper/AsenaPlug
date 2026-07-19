# AsenaPlug — Mobil (Android) Tasarım & Mimari

> **Tek cümle:** Intra kadar hafif, ama IP/SNI bloklarını da açan, **sadece yasaklı siteleri**
> Cloudflare MASQUE tünelinden geçiren — gerisini native hızda direkt bırakan Android VPN.

---

## 1. Vizyon & farklılaşma

| | 1.1.1.1 / WARP | Intra | **AsenaPlug Mobil** |
|---|---|---|---|
| Model | Full tünel | Sadece DNS | **Selective (domain-bazlı)** |
| IP/SNI bloğu açar mı | ✅ (ama her şeyi yavaşlatır) | ❌ | ✅ |
| Hız | Yavaş (tüm trafik tünelde) | Hızlı ama yetersiz | **Hızlı + yeterli** |
| Dağıtım | Store'a mahkûm | Store | **Doğrudan APK (bloklanamaz)** |

**Hız iddiasının kaynağı mimari:** trafiğin ~%95'i (banka, yerel, sansürsüz) hiç tünele
girmez → sıfır tünel gecikmesi. Sadece blacklist'teki alanlar MASQUE'tan geçer.

---

## 2. Mimari — Kotlin kabuk + Go çekirdek

Hız veri-yolunda; veri-yolu **Go native** (Tailscale/Outline/Intra hepsi böyle). Kotlin
sadece VpnService + UI orkestrasyonu. Paket-işleme Kotlin'de OLMAZ (JNI + GC yavaşlatır).

```
┌──────────────────────── Android APK ────────────────────────┐
│  Kotlin katmanı (ince kabuk)                                 │
│   • VpnService  → TUN fd (ParcelFileDescriptor)              │
│   • Jetpack Compose UI (Material 3 Expressive)               │
│   • Config / register / start-stop / bildirim               │
│                          │ JNI                               │
│  ────────────────────────┼─────────────────────────────     │
│  Go çekirdek (gomobile → tek .aar)                           │
│   • tun2socks  (Outline SDK / go-tun2socks, Apache-2)        │
│   • DNS-intercept + selective router  (BİZİM kod)           │
│   • usque MASQUE client  (socks/gvisor netstack — HAZIR)    │
│                          │                                   │
└──────────────────────────┼───────────────────────────────── ┘
                           ▼
              Cloudflare MASQUE (HTTP/2 · HTTP/3)
```

**Neyi yeniden kullanırız:**
- `usque` — Go, Android arm64 binary + `socks` modu (gvisor netstack) zaten var. Kütüphane
  olarak gömülür.
- `Outline SDK` / `go-tun2socks` — VpnService-fd → tun2socks, Apache-2, uyarlanır.
- `Intra` DNS-split deseni — referans.

**Neyi yazarız:** selective router (Go glue) + VpnService/UI (Kotlin).

---

## 3. Algoritma — Selective router (çekirdek)

Masaüstündeki nftset/NRPT mantığının userspace (gvisor) karşılığı.

### 3.1 Kurulum
```
VpnService.Builder:
  addAddress(10.111.0.2/32)          # sanal TUN adresi
  addRoute(0.0.0.0/0)                # HER paketi yakala (userspace'te ayrıştıracağız)
  addDnsServer(10.111.0.53)          # DNS'i kendi resolver'ımıza al
  # NOT: usque MASQUE soketi VpnService.protect() ile TUN'u BAYPAS eder (loop yok)
```

### 3.2 DNS akışı (her sorgu)
```
onDnsQuery(domain):
    if matchBlacklist(domain):                 # apex + subdomain (*.site.com)
        ip = resolveViaTunnel(domain)          # usque üstünden TEMİZ çözüm (zehirlenmez)
        ipSet.add(ip, ttl=max(dnsTtl, 3600))   # IP'yi "tünelli" olarak işaretle
        return ip
    else:
        return resolveDirect(domain)           # normal/DoH — hızlı, tünelsiz
```

### 3.3 TCP/UDP akışı (her yeni bağlantı)
```
onNewFlow(dstIP, dstPort):
    if ipSet.contains(dstIP):                  # blacklist domaininin IP'si
        dial via usque-SOCKS (MASQUE tünel)    # → sansür aşılır
    else:
        dial via protectedSocket (direkt)      # → native hız, tünel yok
```

### 3.4 Sağlamlık kuralları (masaüstünden taşınan)
- **conntrack kalıcılık:** akış bir kez tünele atandıysa, IP-set girdisi süre dolsa bile
  bağlantı bitene dek tünelde kalır (orta-akış kopma/leak yok).
- **DNS-leak fail-closed:** blacklist domainin DNS'i SADECE tünelden; düz-53 sızıntısı bloklu.
- **IPv6:** tünel v4-only → blacklist domainlerin v6'sı fail-closed (app v4'e = tünele düşer).
- **HTTP/3 fallback:** UDP 443 bloksa usque otomatik HTTP/2'ye (eduroam/kısıtlı ağlar).
- **SNI-sniff (v2, opsiyonel):** ilk pakette TLS ClientHello SNI'a bakıp DNS'i baypas eden
  IP-direkt bağlantıları da yakala (CDN paylaşımlı IP'lerde doğruluk artar).

---

## 4. UI — Material 3 Expressive, üç ekran

**Kimlik:** Asena = bozkurt. Grafit zemin, kurt-gözü **amber** aksan (bağlıyken "glow").
Cesur tipografi, yumuşak-köşe kartlar, akıcı ama ölçülü hareket.

### Ekran 1 — Bağlan (ana)
- Merkezde büyük **kalkan/kurt** — kapalı: gri outline; bağlı: amber dolu + nabız glow.
- Tek büyük **Bağlan/Kes** aksiyonu (kalkana dokun ya da alttaki bar).
- Durum satırı: `Bağlı · HTTP/2 · Sadece blacklist` + canlı hız (↓↑ mono rakam).
- Küçük istatistik: "Bu oturum 14 site açıldı · 0 leak".

### Ekran 2 — Siteler (blacklist)
- Açılan sitelerin **canlı listesi** (amber nokta = şu an tünelde).
- Sayaç + "Ekle" (FAB). Uzun bas → sil. Arama.
- Full modda "hepsi açık" notu.

### Ekran 3 — Mod & Ayarlar
- İki eksen chip: **Transport** (HTTP/2 · HTTP/3) × **Kapsam** (Sadece blacklist · Her şey).
- Değişiklik **anında uygulanır** (mobilde native menü, seç-Değiştir gerekmez).
- Dil (5), PC-yok, autostart-yok; "başlangıçta bağlan", "güvenilir Wi-Fi'da kapan".

**Navigasyon:** M3 adaptif — telefon: alt navigasyon (Bağlan · Siteler · Ayarlar).

---

## 5. Tech stack

| Katman | Teknoloji |
|---|---|
| UI | Kotlin + Jetpack Compose + **Material 3 Expressive** |
| VPN kabuğu | Android `VpnService` (root yok) |
| Veri yolu | Go (gomobile `.aar`): tun2socks + selective router |
| Tünel | **usque** (MASQUE, connect-ip RFC 9484) |
| tun2socks | Outline SDK / go-tun2socks (Apache-2) |
| Min SDK | Android 8+ (API 26) — VpnService + gomobile |

---

## 6. Yol haritası

1. **PoC (1 hafta):** usque `socks`'u Go kütüphanesi olarak in-process çağır + Outline
   tun2socks ile full-tünel MVP (Android'de "bağlan → tüm trafik MASQUE"). Doğrula: TR'de
   sansürlü site açılıyor mu, hız.
2. **Selective (2 hafta):** DNS-intercept + IP-set + dialer ayrımı → blacklist tünelde,
   gerisi direkt. Asıl ürün.
3. **UI (1-2 hafta):** Compose 3 ekran, M3 Expressive, akış.
4. **Sağlamlaştırma:** conntrack kalıcılık, IPv6 fail-closed, HTTP/3 fallback, reconnect.
5. **Dağıtım:** imzalı APK + doğrudan indirme (Play değil) + otomatik güncelleme.

## 7. Riskler
- **Ana:** usque'yu ayrı binary değil **kütüphane** olarak gömmek (socks'u programatik API
  yapmak) — Go refactor gerekir.
- **Ağ:** aynı Cloudflare backend → TR endpoint'leri komple bloklarsa ikisi de düşer. Edge:
  maskeleme + selective + bloklanamaz dağıtım (ayrı ağ değil).
- **Pil/arka plan:** VpnService sürekli açık — Doze/battery optimizasyonu iyi yönetilmeli.
