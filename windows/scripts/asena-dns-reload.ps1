#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Blacklist değişince taze yenile: NRPT kurallarını blacklist'e göre yeniden kur
    (sadece listedeki domainler dnsproxy/clean DNS'e gider; sistem DNS değişmez),
    dnsproxy'yi diri tut, /32 route'ları + DNS cache'i temizleyip route-sync'i
    sıfırdan başlat.
#>
Set-StrictMode -Version 1.0
$ErrorActionPreference = "SilentlyContinue"

# Ortak mantık (blacklist parse + dnsproxy args) — asena-on ile TEK kaynak
. (Join-Path $PSScriptRoot 'asena-common.ps1')

$DataDir      = Join-Path $env:ProgramData "AsenaPlug"
$ConfigDir    = Join-Path $DataDir "config"
$RunDir       = Join-Path $DataDir "run"
$LogFile      = Join-Path $DataDir "usque.log"
$BlacklistTxt = Join-Path $ConfigDir "asena-blacklist.txt"
$ResolvedFile = Join-Path $RunDir "asena-resolved-ips.txt"
$DnsproxyExe  = Join-Path (Join-Path $env:ProgramFiles "AsenaPlug") "dnsproxy.exe"
$TunName      = "usque"
$V6Rule       = "AsenaPlug-IPv6-FailClosed"
$ListenDns    = "127.0.0.2"
$UpstreamDns1 = "1.1.1.1:53"
$UpstreamDns2 = "1.0.0.1:53"
$Resolvers    = @("1.1.1.1", "1.0.0.1")
$RouteExe     = Join-Path $env:SystemRoot "System32\route.exe"

function Write-Log($msg) {
    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    Add-Content -Path $LogFile -Value "$ts  [dns-reload] $msg" -Encoding UTF8 -ErrorAction SilentlyContinue
}

$tun = Get-NetAdapter -Name $TunName -ErrorAction SilentlyContinue
if (-not $tun) {
    Write-Log "Asena kapalı — atlandı."
    exit 0
}

Clear-DnsClientCache -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName "AsenaPlug_RouteSync" -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 300

# Eski /32 host route'ları + v6 kuralı + defter + eski NRPT kurallarımızı temizle
Get-NetRoute -InterfaceIndex $tun.InterfaceIndex -ErrorAction SilentlyContinue |
    Where-Object { $_.DestinationPrefix -like "*/32" } |
    Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
Remove-NetFirewallRule -Group $V6Rule -ErrorAction SilentlyContinue
Remove-Item $ResolvedFile -Force -ErrorAction SilentlyContinue
Get-DnsClientNrptRule -ErrorAction SilentlyContinue |
    Where-Object { $_.NameServers -contains $ListenDns } |
    ForEach-Object { Remove-DnsClientNrptRule -Name $_.Name -Force -ErrorAction SilentlyContinue }

# Blacklist oku (ortak parse)
$domains = @(Get-BlacklistDomains $BlacklistTxt)

if ($domains.Count -eq 0) {
    Stop-Process -Name "dnsproxy" -Force -ErrorAction SilentlyContinue
    Write-Log "blacklist boş — NRPT/dnsproxy kaldırıldı, hiçbir şey unblock edilmiyor."
    exit 0
}

# dnsproxy diri mi? değilse başlat + dinlediğini doğrula
if (-not (Get-Process -Name "dnsproxy" -ErrorAction SilentlyContinue)) {
    if (Test-Path $DnsproxyExe) {
        # Cache PIN — asena-on/route-sync ile AYNI (tarayıcı/route-sync uyuşmazlığı yok)
        Start-Process -FilePath $DnsproxyExe `
            -ArgumentList (Get-DnsproxyArgs $ListenDns $UpstreamDns1 $UpstreamDns2) `
            -NoNewWindow -ErrorAction SilentlyContinue
    }
}
$ok = $false; $tries = 0
while (-not $ok -and $tries -lt 10) {
    Start-Sleep -Milliseconds 300
    if ((Get-Process -Name "dnsproxy" -ErrorAction SilentlyContinue) -and
        (Get-NetUDPEndpoint -LocalAddress $ListenDns -LocalPort 53 -ErrorAction SilentlyContinue)) { $ok = $true }
    $tries++
}

if ($ok) {
    # resolver IP'lerini Asena tüneline route et (zehirsiz DNS) — /32 temizliğinde silindi
    foreach ($r in $Resolvers) {
        Get-NetRoute -DestinationPrefix "$r/32" -ErrorAction SilentlyContinue |
            Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
        New-NetRoute -DestinationPrefix "$r/32" -InterfaceAlias $TunName -RouteMetric 1 -ErrorAction SilentlyContinue | Out-Null
    }
    # Hem apex ("site.com") hem subdomain (".site.com") — asena-on ile aynı gerekçe
    $ns = @($domains | ForEach-Object { $_; "." + $_ })
    Add-DnsClientNrptRule -Namespace $ns -NameServers $ListenDns -ErrorAction SilentlyContinue

    # /32 route'ları route-sync ARKA PLANDA yeniden kurar (yukarıda temizlendi).
    # Bloklamaz -> DNS yenile hızlı döner; route'lar arka planda dolar.
    Start-ScheduledTask -TaskName "AsenaPlug_RouteSync" -ErrorAction SilentlyContinue
    Write-Log "tamam — $($domains.Count) domain NRPT, route-sync (arka plan) başlatıldı."
} else {
    Write-Log "UYARI: dnsproxy dinlemedi — NRPT eklenmedi."
}
