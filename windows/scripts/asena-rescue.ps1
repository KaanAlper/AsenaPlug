#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Kurtarma görevi (boot + logon'da tetiklenir). Çökme / elektrik kesintisi
    sonrası Asena düzgün kapanamadıysa: DNS'i otomatiğe alır, IPv6 fail-closed
    kuralını ve TUN üzerindeki artık route'ları temizler ki sistem temiz açılsın.
#>
Set-StrictMode -Version 1.0
$ErrorActionPreference = "SilentlyContinue"

# Ortak mantık (Disable-KillSwitch burada)
. (Join-Path $PSScriptRoot 'asena-common.ps1')

$DataDir   = Join-Path $env:ProgramData "AsenaPlug"
$RunDir    = Join-Path $DataDir "run"
$LogFile   = Join-Path $DataDir "usque.log"
$StateFile = Join-Path $RunDir "state.json"
$TunName   = "usque"
$V6Rule    = "AsenaPlug-IPv6-FailClosed"
$ListenDns = "127.0.0.2"

function Write-Log($msg) {
    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    Add-Content -Path $LogFile -Value "$ts  [rescue] $msg" -Encoding UTF8 -ErrorAction SilentlyContinue
}

function Restore-Dns($prev) {
    # state.prevDns'i AYNEN geri koy: değer varsa kullanıcının statik DNS'i, boşsa DHCP.
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

# usque ayakta değilken (boot/logon ya da çökme sonrası) artık Asena yapılandırması
# varsa temizle ki internet kesin gelsin (kullanıcının korkusu: elektrik gidince
# DNS 127.0.0.2'de takılı kalması).
if (-not (Get-Process -Name "usque" -ErrorAction SilentlyContinue)) {
    # Çökme öncesi full moddaysak state.prevDns kullanıcının DNS'ini taşır — geri koy
    # (bunu yapmazsak DNS 1.1.1.1 statik takılı kalır). Bayat state.json da silinir.
    if (Test-Path $StateFile) {
        try {
            $st = Get-Content $StateFile -Raw | ConvertFrom-Json
            if ($st -and $st.prevDns) { Restore-Dns $st.prevDns }
        } catch {}
        Remove-Item $StateFile -Force -ErrorAction SilentlyContinue
    }

    # NRPT kurallarımızı kaldır
    Get-DnsClientNrptRule -ErrorAction SilentlyContinue |
        Where-Object { $_.NameServers -contains $ListenDns } |
        ForEach-Object { Remove-DnsClientNrptRule -Name $_.Name -Force -ErrorAction SilentlyContinue }

    # Sistem DNS'i 127.0.0.2'de KALMIŞ adapterleri otomatiğe al (tehlikeli kalıntı;
    # bunu yapmazsak internet gelmez). Kullanıcının kendi DNS'ine dokunmamak için
    # SADECE 127.0.0.2 olanları sıfırlarız.
    Get-NetAdapter -ErrorAction SilentlyContinue | ForEach-Object {
        $cur = (Get-DnsClientServerAddress -InterfaceAlias $_.Name -AddressFamily IPv4 -ErrorAction SilentlyContinue).ServerAddresses
        if ($cur -contains $ListenDns) {
            Set-DnsClientServerAddress -InterfaceAlias $_.Name -ResetServerAddresses -ErrorAction SilentlyContinue
        }
    }

    Remove-NetFirewallRule -Group $V6Rule -ErrorAction SilentlyContinue
    Remove-NetFirewallRule -Group "AsenaPlug-Full-IPv6Block" -ErrorAction SilentlyContinue

    # Kill-switch artığını temizle: usque çökünce default outbound=Block kalırsa TÜM
    # internet gider. usque yokken bunu KESİN kaldır (brick önleme — rescue'nin görevi).
    Disable-KillSwitch
    if ($tun) {
        Get-NetRoute -InterfaceIndex $tun.InterfaceIndex -ErrorAction SilentlyContinue |
            Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
    }
    Write-Log "kurtarma: NRPT/DNS(127.0.0.2)/firewall/route artıkları temizlendi."
}
