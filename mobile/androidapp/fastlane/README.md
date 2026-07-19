# Play Store metadata (fastlane / supply formatı)

Play Console listing metni ve görselleri **standart `fastlane supply` yapısında**:

```
fastlane/metadata/android/<locale>/
  title.txt                 # uygulama adı (≤30)
  short_description.txt     # kısa açıklama (≤80)
  full_description.txt      # tam açıklama (≤4000)
  changelogs/default.txt    # "yenilikler" (sürüm notu); <versionCode>.txt de olabilir
  images/
    icon.png                # 512×512 hi-res icon
    featureGraphic.png      # 1024×500 özellik grafiği
    phoneScreenshots/       # buraya telefon ekran görüntülerini koy (min 2)
```

Diller: `tr-TR`, `en-US`.

## Nasıl yüklenir

**A) fastlane supply ile (otomatik, önerilen):**
```
cd mobile/androidapp
fastlane supply --package_name com.kaanalper.asenaplug \
  --aab app/build/outputs/bundle/release/app-release.aab \
  --json_key play-service-account.json --track internal
```
`supply`, metadata/ altındaki tüm metin + görselleri de yükler.

**B) Play Console'da elle:** yukarıdaki .txt'leri kopyala-yapıştır, icon/featureGraphic'i yükle.

## Not — mevcut CI (r0adkll/upload-google-play)
`.github/workflows/mobile-apk.yml`'deki Play adımı **yalnızca AAB'yi** yükler (title/açıklama/görsel
YÜKLEMEZ — onları supply veya Console yapar). Tam otomasyon istersen CI'yı `fastlane supply`'a
çevirebilirim; o zaman her push metni+görseli de günceller.
