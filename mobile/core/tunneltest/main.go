// tunneltest — PoC Adım 1: MASQUE tüneli mobilde/masaüstünde çalışıyor mu? (VpnService GEREKMEZ)
//
// Kanıt: usque tünelini kurar, tünel netstack'i (tunNet) üzerinden DNS + HTTPS yapar.
// Cloudflare trace'te "warp=on" görürsek MASQUE dialer'ı çalışıyor demektir.
//
//   go run . /path/to/config.json      # config.json = 'usque register' çıktısı
//
// api.ConnectTunnel usque FORK'undan gelir (bkz. mobile/usque-fork/api_mobile.go).
// go.mod replace ile fork'a yönlendir:
//   replace github.com/Diniboy1123/usque => github.com/<sen>/usque <sürüm>

package main

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"github.com/Diniboy1123/usque/api"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("kullanım: go run . <config.json>")
		os.Exit(2)
	}
	cfg, err := os.ReadFile(os.Args[1])
	must("config oku", err)

	fmt.Println("MASQUE tüneli kuruluyor (HTTP/2)…")
	tunNet, cancel, err := api.ConnectMobile(string(cfg), true /*http2*/)
	must("ConnectMobile", err)
	defer cancel()

	time.Sleep(3 * time.Second) // tünel el sıkışsın

	ctx := context.Background()

	// (1) TÜNELDEN DNS — zehirlenmez
	ips, err := tunNet.LookupContextHost(ctx, "cloudflare.com")
	if err != nil {
		fmt.Println("DNS(tünel) hata:", err)
	} else {
		fmt.Println("DNS(tünel) cloudflare.com ->", ips)
	}

	// (2) TÜNELDEN HTTPS — trace warp=on olmalı
	client := &http.Client{
		Timeout:   15 * time.Second,
		Transport: &http.Transport{DialContext: tunNet.DialContext}, // <- MASQUE dialer
	}
	resp, err := client.Get("https://cloudflare.com/cdn-cgi/trace")
	must("trace iste", err)
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)

	fmt.Println("\n--- cloudflare trace (tünelden) ---")
	fmt.Print(string(body))
	fmt.Println("--- 'warp=on' görüyorsan MASQUE dialer ÇALIŞIYOR (selective'in kalbi hazır) ---")
}

func must(what string, err error) {
	if err != nil {
		fmt.Printf("HATA (%s): %v\n", what, err)
		os.Exit(1)
	}
}
