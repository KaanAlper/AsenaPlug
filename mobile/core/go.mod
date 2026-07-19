module asena/core

go 1.23

require (
	github.com/Diniboy1123/usque v0.0.0
	golang.zx2c4.com/wireguard v0.0.0-20260522210424-ecfc5a8d5446
	// TODO(build): Outline SDK — tun2socks/dialer
	// github.com/Jigsaw-Code/outline-sdk v0.0.20
)

// usque'yu FORK'a yönlendir (ConnectTunnel yardımcısı için — bkz. mobile/usque-fork/api_mobile.go).
// Yerel test:  replace github.com/Diniboy1123/usque => ../usque-local
// Prod:        replace github.com/Diniboy1123/usque => github.com/<sen>/usque <sürüm>
// replace github.com/Diniboy1123/usque => ../usque-local
