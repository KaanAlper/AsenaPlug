# AsenaPlug Android — build

Cloudflare MASQUE (usque) tabanlı sansür-bypass VPN. **Kotlin + Jetpack Compose kabuk**,
**Go çekirdek** (gomobile `.aar`). Full-tünel çalışıyor; selective mode (blacklist → tünel,
gerisi direkt) yol haritasında.

## Gerekenler
- JDK 17
- Android SDK (platform 35, build-tools 35.0.0)
- Gradle 8.7 (veya wrapper)
- Çekirdeği (aar) yeniden derlemek için: Go 1.23+, gomobile, Android NDK r27

## 1) local.properties (git'te yok — kendin oluştur)
```
sdk.dir=/ev/dizinin/Android/Sdk
```

## 2) Go çekirdeğini derle (asenacore.aar)  — sadece Go kodu değişince
Çekirdek `../androidcore` (gomobile giriş paketi) + `../usque-fork/api_mobile.go` (usque FORK'una
eklenir; internal erişim gerektirir). usque kaynağını klonla, `api_mobile.go`'yu `api/`'ye kopyala,
`go.mod`'da fork'a `replace` ver, sonra:
```
export ANDROID_HOME=~/Android/Sdk ANDROID_NDK_HOME=~/Android/Sdk/ndk/27.0.12077973
gomobile bind -target=android/arm64 -androidapi 26 -o app/libs/asenacore.aar .
```
Repo'da derlenmiş `app/libs/asenacore.aar` (arm64) hazır gelir; UI'da çalışırken yeniden gerekmez.

## 3) APK
```
gradle assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## İlk açılış
Uygulama **gömülü anahtar taşımaz**. İlk açılışta "Başla" → anonim WARP hesabı (Androidcore.register)
oluşturulur, `SharedPreferences`'a kaydedilir. `config.json` repoya ASLA girmez (.gitignore).

## Mimari
- `MainActivity.kt` — Compose UI (Bağlan/Siteler/Ayarlar), dinamik tema+aksan, i18n (TR/EN).
- `AsenaVpnService.kt` — VpnService: TUN kurar, fd'yi `Androidcore.start`'a verir (full-tünel).
  Loop önleme: `addDisallowedApplication(self)`.
- `*Store.kt` — Config/Domain/Theme/Lang/Settings/Stats (SharedPreferences + StateFlow).
- Go: `androidcore` (Start/Stop/Register) → `api_mobile.go` (StartFullTunnelFd/ConnectMobile/
  RegisterMobile) → usque `api` (MASQUE tüneli).
