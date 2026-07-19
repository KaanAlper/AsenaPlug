// api_mobile.go — usque FORK'una eklenir (github.com/<sen>/usque/api paketine).
//
// NEDEN FORK: Go'nun "internal" kuralı gereği usque'nun `internal` paketi (GenerateCert,
// ConnectSNI, TunnelDNSResolver) DIŞARIDAN import edilemez. Bu yardımcı usque MODÜLÜNÜN
// İÇİNDE yaşadığı için internal'a erişir ve mobile'a tek temiz fonksiyon sunar:
//
//     tunNet, cancel, err := api.ConnectTunnel(configJSON, true /*http2*/)
//     // tunNet.DialContext(ctx,"tcp",addr) -> MASQUE tünelinden çıkar
//     // tunNet.LookupContextHost(ctx, host) -> tünelden temiz DNS
//     defer cancel()
//
// (Alternatif: fork yerine bu ~40 satırı kendi modülünde yeniden yaz + GenerateCert/
//  ConnectSNI'yi kopyala. Fork daha bakımlı — upstream'e PR olarak da açılabilir.)

package api

import (
	"context"
	"crypto/tls"
	"encoding/base64"
	"encoding/json"
	"net"
	"net/netip"
	"time"

	"github.com/Diniboy1123/usque/config"
	"github.com/Diniboy1123/usque/internal"

	"golang.zx2c4.com/wireguard/tun"
	"golang.zx2c4.com/wireguard/tun/netstack"
)

// RegisterMobile — yeni bir anonim Cloudflare WARP hesabı kaydeder + cihaz anahtarını enroll eder,
// config'i JSON string olarak döndürür (cmd/register.go'nun dosyasız hâli). Böylece uygulama gömülü
// anahtar taşımaz; her kullanıcı ilk açılışta kendi hesabını oluşturur.
func RegisterMobile(deviceName string) (string, error) {
	if deviceName == "" {
		deviceName = "AsenaPlug"
	}
	accountData, err := Register(internal.DefaultModel, internal.DefaultLocale, "", true /*accept TOS*/)
	if err != nil {
		return "", err
	}
	privKey, pubKey, err := internal.GenerateEcKeyPair()
	if err != nil {
		return "", err
	}
	updated, err := EnrollKey(accountData.ID, accountData.Token, pubKey, deviceName)
	if err != nil {
		return "", err
	}
	cfg := config.Config{
		PrivateKey:     base64.StdEncoding.EncodeToString(privKey),
		EndpointV4:     updated.Config.Peers[0].Endpoint.V4[:len(updated.Config.Peers[0].Endpoint.V4)-2],
		EndpointV6:     updated.Config.Peers[0].Endpoint.V6[1 : len(updated.Config.Peers[0].Endpoint.V6)-3],
		EndpointH2V4:   config.DefaultEndpointH2V4,
		EndpointH2V6:   config.DefaultEndpointH2V6,
		EndpointPubKey: updated.Config.Peers[0].PublicKey,
		ID:             updated.ID,
		AccessToken:    accountData.Token,
		IPv4:           updated.Config.Interface.Addresses.V4,
		IPv6:           updated.Config.Interface.Addresses.V6,
	}
	b, err := json.Marshal(cfg)
	if err != nil {
		return "", err
	}
	return string(b), nil
}

// loadConfigJSON — config JSON'unu DOSYASIZ olarak config.AppConfig'e yükler. config.LoadConfig
// bir dosya yolu istiyor; ama Android'de app /tmp'ye (/data/local/tmp) YAZAMAZ (permission denied)
// + WARP private key'ini diske yazmak istemeyiz. Bu, LoadConfig'in bellekte çalışan eşdeğeri.
func loadConfigJSON(configJSON string) error {
	if err := json.Unmarshal([]byte(configJSON), &config.AppConfig); err != nil {
		return err
	}
	config.ConfigLoaded = true
	return nil
}

// ConnectMobile usque config'inden (JSON string) MASQUE tünelini kurar ve tünel netstack'ini
// (dialer + resolver) döndürür. cmd/socks.go'nun kurulum akışının kütüphane hâli.
// (İsim: usque'da zaten low-level bir ConnectTunnel var -> çakışmamak için ConnectMobile.)
func ConnectMobile(configJSON string, useHTTP2 bool) (*netstack.Net, context.CancelFunc, error) {
	if err := loadConfigJSON(configJSON); err != nil {
		return nil, nil, err
	}

	privKey, err := config.AppConfig.GetEcPrivateKey()
	if err != nil {
		return nil, nil, err
	}
	peerPubKey, err := config.AppConfig.GetEcEndpointPublicKey()
	if err != nil {
		return nil, nil, err
	}
	cert, err := internal.GenerateCert(privKey, &privKey.PublicKey) // internal — sadece fork içinde erişilir
	if err != nil {
		return nil, nil, err
	}
	tlsConfig, err := PrepareTlsConfig(privKey, peerPubKey, cert, internal.ConnectSNI, false)
	if err != nil {
		return nil, nil, err
	}

	// yerel (atanmış) adres + DNS + endpoint
	v4, err := netip.ParseAddr(config.AppConfig.IPv4)
	if err != nil {
		return nil, nil, err
	}
	localAddresses := []netip.Addr{v4}
	dnsAddrs := []netip.Addr{netip.MustParseAddr("1.1.1.1"), netip.MustParseAddr("1.0.0.1")}

	// endpoint: usque'nun kendi seçicisi doğru net.Addr'ı verir (http2 -> *net.TCPAddr,
	// http3 -> *net.UDPAddr). connect-port default 443.
	endpoint, err := config.SelectEndpointFromConfig(useHTTP2, false /*ipv6*/, 443)
	if err != nil {
		return nil, nil, err
	}

	tunDev, tunNet, err := netstack.CreateNetTUN(localAddresses, dnsAddrs, 1280)
	if err != nil {
		return nil, nil, err
	}

	ctx, cancel := context.WithCancel(context.Background())
	go MaintainTunnel(ctx, MaintainTunnelConfig{
		TLSConfig:       tlsConfig,
		KeepalivePeriod: 30 * time.Second,
		Endpoint:        endpoint,
		Device:          NewNetstackAdapter(tunDev),
		MTU:             1280,
		UseHTTP2:        useHTTP2,
		AlwaysReconnect: true,
	})

	return tunNet, func() { cancel(); tunDev.Close() }, nil
}

// StartFullTunnelFd — VpnService TUN fd'sini usque'ya doğrudan cihaz olarak verir: TÜM trafik
// MASQUE'ten geçer (full-tünel). usque paket pompasını kendi yapar (ayrı tun2socks GEREKMEZ).
// İlk çalışan Android APK'sı için en basit yol; selective sonra (asenacore.selectDialer).
func StartFullTunnelFd(tunFd int, configJSON string, useHTTP2 bool) (context.CancelFunc, error) {
	tls, endpoint, err := prepareFromConfig(configJSON, useHTTP2)
	if err != nil {
		return nil, err
	}
	// VpnService fd -> wireguard-go tun.Device. CreateUnmonitoredTUNFromFD: netlink route
	// monitoring YOK (VpnService için doğru; wireguard-android da bunu kullanır). VpnService
	// TUN'unda IFF_VNET_HDR yok -> vnetHdr=false, batchSize=1 -> NetstackAdapter (offset 0) uyumlu.
	dev, _, err := tun.CreateUnmonitoredTUNFromFD(tunFd)
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithCancel(context.Background())
	go MaintainTunnel(ctx, MaintainTunnelConfig{
		TLSConfig:       tls,
		KeepalivePeriod: 30 * time.Second,
		Endpoint:        endpoint,
		Device:          NewNetstackAdapter(dev),
		MTU:             1280,
		UseHTTP2:        useHTTP2,
		AlwaysReconnect: true,
	})
	return func() { cancel(); dev.Close() }, nil
}

// prepareFromConfig — config JSON -> (tlsConfig, endpoint). ConnectMobile + StartFullTunnelFd ortak.
func prepareFromConfig(configJSON string, useHTTP2 bool) (*tls.Config, net.Addr, error) {
	if err := loadConfigJSON(configJSON); err != nil {
		return nil, nil, err
	}
	privKey, err := config.AppConfig.GetEcPrivateKey()
	if err != nil {
		return nil, nil, err
	}
	peerPubKey, err := config.AppConfig.GetEcEndpointPublicKey()
	if err != nil {
		return nil, nil, err
	}
	cert, err := internal.GenerateCert(privKey, &privKey.PublicKey)
	if err != nil {
		return nil, nil, err
	}
	tlsConfig, err := PrepareTlsConfig(privKey, peerPubKey, cert, internal.ConnectSNI, false)
	if err != nil {
		return nil, nil, err
	}
	endpoint, err := config.SelectEndpointFromConfig(useHTTP2, false, 443)
	if err != nil {
		return nil, nil, err
	}
	return tlsConfig, endpoint, nil
}
