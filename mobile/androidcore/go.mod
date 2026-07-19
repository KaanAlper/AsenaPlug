module asena/androidcore

go 1.23

require github.com/Diniboy1123/usque v0.0.0

require golang.zx2c4.com/wireguard v0.0.0-20260522210424-ecfc5a8d5446 // indirect

// usque'yu FORK'a yönlendir (StartFullTunnelFd yardımcısı için — bkz. mobile/usque-fork/api_mobile.go).
// Yerel derleme:  replace github.com/Diniboy1123/usque => ../usque-local   (api_mobile.go kopyalı klon)
// Prod/CI:        replace github.com/Diniboy1123/usque => github.com/KaanAlper/usque <sürüm>
// replace github.com/Diniboy1123/usque => ../usque-local
