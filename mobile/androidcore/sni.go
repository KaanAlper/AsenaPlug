// sni.go — SNI-tabanlı yönlendirme (selective modun DNS-bağımsız kalbi).
//
// SORUN: Selective mod, hangi IP'lerin tünele gireceğini DNS'i (:53) dinleyerek öğrenir.
// Tarayıcı DoH/DoT (şifreli DNS) kullanınca :53 baypas edilir -> blacklist siteleri tünele
// girmez -> engelli kalır. ÇÖZÜM: 443 (HTTPS) akışında TLS ClientHello'daki SNI'yı (gerçek
// alan adı) okuyup ona göre tünel/direkt karar veririz. DNS nasıl çözülürse çözülsün doğru
// yönlendirir -> DoH/DoT/IPv6-DNS/DNS-cache baypaslarının hepsini kapatır.

package androidcore

import (
	"context"
	"net"
	"net/netip"
	"sync"
	"syscall"
	"time"

	"golang.zx2c4.com/wireguard/tun/netstack"
)

// extractSNI — TLS ClientHello'dan server_name (SNI) çıkarır.
// Döner (sni, needMore): needMore=true ise data kısmi ClientHello (daha fazla bayt bekle);
// TLS değilse ya da SNI yoksa ("", false).
func extractSNI(b []byte) (string, bool) {
	if len(b) < 5 {
		return "", true
	}
	if b[0] != 0x16 { // TLS handshake record değil
		return "", false
	}
	recLen := int(b[3])<<8 | int(b[4])
	if recLen < 4 || recLen > 1<<14 {
		return "", false
	}
	if len(b) < 5+recLen {
		return "", true // tam kayıt gelmedi
	}
	hs := b[5 : 5+recLen]
	if len(hs) < 4 || hs[0] != 0x01 { // ClientHello değil
		return "", false
	}
	p := hs[4:]
	if len(p) < 34 { // version(2)+random(32)
		return "", false
	}
	p = p[34:]
	if len(p) < 1 || len(p) < 1+int(p[0]) { // sessionID
		return "", false
	}
	p = p[1+int(p[0]):]
	if len(p) < 2 { // cipher suites
		return "", false
	}
	csLen := int(p[0])<<8 | int(p[1])
	if len(p) < 2+csLen {
		return "", false
	}
	p = p[2+csLen:]
	if len(p) < 1 || len(p) < 1+int(p[0]) { // compression
		return "", false
	}
	p = p[1+int(p[0]):]
	if len(p) < 2 { // extensions
		return "", false
	}
	extLen := int(p[0])<<8 | int(p[1])
	p = p[2:]
	if len(p) < extLen {
		return "", false
	}
	ext := p[:extLen]
	for len(ext) >= 4 {
		etype := int(ext[0])<<8 | int(ext[1])
		elen := int(ext[2])<<8 | int(ext[3])
		ext = ext[4:]
		if len(ext) < elen {
			break
		}
		data := ext[:elen]
		ext = ext[elen:]
		if etype != 0x0000 { // server_name değil
			continue
		}
		if len(data) < 2 {
			continue
		}
		listLen := int(data[0])<<8 | int(data[1])
		d := data[2:]
		if len(d) < listLen {
			continue
		}
		d = d[:listLen]
		for len(d) >= 3 {
			ntype := d[0]
			nlen := int(d[1])<<8 | int(d[2])
			d = d[3:]
			if len(d) < nlen {
				break
			}
			name := d[:nlen]
			d = d[nlen:]
			if ntype == 0 { // host_name
				return string(name), false
			}
		}
	}
	return "", false
}

// lazySNIConn — 443 TCP akışı: ilk yazımı (ClientHello) tamponlar, SNI'yı okur, blacklist
// eşleşmesine göre TÜNEL ya da DİREKT bağlanır. Bağlantı ilk Write'a (ya da 3sn güvenlik
// zamanlayıcısına) kadar ERTELENİR. Karar bir kez verilir; sonra saf proxy (throughput maliyeti yok).
type lazySNIConn struct {
	addr          string
	ip            netip.Addr
	ipset         *ipSet
	match         *matcher
	tunNet        *netstack.Net
	directControl func(string, string, syscall.RawConn) error

	mu     sync.Mutex
	dialed bool
	conn   net.Conn
	err    error
	buf    []byte
	done   chan struct{}
	once   sync.Once
}

func newLazySNIConn(addr string, ip netip.Addr, ipset *ipSet, match *matcher, tunNet *netstack.Net,
	dc func(string, string, syscall.RawConn) error) *lazySNIConn {
	l := &lazySNIConn{addr: addr, ip: ip, ipset: ipset, match: match, tunNet: tunNet, directControl: dc,
		done: make(chan struct{})}
	// ClientHello hiç gelmezse (server-first vb.) 3sn sonra ipset'e göre bağlan -> asılı kalma.
	time.AfterFunc(3*time.Second, l.ensureDial)
	return l
}

// ensureDial — bir kez: SNI'ya (varsa) ve ipset'e göre karar verip bağlanır, tamponu yazar.
func (l *lazySNIConn) ensureDial() {
	l.once.Do(func() {
		l.mu.Lock()
		sni, _ := extractSNI(l.buf)
		buf := l.buf
		l.mu.Unlock()

		// SNI blacklist'te eşleşir VEYA (SNI yoksa) DNS'ten öğrenilen ipset içindeyse -> TÜNEL.
		tunnel := (sni != "" && l.match.Match(sni)) || (l.ip.IsValid() && l.ipset.Contains(l.ip))

		ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		var c net.Conn
		var e error
		if tunnel {
			c, e = l.tunNet.DialContext(ctx, "tcp", l.addr)
		} else {
			d := &net.Dialer{Control: l.directControl}
			c, e = d.DialContext(ctx, "tcp", l.addr)
		}
		l.mu.Lock()
		l.conn, l.err = c, e
		if e == nil && len(buf) > 0 {
			_, l.err = c.Write(buf) // tamponlanan ClientHello'yu ilet
		}
		l.buf = nil
		l.dialed = true
		l.mu.Unlock()
		close(l.done)
	})
}

func (l *lazySNIConn) Write(p []byte) (int, error) {
	l.mu.Lock()
	if l.dialed {
		c, e := l.conn, l.err
		l.mu.Unlock()
		if e != nil {
			return 0, e
		}
		return c.Write(p)
	}
	l.buf = append(l.buf, p...)
	_, needMore := extractSNI(l.buf)
	tooBig := len(l.buf) >= 16384
	l.mu.Unlock()
	if needMore && !tooBig {
		return len(p), nil // tamponla, ClientHello'nun tamamını bekle
	}
	l.ensureDial()
	l.mu.Lock()
	e := l.err
	l.mu.Unlock()
	if e != nil {
		return 0, e
	}
	return len(p), nil
}

func (l *lazySNIConn) Read(p []byte) (int, error) {
	<-l.done // bağlanana kadar bekle (443'te istemci önce ClientHello yazar -> hızlı)
	l.mu.Lock()
	c, e := l.conn, l.err
	l.mu.Unlock()
	if e != nil {
		return 0, e
	}
	return c.Read(p)
}

func (l *lazySNIConn) Close() error {
	l.ensureDial()
	l.mu.Lock()
	c := l.conn
	l.mu.Unlock()
	if c != nil {
		return c.Close()
	}
	return nil
}

func (l *lazySNIConn) CloseRead() error {
	<-l.done
	if c, ok := l.conn.(interface{ CloseRead() error }); ok {
		return c.CloseRead()
	}
	return nil
}

func (l *lazySNIConn) CloseWrite() error {
	l.ensureDial()
	<-l.done
	if c, ok := l.conn.(interface{ CloseWrite() error }); ok {
		return c.CloseWrite()
	}
	return nil
}

func (l *lazySNIConn) RemoteAddr() net.Addr {
	a, _ := net.ResolveTCPAddr("tcp", l.addr)
	return a
}

func (l *lazySNIConn) LocalAddr() net.Addr {
	l.mu.Lock()
	c := l.conn
	l.mu.Unlock()
	if c != nil {
		return c.LocalAddr()
	}
	return &net.TCPAddr{}
}

// Deadline'lar: bağlanmadan önce no-op (dial kendi timeout'unu kullanır), sonra delege — BLOKLAMAZ.
func (l *lazySNIConn) SetDeadline(t time.Time) error      { return l.setDL(0, t) }
func (l *lazySNIConn) SetReadDeadline(t time.Time) error  { return l.setDL(1, t) }
func (l *lazySNIConn) SetWriteDeadline(t time.Time) error { return l.setDL(2, t) }

func (l *lazySNIConn) setDL(which int, t time.Time) error {
	l.mu.Lock()
	c, dialed := l.conn, l.dialed
	l.mu.Unlock()
	if !dialed || c == nil {
		return nil
	}
	switch which {
	case 1:
		return c.SetReadDeadline(t)
	case 2:
		return c.SetWriteDeadline(t)
	default:
		return c.SetDeadline(t)
	}
}
