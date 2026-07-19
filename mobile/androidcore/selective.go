// selective.go — SELECTIVE ROUTING (masaüstü nftset/NRPT'nin userspace hâli).
//
// VpnService fd -> Outline SDK lwip2transport -> per-flow karar:
//   TCP: hedef IP blacklist-set'te ise usque MASQUE tüneli, değilse protect'li DİREKT soket.
//   UDP/DNS: dest:53 -> domain blacklist ise TÜNELDEN temiz çöz + IP'leri set'e ekle + yanıtla
//            (böylece istemci temiz IP'ye bağlanır -> TCP flow tünele gider). Değilse direkt ilet.
//
// Değer: yavaşlama/kesinti SADECE blacklist sitelerinde olur; gerisi native hızda.

package androidcore

import (
	"context"
	"errors"
	"net"
	"net/netip"
	"os"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/Diniboy1123/usque/api"
	"github.com/miekg/dns"
	"golang.getoutline.org/sdk/network"
	"golang.getoutline.org/sdk/network/lwip2transport"
	"golang.getoutline.org/sdk/transport"
	"golang.zx2c4.com/wireguard/tun/netstack"
)

type selectiveTunnel struct {
	cancel context.CancelFunc
	fd     *os.File
	lwip   network.IPDevice
}

var (
	selMu     sync.Mutex
	selActive *selectiveTunnel
)

// StartSelective — selective mode başlatır. tunFd=VpnService fd, blacklistJSON=domain listesi (JSON dizi),
// protect=VpnService.protect (direkt soketler TUN'u bypass etsin -> loop yok).
func StartSelective(tunFd int, configJSON, blacklistJSON string, useHTTP2 bool, protect ProtectFunc) error {
	selMu.Lock()
	defer selMu.Unlock()
	if selActive != nil {
		return errors.New("selective zaten aktif")
	}

	// (1) usque MASQUE tüneli — tunNet: tünel dialer + temiz resolver
	tunNet, cancel, err := api.ConnectMobile(configJSON, useHTTP2)
	if err != nil {
		return err
	}

	ipset := newIPSet()
	match := newMatcher(parseBlacklist(blacklistJSON))

	// direkt soket kontrolü: VpnService.protect(fd) -> TUN'u bypass
	directControl := func(_, _ string, c syscall.RawConn) error {
		if protect == nil {
			return nil
		}
		return c.Control(func(fd uintptr) { protect.Protect(int32(fd)) })
	}

	// (2) TCP: hedef IP tünelli mi?
	sd := transport.FuncStreamDialer(func(ctx context.Context, addr string) (transport.StreamConn, error) {
		host, _, _ := net.SplitHostPort(addr)
		ip, _ := netip.ParseAddr(host)
		var c net.Conn
		if ip.IsValid() && ipset.Contains(ip) {
			c, err = tunNet.DialContext(ctx, "tcp", addr) // TÜNEL
		} else {
			d := &net.Dialer{Control: directControl}
			c, err = d.DialContext(ctx, "tcp", addr) // DİREKT (protect)
		}
		if err != nil {
			return nil, err
		}
		if sc, ok := c.(transport.StreamConn); ok {
			return sc, nil
		}
		return &wrapStream{Conn: c}, nil
	})

	// (3) UDP + DNS-intercept
	pp := &selPacketProxy{tunNet: tunNet, ipset: ipset, match: match, directControl: directControl}

	lwipDev, err := lwip2transport.ConfigureDevice(sd, pp)
	if err != nil {
		cancel()
		return err
	}

	// (4) pump: VpnService fd <-> lwip cihazı (her yön bir goroutine)
	fd := os.NewFile(uintptr(tunFd), "asena-tun")
	go copyPackets(lwipDev, fd) // fd -> lwip (giden)
	go copyPackets(fd, lwipDev) // lwip -> fd (gelen)

	selActive = &selectiveTunnel{cancel: cancel, fd: fd, lwip: lwipDev}
	return nil
}

// StopSelective — selective tüneli kapatır.
func StopSelective() {
	selMu.Lock()
	defer selMu.Unlock()
	if selActive == nil {
		return
	}
	selActive.cancel()
	_ = selActive.lwip.Close()
	_ = selActive.fd.Close()
	selActive = nil
}

// IsSelectiveRunning — Kotlin durum senkronu için.
func IsSelectiveRunning() bool {
	selMu.Lock()
	defer selMu.Unlock()
	return selActive != nil
}

// copyPackets — IP paketlerini bir cihazdan diğerine kopyalar (her Read/Write = bir paket).
func copyPackets(dst interface{ Write([]byte) (int, error) }, src interface{ Read([]byte) (int, error) }) {
	buf := make([]byte, 65535)
	for {
		n, err := src.Read(buf)
		if n > 0 {
			_, _ = dst.Write(buf[:n])
		}
		if err != nil {
			return
		}
	}
}

// wrapStream — StreamConn'u sağlamayan net.Conn'lar için (CloseRead/CloseWrite fallback).
type wrapStream struct{ net.Conn }

func (w *wrapStream) CloseRead() error {
	if c, ok := w.Conn.(interface{ CloseRead() error }); ok {
		return c.CloseRead()
	}
	return nil
}
func (w *wrapStream) CloseWrite() error {
	if c, ok := w.Conn.(interface{ CloseWrite() error }); ok {
		return c.CloseWrite()
	}
	return nil
}

/* ---------- UDP + DNS PacketProxy ---------- */

type selPacketProxy struct {
	tunNet        *netstack.Net
	ipset         *ipSet
	match         *matcher
	directControl func(string, string, syscall.RawConn) error
}

func (pp *selPacketProxy) NewSession(resp network.PacketResponseReceiver) (network.PacketRequestSender, error) {
	return &selSession{pp: pp, resp: resp, conns: make(map[netip.AddrPort]net.Conn)}, nil
}

type selSession struct {
	pp     *selPacketProxy
	resp   network.PacketResponseReceiver
	mu     sync.Mutex
	conns  map[netip.AddrPort]net.Conn
	closed bool
}

func (s *selSession) WriteTo(p []byte, dest netip.AddrPort) (int, error) {
	if dest.Port() == 53 {
		payload := make([]byte, len(p))
		copy(payload, p)
		go s.handleDNS(payload, dest)
		return len(p), nil
	}
	c, err := s.udpConn(dest)
	if err != nil {
		return 0, err
	}
	return c.Write(p)
}

func (s *selSession) udpConn(dest netip.AddrPort) (net.Conn, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return nil, net.ErrClosed
	}
	if c, ok := s.conns[dest]; ok {
		return c, nil
	}
	var c net.Conn
	var err error
	if s.pp.ipset.Contains(dest.Addr()) {
		c, err = s.pp.tunNet.DialContext(context.Background(), "udp", dest.String()) // TÜNEL
	} else {
		d := &net.Dialer{Control: s.pp.directControl}
		c, err = d.DialContext(context.Background(), "udp", dest.String()) // DİREKT
	}
	if err != nil {
		return nil, err
	}
	s.conns[dest] = c
	go s.readLoop(c, dest)
	return c, nil
}

func (s *selSession) readLoop(c net.Conn, dest netip.AddrPort) {
	buf := make([]byte, 65535)
	src := net.UDPAddrFromAddrPort(dest)
	for {
		_ = c.SetReadDeadline(time.Now().Add(60 * time.Second))
		n, err := c.Read(buf)
		if n > 0 {
			_, _ = s.resp.WriteFrom(buf[:n], src)
		}
		if err != nil {
			return
		}
	}
}

// handleDNS — blacklist domaini tünelden temiz çöz + ipSet'e ekle + yanıtla; değilse direkt ilet.
func (s *selSession) handleDNS(query []byte, dest netip.AddrPort) {
	var req dns.Msg
	if err := req.Unpack(query); err != nil || len(req.Question) == 0 {
		s.forwardDNSRaw(query, dest)
		return
	}
	q := req.Question[0]
	name := strings.TrimSuffix(q.Name, ".")

	if !s.pp.match.Match(name) {
		s.forwardDNSRaw(query, dest) // blacklist değil -> normal
		return
	}

	// blacklist -> TÜNELDEN temiz çöz (ISP zehirleyemez)
	ips, err := s.pp.tunNet.LookupContextHost(context.Background(), name)
	if err != nil || len(ips) == 0 {
		s.forwardDNSRaw(query, dest)
		return
	}
	v4 := make([]netip.Addr, 0, len(ips))
	for _, str := range ips {
		if a, e := netip.ParseAddr(str); e == nil && a.Is4() {
			v4 = append(v4, a)
		}
	}
	s.pp.ipset.AddAll(v4, time.Hour) // conntrack-benzeri kalıcılık

	resp := new(dns.Msg)
	resp.SetReply(&req)
	resp.RecursionAvailable = true
	if q.Qtype == dns.TypeA {
		for _, a := range v4 {
			resp.Answer = append(resp.Answer, &dns.A{
				Hdr: dns.RR_Header{Name: q.Name, Rrtype: dns.TypeA, Class: dns.ClassINET, Ttl: 300},
				A:   net.IP(a.AsSlice()),
			})
		}
	}
	// AAAA (veya A ama v4 yok): boş yanıt -> istemci IPv4'e düşer (tünel IPv4 taşır)
	b, err := resp.Pack()
	if err != nil {
		s.forwardDNSRaw(query, dest)
		return
	}
	_, _ = s.resp.WriteFrom(b, net.UDPAddrFromAddrPort(dest))
}

func (s *selSession) forwardDNSRaw(query []byte, dest netip.AddrPort) {
	d := &net.Dialer{Control: s.pp.directControl}
	c, err := d.DialContext(context.Background(), "udp", dest.String())
	if err != nil {
		return
	}
	defer c.Close()
	if _, err = c.Write(query); err != nil {
		return
	}
	buf := make([]byte, 65535)
	_ = c.SetReadDeadline(time.Now().Add(5 * time.Second))
	if n, _ := c.Read(buf); n > 0 {
		_, _ = s.resp.WriteFrom(buf[:n], net.UDPAddrFromAddrPort(dest))
	}
}

func (s *selSession) Close() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.closed = true
	for _, c := range s.conns {
		_ = c.Close()
	}
	return nil
}
