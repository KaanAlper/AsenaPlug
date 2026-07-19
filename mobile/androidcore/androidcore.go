// Package androidcore — gomobile ile Kotlin'e açılan MİNİMAL full-tünel çekirdeği (ilk APK).
//
//   gomobile bind -target=android -androidapi 26 -o asenacore.aar .
//
// Kotlin:
//   import asena.androidcore.Androidcore
//   Androidcore.start(tunFd, configJson, /*http2=*/true)   // VpnService.establish().fd
//   Androidcore.stop()
//
// Bu sürüm FULL-TÜNEL: VpnService TUN fd'sini usque'ya doğrudan cihaz olarak verir; TÜM trafik
// MASQUE'ten geçer (usque paket pompasını kendi yapar — ayrı tun2socks YOK). Selective mod (blacklist
// -> tünel, gerisi direkt) sonraki adım: mobile/core/asenacore.go (per-flow dialer + protect).
package androidcore

import (
	"errors"
	"sync"

	"github.com/Diniboy1123/usque/api" // fork: StartFullTunnelFd (bkz. mobile/usque-fork/api_mobile.go)
)

// ProtectFunc: Kotlin (VpnService.protect) implement eder — direkt soketlerin TUN'u bypass etmesi için
// (selective mode'da "gerisi direkt" trafiği tünele geri girmesin). gomobile Java arayüzü üretir.
type ProtectFunc interface{ Protect(fd int32) bool }

var (
	mu   sync.Mutex
	stop func()
)

// Start — full-tünel'i başlatır. tunFd = VpnService.establish() dosya tanıtıcısı.
// configJSON = 'usque register' çıktısı. useHTTP2 = TR'de sağlam (true önerilir).
func Start(tunFd int, configJSON string, useHTTP2 bool) error {
	mu.Lock()
	defer mu.Unlock()
	if stop != nil {
		return errors.New("zaten bağlı")
	}
	cancel, err := api.StartFullTunnelFd(tunFd, configJSON, useHTTP2)
	if err != nil {
		return err
	}
	stop = cancel
	return nil
}

// Stop — tüneli kapatır, TUN cihazını serbest bırakır.
func Stop() {
	mu.Lock()
	defer mu.Unlock()
	if stop != nil {
		stop()
		stop = nil
	}
}

// IsRunning — bağlı mı? (Kotlin durum senkronu için)
func IsRunning() bool {
	mu.Lock()
	defer mu.Unlock()
	return stop != nil
}

// Register — yeni anonim WARP hesabı oluşturur, config JSON döndürür (ilk açılış).
// Kotlin bunu arka planda çağırır, sonucu ConfigStore'a kaydeder. Uygulama gömülü anahtar taşımaz.
func Register(deviceName string) (string, error) {
	return api.RegisterMobile(deviceName)
}
