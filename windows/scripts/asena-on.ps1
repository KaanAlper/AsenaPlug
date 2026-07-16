#Requires -RunAsAdministrator
<#
.SYNOPSIS
    usque MASQUE tünelini başlat + routing kur.
    Mod (transport + scope) desired.json'dan okunur.

    transport: http2 | http3
    scope:     selective (fiziksel default, sadece blacklist /32 -> TUN)
               full      (split-default -> TUN, endpoint fiziksel'de pinli)

    -Transport / -Scope CLI argümanı verilirse desired.json'ı GEÇERSİZ KILAR
    (tray bunları doğrudan geçer — dosya round-trip'ine güvenmeyen güvenilir yol).
#>
param(
    [ValidateSet("", "http2", "http3")][string]$Transport = "",
    [ValidateSet("", "selective", "full")][string]$Scope = ""
)
Set-StrictMode -Version 1.0
$ErrorActionPreference = "Stop"

# Ortak mantık (blacklist parse + dnsproxy args) — kopya yerine tek kaynak
. (Join-Path $PSScriptRoot 'asena-common.ps1')

# --- Yollar (hepsi paylaşılan ProgramData; SYSTEM + kullanıcı ortak) ---
$InstallDir   = Join-Path $env:ProgramFiles "AsenaPlug"
$UsqueExe     = Join-Path $InstallDir "usque.exe"
$DnsproxyExe  = Join-Path $InstallDir "dnsproxy.exe"
$DataDir      = Join-Path $env:ProgramData "AsenaPlug"
$ConfigDir    = Join-Path $DataDir "config"
$RunDir       = Join-Path $DataDir "run"
$LogFile      = Join-Path $DataDir "usque.log"
$ConfigJson   = Join-Path $ConfigDir "config.json"
$BlacklistTxt = Join-Path $ConfigDir "asena-blacklist.txt"
$StateFile    = Join-Path $RunDir "state.json"
$DesiredFile  = Join-Path $RunDir "desired.json"
$StdoutLog    = Join-Path $DataDir "usque-stdout.log"
$StderrLog    = Join-Path $DataDir "usque-stderr.log"
$TunName      = "usque"
$V6Rule       = "AsenaPlug-IPv6-FailClosed"
$ListenDns    = "127.0.0.2"
# dnsproxy upstream: sorgular Asena TÜNELİNDEN geçer (resolver IP'leri TUN'a
# route'lanır) -> ISP zehirleyemez. Yandex:1253 düz-DNS artık TR'de zehirleniyordu.
$UpstreamDns1 = "1.1.1.1:53"
$UpstreamDns2 = "1.0.0.1:53"
$Resolvers    = @("1.1.1.1", "1.0.0.1")   # /32 -> TUN
$FullDns      = "1.1.1.1"          # full modda DNS tünelden geçer
# Cloudflare MASQUE endpoint altyapısı (içerik DEĞİL — bunları fiziksel'de pinlemek
# güvenli; usque'nin kendi bağlantısı tünele girip loop yapmasın). 162.159.192.0/19
# tüm Asena endpoint /24'lerini kapsar (.192/.193/.195/.198/.204).
$CfRanges     = @("162.159.192.0/19")

foreach ($d in @($RunDir, $ConfigDir, $DataDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

function Write-Log($msg) {
    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    Add-Content -Path $LogFile -Value "$ts  $msg" -Encoding UTF8 -ErrorAction SilentlyContinue
}

function Get-StaticDnsConfig([string]$alias) {
    # Adapterin STATİK IPv4 DNS'i. Get-DnsClientServerAddress statik/DHCP ayrımı
    # yapamaz (DHCP'den geleni de listeler); ayrım registry NameServer'da.
    # Boş dönüş = DHCP (restore'da ResetServerAddresses).
    try {
        $guid = (Get-NetAdapter -Name $alias -ErrorAction Stop).InterfaceGuid
        $key  = "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\$guid"
        $v = (Get-ItemProperty -Path $key -Name NameServer -ErrorAction SilentlyContinue).NameServer
        if ($v) { return ("$v".Trim() -replace '[ ;]+', ',') }
    } catch {}
    return ""
}

function Restore-Dns($prev) {
    # state.prevDns'i AYNEN geri koy: değer varsa kullanıcının statik DNS'i,
    # boşsa DHCP. (Eskiden hepsi DHCP'ye sıfırlanıyordu -> elle girilen DNS kayboluyordu.)
    if (-not $prev) { return }
    foreach ($p in $prev.PSObject.Properties) {
        if (-not (Get-NetAdapter -Name $p.Name -ErrorAction SilentlyContinue)) { continue }
        if ($p.Value) {
            Set-DnsClientServerAddress -InterfaceAlias $p.Name -ServerAddresses ($p.Value -split ',') -ErrorAction SilentlyContinue
        } else {
            Set-DnsClientServerAddress -InterfaceAlias $p.Name -ResetServerAddresses -ErrorAction SilentlyContinue
        }
    }
}

# --- desired oku ---
$transport = "http2"; $scope = "selective"
if (Test-Path $DesiredFile) {
    try {
        $d = Get-Content $DesiredFile -Raw | ConvertFrom-Json
        if ($d.transport) { $transport = "$($d.transport)" }
        if ($d.scope)     { $scope     = "$($d.scope)" }
    } catch { Write-Log "desired.json okunamadı, varsayılan kullanılıyor: $_" }
}
# CLI argümanları (tray'den) desired.json'ı geçersiz kılar — öncelikli
if ($Transport) { $transport = $Transport }
if ($Scope)     { $scope     = $Scope }
if ($transport -notin @("http2","http3")) { $transport = "http2" }
if ($scope     -notin @("selective","full")) { $scope = "selective" }
Write-Log "asena-on: transport=$transport scope=$scope (arg: '$Transport'/'$Scope')"

# --- 0. Mod değişimi -> CLEAN SLATE (declarative) ---
# Çalışan mod isteneni tutmuyorsa usque'yu öldür: TUN adapteri + üzerindeki TÜM
# route'lar (split-default + yüzlerce /32) KENDİLİĞİNDEN uçar. DNS/NRPT/IPv6
# artıklarını da temizle. Böylece "eski usque'ya bağlanma" ve "eski route artığı"
# imkânsız olur; reconciler tek asena-on çağırır (off->on dansı YOK -> thrashing yok).
$curState = $null
if (Test-Path $StateFile) { try { $curState = Get-Content $StateFile -Raw | ConvertFrom-Json } catch {} }
if ($curState -and (("$($curState.transport)" -ne $transport) -or ("$($curState.scope)" -ne $scope))) {
    Write-Log "mod değişti ($($curState.transport)/$($curState.scope) -> $transport/$scope): clean slate"
    Stop-ScheduledTask -TaskName "AsenaPlug_RouteSync" -ErrorAction SilentlyContinue
    Stop-Process -Name "usque" -Force -ErrorAction SilentlyContinue
    Get-DnsClientNrptRule -ErrorAction SilentlyContinue |
        Where-Object { $_.NameServers -contains $ListenDns } |
        ForEach-Object { Remove-DnsClientNrptRule -Name $_.Name -Force -ErrorAction SilentlyContinue }
    Remove-NetFirewallRule -Group $V6Rule -ErrorAction SilentlyContinue
    Remove-NetFirewallRule -Group "AsenaPlug-Full-IPv6Block" -ErrorAction SilentlyContinue
    # full'den ÇIKILIYORSA kullanıcının DNS'ini geri koy (selective DNS'e dokunmaz;
    # bunu yapmazsak 1.1.1.1 statik kalır ve "sistem DNS değişmez" sözü bozulur)
    if (("$($curState.scope)" -eq "full") -and ($scope -ne "full")) {
        Restore-Dns $curState.prevDns
    }
    Remove-Item $StateFile -Force -ErrorAction SilentlyContinue
    # TUN kaybolana dek bekle (route'lar uçsun -> temiz zemin), en fazla ~6sn
    $w = 0
    while ((Get-NetAdapter -Name $TunName -ErrorAction SilentlyContinue) -and $w -lt 24) {
        Start-Sleep -Milliseconds 250; $w++
    }
    Write-Log "clean slate tamam (TUN indi)."
}

# --- 1. usque başlat (http3 dene, TUN gelmezse http2'ye DÜŞ) ---
# http3 (QUIC/UDP 443) daha hızlı ama bazı ağlarda UDP 443 bloklu/throttle -> TUN
# hiç gelmez. O durumda otomatik --http2 (TCP+TLS) ile yeniden dener: "h3 hızı,
# olmazsa h2 sağlamlığı". Seçilen transport state.json'a GERÇEK haliyle yazılır.
function Start-UsqueAndWait([bool]$useHttp2) {
    $protoFlags = @(); if ($useHttp2) { $protoFlags = @("--http2") }
    $argList = @("-c", $ConfigJson, "nativetun", "--always-reconnect",
                 "--keepalive-period", "15s") + $protoFlags
    Write-Log "usque başlatılıyor: $($argList -join ' ')"
    $proc = Start-Process -FilePath $UsqueExe -ArgumentList $argList `
        -RedirectStandardOutput $StdoutLog -RedirectStandardError $StderrLog -NoNewWindow -PassThru
    $w = 0
    while (-not (Get-NetAdapter -Name $TunName -ErrorAction SilentlyContinue) -and $w -lt 24) {
        Start-Sleep -Milliseconds 500; $w++
    }
    if (Get-NetAdapter -Name $TunName -ErrorAction SilentlyContinue) { return $proc.Id }
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue   # başarısız -> temiz zemin
    return $null
}

$usque = Get-Process -Name "usque" -ErrorAction SilentlyContinue
if (-not $usque) {
    if (-not (Test-Path $UsqueExe))   { throw "usque.exe yok: $UsqueExe" }
    if (-not (Test-Path $ConfigJson)) { throw "config.json yok: $ConfigJson — 'usque register' çalıştır" }

    $usquePid = Start-UsqueAndWait ($transport -eq "http2")
    if (-not $usquePid -and $transport -eq "http3") {
        Write-Log "http3/QUIC TUN gelmedi -> http2 fallback (UDP 443 bloklu olabilir)"
        $w = 0
        while ((Get-NetAdapter -Name $TunName -ErrorAction SilentlyContinue) -and $w -lt 12) {
            Start-Sleep -Milliseconds 250; $w++
        }
        $transport = "http2"    # GERÇEK transport -> state.json + DNS mantığı bunu görsün
        $usquePid = Start-UsqueAndWait $true
    }
    if (-not $usquePid) { throw "TUN adapteri '$TunName' gelmedi (h3+h2 denendi). usque-stderr.log'a bak." }
} else {
    $usquePid = $usque.Id
    Write-Log "usque zaten çalışıyor (PID $usquePid)."
    # Zaten çalışan usque (ör. ağ-değişimi reapply): TUN ayakta mı doğrula
    $waited = 0
    while (-not (Get-NetAdapter -Name $TunName -ErrorAction SilentlyContinue) -and $waited -lt 24) {
        Start-Sleep -Milliseconds 500; $waited++
    }
    if (-not (Get-NetAdapter -Name $TunName -ErrorAction SilentlyContinue)) {
        throw "TUN '$TunName' yok (usque çalışıyor ama adapter gelmedi)."
    }
}
Write-Log "TUN '$TunName' ayakta."

# MTU/MSS clamp (Linux'taki 'tcp option maxseg size set 1220' eşdeğeri):
# tünel MTU'su fiziksel'den (1500) küçük. Set etmezsek Windows büyük paket
# gönderir, tünele sığmaz, sessizce düşer -> siteler yarım açılır (HTML gelir,
# resim/CSS/JS gelmez). MTU 1260 -> ilan edilen MSS ~1220 (Linux'un kanıtlı değeri).
Set-NetIPInterface -InterfaceAlias $TunName -NlMtuBytes 1260 -ErrorAction SilentlyContinue
Write-Log "TUN MTU -> 1260 (MSS ~1220; yarım yüklenmeyi önler)."

# --- 2. Default gateway / fiziksel arayüz ---
$defRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
            Where-Object { $_.NextHop -ne "0.0.0.0" } |
            Sort-Object RouteMetric | Select-Object -First 1
if (-not $defRoute) { throw "Default gateway bulunamadı." }
$gwIP      = $defRoute.NextHop
$physIface = (Get-NetAdapter -InterfaceIndex $defRoute.InterfaceIndex).Name
Write-Log "Gateway: $gwIP via $physIface"

# --- 3. Endpoint pin (loop önler) ---
$pins = New-Object System.Collections.Generic.List[string]
function Add-Pin([string]$prefix) {
    if ([string]::IsNullOrWhiteSpace($prefix)) { return }
    Get-NetRoute -DestinationPrefix $prefix -ErrorAction SilentlyContinue |
        Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
    New-NetRoute -DestinationPrefix $prefix -InterfaceAlias $physIface -NextHop $gwIP `
        -RouteMetric 1 -ErrorAction SilentlyContinue | Out-Null
    $pins.Add($prefix)
    Write-Log "Endpoint pin: $prefix -> $physIface"
}

# http2 (TCP) ise gerçek endpoint'i bul; bulunamazsa (http3/UDP) Asena aralıklarını pinle
$endpoint = $null
try {
    $endpoint = (Get-NetTCPConnection -OwningProcess $usquePid -RemotePort 443 `
                 -State Established -ErrorAction SilentlyContinue |
                 Select-Object -First 1).RemoteAddress
} catch {}
if ($endpoint) { Add-Pin "$endpoint/32" }
# full modda VEYA endpoint dinamik bulunamadıysa: tüm Cloudflare MASQUE endpoint
# aralıklarını fiziksel'de pinle ki usque'nin kendi bağlantısı tünele girip loop yapmasın.
if ($scope -eq "full" -or -not $endpoint) {
    foreach ($r in $CfRanges) { Add-Pin $r }
}

# --- 4. Scope'a göre routing ---
$prevDns = $null   # full modda dolar; state.json'a yazılır (asena-off geri koyar)
if ($scope -eq "full") {
    # split-default: fiziksel default'u SİLMEDEN geçersiz kıl (teardown temiz)
    foreach ($half in @("0.0.0.0/1","128.0.0.0/1")) {
        Get-NetRoute -DestinationPrefix $half -InterfaceAlias $TunName -ErrorAction SilentlyContinue |
            Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
        New-NetRoute -DestinationPrefix $half -InterfaceAlias $TunName -RouteMetric 1 `
            -ErrorAction SilentlyContinue | Out-Null
    }

    # DNS: TÜM ayakta fiziksel adapterlerde değiştir (yalnız default arayüz yetmez:
    # Windows'un paralel çözümlemesi -SMHNR- ikinci arayüzden ISP DNS'ine sorup
    # sızdırabilir). Değiştirmeden önce her adapterin STATİK DNS'i prevDns'e alınır.
    # full->full reconnect'te mevcut DNS bizim 1.1.1.1'imiz olduğundan snapshot
    # ALINMAZ, önceki state'in prevDns'i taşınır (yoksa kendi değerimizi "kullanıcının
    # ayarı" sanıp kalıcılaştırırdık).
    if ($curState -and ("$($curState.scope)" -eq "full") -and $curState.prevDns) {
        $prevDns = $curState.prevDns
    }
    $targets = @{}
    Get-NetAdapter -Physical -ErrorAction SilentlyContinue |
        Where-Object { $_.Status -eq "Up" -and $_.Name -ne $TunName } |
        ForEach-Object { $targets[$_.Name] = $true }
    $targets[$physIface] = $true   # default arayüz sanal olsa bile kapsansın
    if (-not $prevDns) {
        $snap = [ordered]@{}
        foreach ($name in @($targets.Keys | Sort-Object)) {
            $curDns = Get-StaticDnsConfig $name
            # Mevcut statik DNS zaten BİZİM FullDns'imizse (önceki full oturum düzgün
            # restore etmemiş), "orijinal" diye onu kaydetme -> "" (DHCP) yaz. Yoksa
            # 1.1.1.1 zincirleme kalıcılaşırdı (state.json'da prevDns=1.1.1.1 bug'ı).
            if ($curDns -eq $FullDns) { $curDns = "" }
            $snap[$name] = $curDns
        }
        $prevDns = $snap
    }
    foreach ($name in @($targets.Keys)) {
        Set-DnsClientServerAddress -InterfaceAlias $name -ServerAddresses @($FullDns) -ErrorAction SilentlyContinue
    }

    # IPv6 LEAK koruması: usque IPv4-only. Full modda IPv6 internet'i (2000::/3 global
    # unicast) blokla -> uygulamalar IPv4'e (tünele) düşer, gerçek IPv6 sızmaz.
    # Teardown'da AsenaPlug-Full-IPv6Block grubu kaldırılır.
    Remove-NetFirewallRule -Group "AsenaPlug-Full-IPv6Block" -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName "AsenaPlug-Full-IPv6Block" -Group "AsenaPlug-Full-IPv6Block" `
        -Direction Outbound -Action Block -RemoteAddress "2000::/3" -Profile Any -ErrorAction SilentlyContinue | Out-Null
    # DNS sızıntısı: router'ın link-local (fe80::) veya ULA DNS'i 2000::/3'e GİRMEZ,
    # sorgular oradan dışarı sızardı. Bu aralıklar için port 53'ü ayrıca blokla.
    # (fe80/ULA'nın kendisi bloklanmaz — yalnız DNS; LAN erişimi bozulmaz.)
    foreach ($proto in @("UDP","TCP")) {
        New-NetFirewallRule -DisplayName "AsenaPlug-Full-DnsV6Block-$proto" -Group "AsenaPlug-Full-IPv6Block" `
            -Direction Outbound -Action Block -Protocol $proto -RemotePort 53 `
            -RemoteAddress @("fe80::/10","fc00::/7") -Profile Any -ErrorAction SilentlyContinue | Out-Null
    }
    Write-Log "FULL: split-default -> $TunName, DNS=$FullDns ($($targets.Count) adapter, prevDns kayıtlı), IPv6+v6DNS bloklu"
}
else {
    # selective: fiziksel default kalır; TUN yüksek metric. SİSTEM DNS'İNE DOKUNMAYIZ.
    # Sadece blacklist domainleri NRPT ile dnsproxy'ye (clean DNS) yönlendirilir;
    # gerisi normal ISP DNS kullanır (zehirli/normal kalır). dnsproxy ölse bile
    # sadece blacklist çözümü etkilenir, internet ayakta kalır.
    Set-NetIPInterface -InterfaceAlias $TunName -InterfaceMetric 5000 -ErrorAction SilentlyContinue

    # blacklist oku (ortak parse -> Python state.py ile aynı kural)
    $domains = @(Get-BlacklistDomains $BlacklistTxt)

    # eski NRPT kurallarımızı temizle (NameServers 127.0.0.2 = bizimkiler)
    Get-DnsClientNrptRule -ErrorAction SilentlyContinue |
        Where-Object { $_.NameServers -contains $ListenDns } |
        ForEach-Object { Remove-DnsClientNrptRule -Name $_.Name -Force -ErrorAction SilentlyContinue }

    if ($domains.Count -eq 0) {
        Write-Log "SELECTIVE: blacklist boş — DNS'e dokunulmadı, hiçbir şey unblock edilmedi."
    } else {
        Stop-Process -Name "dnsproxy" -Force -ErrorAction SilentlyContinue
        if (Test-Path $DnsproxyExe) {
            # Cache: min-ttl FLOOR (düşük-TTL/TTL-0 CDN'leri sabitler) + optimistic
            # (stale cevabı ANINDA verir, arkada tazeler). Tarayıcı ile route-sync
            # aynı sabit cevabı görür -> CDN rotasyonu azalır. Asıl uyuşmazlık çözümü
            # route-sync BİRİKİMİ (görülen tüm IP'ler ~1sa route'lu kalır = Linux
            # nftset) + eager warm-up. (route-sync watchdog AYNI argümanları kullanır.)
            $dnsArgs = Get-DnsproxyArgs $ListenDns $UpstreamDns1 $UpstreamDns2
            $dnsProc = Start-Process -FilePath $DnsproxyExe -ArgumentList $dnsArgs -NoNewWindow -PassThru
            $ok = $false; $tries = 0
            while (-not $ok -and $tries -lt 10) {
                Start-Sleep -Milliseconds 300
                $alive = Get-Process -Id $dnsProc.Id -ErrorAction SilentlyContinue
                $listen = Get-NetUDPEndpoint -LocalAddress $ListenDns -LocalPort 53 -ErrorAction SilentlyContinue
                if ($alive -and $listen) { $ok = $true }
                $tries++
            }
            if ($ok) {
                # dnsproxy upstream sorgularını (1.1.1.1/1.0.0.1) Asena tüneline sok
                # -> DNS cevabı ISP tarafından zehirlenemez, gerçek IP gelir.
                foreach ($r in $Resolvers) {
                    Get-NetRoute -DestinationPrefix "$r/32" -ErrorAction SilentlyContinue |
                        Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
                    New-NetRoute -DestinationPrefix "$r/32" -InterfaceAlias $TunName -RouteMetric 1 -ErrorAction SilentlyContinue | Out-Null
                }
                # SADECE blacklist domainleri -> dnsproxy (NRPT). Sistem DNS değişmez.
                # Tek çağrıda tüm namespace'ler (324 ayrı cmdlet yerine) -> hızlı.
                # Hem "site.com" (apex) hem ".site.com" (subdomain) girilir — nokta-önekli
                # suffix bazı Windows sürümlerinde apex'i EŞLEMEZ, apex kaçırılırdı.
                $ns = @($domains | ForEach-Object { $_; "." + $_ })
                Add-DnsClientNrptRule -Namespace $ns -NameServers $ListenDns -ErrorAction SilentlyContinue
                Clear-DnsClientCache -ErrorAction SilentlyContinue  # eski zehirli kayıtları at
                Write-Log "SELECTIVE: $($domains.Count) domain NRPT, resolver'lar tünelden (sistem DNS değişmedi)."
                # NOT: blacklist /32 route'ları route-sync ARKA PLANDA doldurur
                # (connect'i bloklamaz -> "Connected" hemen). Eskiden burada senkron
                # warm-up vardı; kullanıcı beklemesin diye arka plana alındı.
            } else {
                Write-Log "UYARI: dnsproxy dinlemedi — NRPT eklenmedi, blacklist devre dışı."
            }
        } else {
            Write-Log "UYARI: dnsproxy.exe yok — blacklist DNS atlandı."
        }
        # route-sync ARKA PLANDA tüm blacklist route'larını kurar: cache preload
        # (önceki oturumdan ANINDA) + paralel çöz + /32 route + IPv6 fail-closed.
        # Connect'i BLOKLAMAZ -> "Connected" hemen görünür, route'lar arka planda dolar.
        Start-ScheduledTask -TaskName "AsenaPlug_RouteSync" -ErrorAction SilentlyContinue
    }
}

# --- 4b. Kill-switch DEVRE DIŞI ---
# WFP helper'ın permit-tun kuralı tünel trafiğini eşleştirmiyor -> yeni bağlantıları
# (DNS/youtube/oyun) blokluyordu. Windows'ta test edilip düzeltilene dek HER ZAMAN
# kapalı; çalışan artık helper varsa durdurulur (dinamik WFP filtreleri kendiliğinden
# uçar). (Enable-KillSwitch kodu asena-common'da ileride düzeltilmek üzere duruyor.)
Disable-KillSwitch

# --- 5. state.json yaz (tek doğru kaynak) ---
$state = [ordered]@{
    transport = $transport
    scope     = $scope
    pid       = $usquePid
    endpoint  = $endpoint
    pins      = @($pins)
    prevDns   = $prevDns          # full: adapter -> önceki statik DNS ("" = DHCP); selective: null
    gwIP      = $gwIP             # bağlanınca kullanılan fiziksel gateway (ağ-değişimi tespiti)
    physIface = $physIface        # fiziksel arayüz adı (endpoint pin'i burada)
    killswitch = $false                                  # kill-switch devre dışı (bkz. 4b)
    started   = (Get-Date).ToString("o")
}
$state | ConvertTo-Json -Compress -Depth 4 | Set-Content -Path $StateFile -Encoding UTF8
Write-Log "asena-on OK | $transport/$scope | pid=$usquePid | pins=$($pins -join ',')"
