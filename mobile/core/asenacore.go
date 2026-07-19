// Package asenacore — gomobile ile Kotlin'e açılan çekirdek.
//   gomobile bind -target=android -androidapi 26 -o asenacore.aar .
//
// Kotlin:
//   val core = Asenacore.newCore()
//   core.start(tunFd, configJson, blacklistJson, protectImpl)  // protect: VpnService.protect
//   ...
//   core.stop()
//
// Mimari: usque MASQUE tüneli (api.ConnectTunnel -> tunNet dialer) + VpnService TUN fd üstünde
// tun2socks. Her flow: dstIP blacklist-set'te ise TÜNEL, değilse DİREKT (protect'li) = HIZ.

package asenacore

import (
	"context"
	"net"
	"net/netip"
	"os"
	"sync"
	"time"

	"github.com/Diniboy1123/usque/api" // fork: ConnectTunnel içerir

	"golang.zx2c4.com/wireguard/tun"
	"golang.zx2c4.com/wireguard/tun/netstack"
	// TODO(build): Outline SDK tun2socks + transport
	// "github.com/Jigsaw-Code/outline-sdk/network"
	// "github.com/Jigsaw-Code/outline-sdk/transport"
)

// ProtectFunc: direkt soketlerin VpnService TUN'unu BAYPAS etmesi için (Kotlin implement eder:
// VpnService.protect(fd)). Böylece "gerisi direkt" trafiği tünele geri girmez (loop yok).
type ProtectFunc interface{ Protect(fd int32) bool }

type Core struct {
	mu      sync.Mutex
	cancel  context.CancelFunc
	tunNet  *netstack.Net // usque tünel dialer + resolver
	ipset   *ipSet        // blacklist domainlerin çözülmüş IP'leri (TTL'li)
	matcher *matcher      // apex + *.subdomain
	protect ProtectFunc
}

func NewCore() *Core { return &Core{} }

// Start: tünel + tun2socks'u başlatır. tunFd = VpnService establish()'in fd'si.
func (c *Core) Start(tunFd int, configJSON string, blacklistJSON string, p ProtectFunc) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.protect = p
	c.matcher = newMatcher(parseBlacklist(blacklistJSON))
	c.ipset = newIPSet()

	// (1) MASQUE tüneli — tunNet.DialContext = tünel dialer (bkz. usque-fork/api_mobile.go)
	tunNet, cancel, err := api.ConnectMobile(configJSON, true /*http2: TR'de sağlam*/)
	if err != nil {
		return err
	}
	c.tunNet, c.cancel = tunNet, cancel

	// (2) VpnService fd'sini wireguard-go tun.Device'ına sar (fd sahipliği bizde)
	f := os.NewFile(uintptr(tunFd), "asena-tun")
	tunOS, _, err := tun.CreateUnmonitoredTUNFromFD(int(f.Fd())) // veya CreateTUNFromFile
	if err != nil {
		cancel()
		return err
	}

	// (3) tun2socks: fd üstündeki paketleri per-flow dialer'ımızla yönlendir
	//     TODO(build): Outline network.NewTUNDevice / IPDevice + StreamHandler.
	//     StreamDialer = c.selectDialer ; PacketProxy (UDP) benzer ; DNS = c.handleDNS.
	go c.runTun2Socks(tunOS)

	return nil
}

// selectDialer: KARAR — blacklist IP'si tünele, gerisi direkt (native hız).
func (c *Core) selectDialer(ctx context.Context, dst netip.AddrPort) (net.Conn, error) {
	if c.ipset.Contains(dst.Addr()) {
		return c.tunNet.DialContext(ctx, "tcp", dst.String()) // → MASQUE TÜNEL
	}
	return c.directDial(ctx, dst) // → DİREKT (protect'li)
}

// handleDNS: blacklist domaini tünelden temiz çöz + IP'yi işaretle; değilse sisteme bırak.
func (c *Core) handleDNS(domain string) ([]netip.Addr, bool) {
	if !c.matcher.Match(domain) {
		return nil, false // false => normal/sistem DNS (hızlı)
	}
	ips, err := c.tunNet.LookupContextHost(context.Background(), domain) // TEMİZ (zehirlenmez)
	if err != nil {
		return nil, false
	}
	out := make([]netip.Addr, 0, len(ips))
	for _, s := range ips {
		if a, e := netip.ParseAddr(s); e == nil {
			out = append(out, a)
		}
	}
	c.ipset.AddAll(out, time.Hour) // conntrack-benzeri kalıcılık (akış ortasında düşmesin)
	return out, true
}

// directDial: TUN'u BAYPAS eden soket (Kotlin protect ile). "gerisi direkt" native hız.
func (c *Core) directDial(ctx context.Context, dst netip.AddrPort) (net.Conn, error) {
	d := net.Dialer{Control: func(_, _ string, rc syscallRawConn) error {
		return rc.Control(func(fd uintptr) { c.protect.Protect(int32(fd)) })
	}}
	return d.DialContext(ctx, "tcp", dst.String())
}

func (c *Core) Stop() {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.cancel != nil {
		c.cancel()
		c.cancel = nil
	}
}

// --- TODO(build): Outline SDK ile doldurulacak tun2socks pompası ---
func (c *Core) runTun2Socks(dev tun.Device) { /* Outline network paketi: dev <-> selectDialer/handleDNS */ }

// syscallRawConn: net.Dialer.Control imzası için (syscall.RawConn).
type syscallRawConn interface {
	Control(f func(fd uintptr)) error
}
