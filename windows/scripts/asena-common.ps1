<#
.SYNOPSIS
    asena-*.ps1 scriptlerinin PAYLAŞTIĞI mantık — TEK KAYNAK.

    Eskiden blacklist parse + dnsproxy argümanları asena-on / asena-route-sync /
    asena-dns-reload'da KOPYA'ydı. Drift = gizli bug (apex NRPT hatası tam bu yüzden
    2 dosyada ayrı düzeltilmişti; dnsproxy args uyuşmazlığı cache PIN'i bozardı).
    Artık her script bunu dot-source eder: . (Join-Path $PSScriptRoot 'asena-common.ps1')
#>

# Blacklist dosyasını domain listesine çevir (yorum/wildcard/port temizle, küçült,
# TLD doğrula, sırala-tekrarsız). Boşsa boş dizi. asenaplug/state.py normalize_domain
# ile AYNI kural (Python/PS tutarlılığı).
function Get-BlacklistDomains([string]$path) {
    if (-not (Test-Path $path)) { return @() }
    Get-Content $path |
        ForEach-Object { ($_ -replace '#.*', '').Trim() } |
        Where-Object { $_ -ne '' } |
        ForEach-Object { (($_ -replace '^\*\.', '') -replace ':\d+.*$', '').TrimEnd('.').ToLower() } |
        Where-Object { $_ -match '^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$' } |
        Sort-Object -Unique
}

# dnsproxy başlatma argümanları — 3 script'te AYNI olmalı (cache PIN: aynı ayarlar
# yoksa route-sync watchdog restart'ında cache sıfırlanır, tarayıcı/route-sync
# uyuşmazlığı geri gelir). Cache: min-ttl FLOOR + optimistic (stale ANINDA döner).
function Get-DnsproxyArgs([string]$listen, [string]$up1, [string]$up2) {
    return @("-l", $listen, "-p", "53", "-u", $up1, "-u", $up2,
             "--cache", "--cache-optimistic", "--cache-min-ttl=600", "--cache-size=4194304")
}

# --- Kill-switch (OPSİYONEL; sadece full mod) ---
# WFP DYNAMIC session ile yapılır: asena-killswitch.exe bir dinamik WFP oturumu tutar;
# süreç ÖLÜNCE (taskkill / çökme / güç kesintisi sonrası reboot) filtreler Windows
# tarafından OTOMATİK silinir -> BRICK İMKANSIZ. (Eski NetFirewall DefaultOutboundAction
# yaklaşımı global+kalıcıydı, çökmede internet kilitli kalabiliyordu; bu yüzden bırakıldı.)
#
# Enable = helper'ı başlat (o WFP filtrelerini kurar: permit TUN/usque/endpoint/LAN,
# block gerisi — permit-above-block). Disable = helper'ı öldür (filtreler kendiliğinden uçar).
$KillSwitchExe = Join-Path (Join-Path $env:ProgramFiles "AsenaPlug") "asena-killswitch.exe"

function Enable-KillSwitch([int]$tunIndex, [string[]]$cfRanges, [string]$usqueExe) {
    # !!! DEVRE DIŞI: WFP permit-tun kuralı tünel trafiğini eşleştirmiyor -> yeni
    # bağlantıları (DNS/youtube/oyun) blokluyor. asena-on artık bunu ÇAĞIRMIYOR;
    # kod, Windows'ta düzeltilip test edilene dek ileri kullanım için duruyor.
    Stop-Process -Name "asena-killswitch" -Force -ErrorAction SilentlyContinue   # varsa eskiyi durdur
    if (-not (Test-Path $KillSwitchExe)) {
        Write-Log "kill-switch atlandı: helper yok ($KillSwitchExe). Go ile build alınmamış olabilir."
        return
    }
    if ($tunIndex -le 0) { Write-Log "kill-switch atlandı: TUN index alınamadı."; return }
    $allow = ($cfRanges -join ",")
    Start-Process -FilePath $KillSwitchExe -ArgumentList @(
        "-tun-index", "$tunIndex", "-usque", "`"$usqueExe`"", "-allow", "`"$allow`""
    ) -NoNewWindow -ErrorAction SilentlyContinue
}

function Disable-KillSwitch {
    # Helper ölünce dinamik WFP filtreleri OTOMATİK kalkar (ayrıca güvenlik için öldür).
    Stop-Process -Name "asena-killswitch" -Force -ErrorAction SilentlyContinue
}
