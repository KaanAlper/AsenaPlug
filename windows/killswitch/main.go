// asena-killswitch — full-mod kill-switch'i WFP (Windows Filtering Platform)
// DYNAMIC session ile kurar. Kritik özellik: dinamik oturumdaki filtreler, oturumu
// açan SÜREÇ ölünce (normal çıkış / taskkill / çökme / güç kesintisi sonrası reboot)
// Windows tarafından OTOMATİK silinir. Yani kill-switch açıkken uygulama çökse bile
// internet kalıcı bloklu KALMAZ -> brick imkânsız (NetFirewall DefaultOutboundAction
// yaklaşımının aksine; onu bu yüzden bıraktık).
//
// Correctness: WFP sublayer + ağırlık ile "permit-above-block" -> yüksek ağırlıklı
// Permit, düşük ağırlıklı Block'u yener (NetFirewall'da Block hep kazanırdı). Böylece
// TUN / usque / endpoint / LAN'a izin verip gerisini temizce bloklarız (CIDR complement
// gymnastic'i yok).
//
// Yaşam döngüsü: full mod + kill-switch açıkken asena-on başlatır; disconnect / mod
// değişimi / kill-switch kapatınca tray öldürür (ölünce filtreler uçar).
//
//	asena-killswitch.exe -tun-index <ifIndex> -usque <path\usque.exe> -allow <cidr,cidr,...>
package main

import (
	"flag"
	"fmt"
	"net/netip"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"unsafe"

	"github.com/tailscale/wf"
	"golang.org/x/sys/windows"
)

var (
	iphlpapi                       = windows.NewLazySystemDLL("iphlpapi.dll")
	procConvertInterfaceIndexToLuid = iphlpapi.NewProc("ConvertInterfaceIndexToLuid")
)

// TUN'un ifIndex'inden NET_LUID (uint64). WFP FieldIPLocalInterface LUID ister.
func luidFromIndex(idx uint32) (uint64, error) {
	var luid uint64
	r, _, _ := procConvertInterfaceIndexToLuid.Call(uintptr(idx), uintptr(unsafe.Pointer(&luid)))
	if r != 0 {
		return 0, fmt.Errorf("ConvertInterfaceIndexToLuid(%d) failed: status=%d", idx, r)
	}
	return luid, nil
}

func main() {
	tunIndex := flag.Uint("tun-index", 0, "TUN (usque) interface index")
	usquePath := flag.String("usque", "", "path to usque.exe (permitted on physical for reconnect)")
	allowCSV := flag.String("allow", "", "comma-separated extra CIDRs to permit (WARP endpoint ranges)")
	flag.Parse()

	if *tunIndex == 0 {
		die("-tun-index is required")
	}
	tunLUID, err := luidFromIndex(uint32(*tunIndex))
	if err != nil {
		die(err.Error())
	}

	// Dinamik oturum: filtreler süreç ölünce OTOMATİK silinir (brick yok).
	session, err := wf.New(&wf.Options{
		Name:        "AsenaPlug kill-switch",
		Description: "Blocks non-tunnel IPv4 while the tunnel is up (auto-removed on exit)",
		Dynamic:     true,
	})
	if err != nil {
		die("wf.New: " + err.Error())
	}

	slGUID, err := windows.GenerateGUID()
	if err != nil {
		die("GenerateGUID: " + err.Error())
	}
	sublayerID := wf.SublayerID(slGUID)
	if err := session.AddSublayer(&wf.Sublayer{
		ID:     sublayerID,
		Name:   "AsenaPlug kill-switch",
		Weight: 0xffff,
	}); err != nil {
		die("AddSublayer: " + err.Error())
	}

	layer := wf.LayerALEAuthConnectV4 // giden bağlantı yetkilendirme (outbound)

	addRule := func(name string, weight uint64, action wf.Action, conds []*wf.Match) {
		g, err := windows.GenerateGUID()
		if err != nil {
			die("GenerateGUID: " + err.Error())
		}
		if err := session.AddRule(&wf.Rule{
			ID:         wf.RuleID(g),
			Name:       name,
			Layer:      layer,
			Sublayer:   sublayerID,
			Weight:     weight,
			Conditions: conds,
			Action:     action,
		}); err != nil {
			die("AddRule(" + name + "): " + err.Error())
		}
	}

	// 1) TUN'a giden HER ŞEY (tünellenen trafik) — en yüksek öncelik
	addRule("permit-tun", 15, wf.ActionPermit, []*wf.Match{
		{Field: wf.FieldIPLocalInterface, Op: wf.MatchTypeEqual, Value: tunLUID},
	})

	// 2) usque'nin kendi trafiği (fiziksel üzerinden endpoint'e reconnect edebilsin)
	if *usquePath != "" {
		if appID, err := wf.AppID(*usquePath); err == nil {
			addRule("permit-usque", 14, wf.ActionPermit, []*wf.Match{
				{Field: wf.FieldALEAppID, Op: wf.MatchTypeEqual, Value: appID},
			})
		}
	}

	// 3) izinli IPv4 aralıkları: loopback + LAN/link-local + multicast/broadcast +
	//    WARP endpoint CIDR'leri (reconnect). netip.Prefix doğrudan V4AddrMask'e çevrilir.
	prefixes := []string{
		"127.0.0.0/8",
		"10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16",
		"224.0.0.0/4", "255.255.255.255/32",
	}
	for _, c := range strings.Split(*allowCSV, ",") {
		if c = strings.TrimSpace(c); c != "" {
			prefixes = append(prefixes, c)
		}
	}
	for _, c := range prefixes {
		p, err := netip.ParsePrefix(c)
		if err != nil || !p.Addr().Is4() {
			continue // yalnız IPv4 (usque IPv4-only; IPv6 full modda ayrı bloklu)
		}
		addRule("permit-"+c, 12, wf.ActionPermit, []*wf.Match{
			{Field: wf.FieldIPRemoteAddress, Op: wf.MatchTypeEqual, Value: p},
		})
	}

	// 4) DHCP (UDP remote port 67) — lease yenileme çalışsın
	addRule("permit-dhcp", 11, wf.ActionPermit, []*wf.Match{
		{Field: wf.FieldIPProtocol, Op: wf.MatchTypeEqual, Value: wf.IPProto(17)},
		{Field: wf.FieldIPRemotePort, Op: wf.MatchTypeEqual, Value: uint16(67)},
	})

	// 5) EN DÜŞÜK ağırlık: gerisini BLOKLA (permit'ler bunu yener)
	addRule("block-all", 1, wf.ActionBlock, nil)

	fmt.Println("asena-killswitch: active (dynamic WFP session — filters auto-remove on exit)")
	// Süreç yaşadıkça filtreler duruyor. Ölünce (tray taskkill / çökme) OTOMATİK
	// silinir; ayrıca temiz sinyalde de açıkça kapatırız.
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	<-sig
	_ = session.Close()
}

func die(msg string) {
	fmt.Fprintln(os.Stderr, "asena-killswitch: "+msg)
	os.Exit(1)
}
