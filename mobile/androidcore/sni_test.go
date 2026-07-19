package androidcore

import (
	"crypto/tls"
	"net"
	"testing"
	"time"
)

// TestExtractSNI — gerçek bir TLS ClientHello üretip SNI'nın doğru çıkarıldığını doğrular.
func TestExtractSNI(t *testing.T) {
	cli, srv := net.Pipe()
	go func() {
		c := tls.Client(cli, &tls.Config{ServerName: "discord.com", InsecureSkipVerify: true})
		_ = c.Handshake() // ClientHello yazar (sonra srv okumadığı için el sıkışma tamamlanmaz — sorun değil)
	}()
	_ = srv.SetReadDeadline(time.Now().Add(3 * time.Second))
	buf := make([]byte, 4096)
	n, err := srv.Read(buf)
	if err != nil {
		t.Fatalf("ClientHello okunamadı: %v", err)
	}
	sni, needMore := extractSNI(buf[:n])
	if needMore {
		t.Fatalf("needMore=true (tam ClientHello beklenirdi), n=%d", n)
	}
	if sni != "discord.com" {
		t.Fatalf("SNI %q, beklenen discord.com", sni)
	}
}

// TestExtractSNI_Partial — kısmi veri needMore=true dönmeli.
func TestExtractSNI_Partial(t *testing.T) {
	// 0x16 (handshake) + versiyon + uzunluk=100 ama sadece 10 bayt -> needMore
	partial := []byte{0x16, 0x03, 0x01, 0x00, 0x64, 0x01, 0x00, 0x00, 0x60, 0x03}
	if _, needMore := extractSNI(partial); !needMore {
		t.Fatal("kısmi ClientHello için needMore=true beklenirdi")
	}
}

// TestExtractSNI_NotTLS — TLS olmayan veri ("", false) dönmeli.
func TestExtractSNI_NotTLS(t *testing.T) {
	if sni, needMore := extractSNI([]byte("GET / HTTP/1.1\r\n")); sni != "" || needMore {
		t.Fatalf("TLS olmayan veri için ('', false) beklenirdi, got (%q, %v)", sni, needMore)
	}
}
