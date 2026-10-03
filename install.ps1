# AsenaPlug - one-line installer
#   irm https://raw.githubusercontent.com/KaanAlper/AsenaPlug/main/install.ps1 | iex
# Downloads the latest release's AsenaPlug.exe with a progress bar, checks its SHA-256 and lets it install
# itself into Program Files\AsenaPlug (Windows asks for administrator permission once: the tunnel needs
# scheduled tasks, Wintun and network settings), then adds a Start menu shortcut and an entry in
# Settings > Apps with an uninstaller. A running AsenaPlug is disconnected cleanly before an update.
# Running the same command again updates it. On an error or Ctrl+C everything goes back to how it was.
# No telemetry: the only requests go to api.github.com and the release download. Log: %TEMP%\AsenaPlug-install.log
# Options (set before running):  $env:ASENAPLUG_UNINSTALL = 1    remove AsenaPlug (add $env:ASENAPLUG_PURGE = 1 to delete the Asena identity too)
#                                 $env:ASENAPLUG_VERSION = 'x.y.z' install that release instead of the latest
#                                 $env:ASENAPLUG_SOURCE = <file>   install from a local AsenaPlug.exe (a CI build)
#                                 $env:ASENAPLUG_LANGUAGE = 'tr' or 'en'
#                                 $env:ASENAPLUG_DEFAULTS = 1      no questions (default answers)
#                                 $env:ASENAPLUG_FORCE = 1         reinstall even when this version is already installed
& {
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# ---------------------------------------------------------------- what is installed
$App = [ordered]@{
    Name          = 'AsenaPlug'
    Id            = 'AsenaPlug'
    Repo          = 'KaanAlper/AsenaPlug'
    Branch        = 'main'
    Publisher     = 'Kaan Alper'
    Env           = 'ASENAPLUG'
    Accent        = '#7fd4c9'
    TaglineEn     = 'WARP / MASQUE tunnel in the tray for selective DPI and DNS-censorship bypass'
    TaglineTr     = 'Seçici DPI ve DNS sansürü aşımı için tepside WARP / MASQUE tüneli'
    Mode          = 'setup'
    Asset         = '^AsenaPlug\.exe$'
    Exe           = 'AsenaPlug.exe'
    Shortcut      = $true
    Path          = $false
    Command       = ''
    Autostart     = 'no'
    AutostartArgs = ''
    Data          = @()
    Legacy        = @()
    Launch        = $false
    KeyName       = 'AsenaPlug'
    SetupArgs     = ''
    UninstallArgs = ''
    Admin         = $true
    DefaultDir    = "$env:ProgramFiles\AsenaPlug"
}
function Opt([string]$name) { [Environment]::GetEnvironmentVariable("$($App.Env)_$name") }
$Dir = Join-Path $env:LOCALAPPDATA ('Programs\' + $App.Id)
$UninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\' + $App.Id
$StartMenu = Join-Path ([Environment]::GetFolderPath('Programs')) ($App.Name + '.lnk')
$RunKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$LogFile = Join-Path $env:TEMP ($App.Id + '-install.log')
$ESC = [char]27

# ---------------------------------------------------------------- texts (Turkish / English)
function Get-Texts([bool]$tr) {
if ($tr) { @{
    tagline = $App.TaglineTr
    qLang = 'Kurulum dili / Installer language'
    looking = 'Son sürüm aranıyor'; noRelease = 'Bu bilgisayar için indirilebilir bir sürüm henüz yayımlanmamış.'
    welcomeNew = '{0} kurulacak'; welcomeUpd = '{0} güncellenecek'
    body = "Sürüm: {0}`nİndirme: {1}`nKonum: {2}"
    bodyUser = 'Yönetici izni gerekmez. Bir şey ters giderse ya da vazgeçersen her şey eski haline döner.'
    bodyAdmin = 'Kurulum programı Windows''tan bir kez yönetici izni isteyecek. Yarıda kalan bir kurulumu kendisi geri alır.'
    current = 'Kurulu sürüm: {0}'
    qGo = 'Devam edelim mi?'; go = 'Kur'; goUpd = 'Güncelle'; cancel = 'Vazgeç'
    upToDate = '{0} {1} zaten kurulu ve güncel.'; qReinstall = 'Yine de yeniden kurulsun mu?'; reinstall = 'Yeniden kur'; keep = 'Böyle kalsın'
    downloading = 'İndiriliyor'; verifying = 'Paket doğrulanıyor'; extracting = 'Paket açılıyor'; closing = 'Açık {0} kapatılıyor'
    placing = 'Dosyalar yerleştiriliyor'; registering = 'Başlat menüsü ve Uygulamalar kaydı'
    running = 'Kurulum programı çalışıyor'; uac = "Windows'un izin penceresini onayla"
    qAutostart = 'Windows açılınca {0} kendiliğinden başlasın mı?'; yes = 'Evet'; no = 'Hayır'
    qStart = '{0} şimdi açılsın mı?'
    doneNew = 'Hazır! {0} {1} kuruldu'; doneUpd = 'Hazır! {0} {1} sürümüne güncellendi'
    doneBody = "Başlat menüsünde: {0}`nGüncellemek için aynı komutu yeniden çalıştır.`nKaldırmak için: Ayarlar > Uygulamalar > {0}"
    doneCli = "Yeni bir terminal aç ve '{1}' yaz.`nGüncellemek için aynı komutu yeniden çalıştır.`nKaldırmak için: Ayarlar > Uygulamalar > {0}"
    other = "Bu bilgisayarda {0} başka bir yolla da kurulmuş ({1}). İki kopya karışmasın diye onu Ayarlar > Uygulamalar'dan kaldırabilirsin."
    errTitle = 'Olmadı, ama merak etme'
    errBody = "Kurulum '{0}' adımında takıldı. Bilgisayarında hiçbir şey yarım kalmadı: yapılan değişiklikler geri alındı."
    errDetail = 'Ayrıntı'; errLog = 'Günlük'
    errRetry = "Aynı komutu yeniden çalıştırarak tekrar deneyebilirsin. Sorun sürerse günlüğü paylaş:`nhttps://github.com/$($App.Repo)/issues"
    netTitle = 'GitHub''a ulaşamadık'; netBody = 'Bağlantını kontrol edip aynı komutu yeniden çalıştır. Bilgisayarında hiçbir şey değişmedi.'
    cancelTitle = 'Kurulumdan vazgeçildi'; cancelBody = 'Her şey eski haline döndü, bilgisayarında hiçbir şey değişmedi.'
    uacTitle = 'İzin verilmedi'; uacBody = 'Yönetici izni olmadan kurulum yapılamıyor. Hiçbir şey değişmedi; hazır olduğunda aynı komutu yeniden çalıştır.'
    badPkg = 'İndirilen paket bozuk görünüyor (SHA-256 tutmadı).'; noExe = 'Pakette {0} bulunamadı.'; setupCode = 'Kurulum programı {0} koduyla bitti.'
    retrying = 'bağlantı koptu, {0} sn sonra kaldığı yerden devam ({1}/5)'
    plainPick = 'Numara yaz ve Enter''a bas'
    unTitle = '{0} kaldırılsın mı?'; unGo = 'Kaldır'; notInstalled = '{0} bu bilgisayarda kurulu değil.'; removed = '{0} kaldırıldı.'
} } else { @{
    tagline = $App.TaglineEn
    qLang = 'Installer language / Kurulum dili'
    looking = 'Looking for the latest release'; noRelease = 'No downloadable release for this computer has been published yet.'
    welcomeNew = 'Installing {0}'; welcomeUpd = 'Updating {0}'
    body = "Version: {0}`nDownload: {1}`nLocation: {2}"
    bodyUser = 'No administrator permission needed. If something goes wrong or you cancel, everything goes back to how it was.'
    bodyAdmin = 'The setup program asks Windows for administrator permission once. It undoes an install that does not finish by itself.'
    current = 'Installed version: {0}'
    qGo = 'Go ahead?'; go = 'Install'; goUpd = 'Update'; cancel = 'Cancel'
    upToDate = '{0} {1} is already installed and up to date.'; qReinstall = 'Reinstall it anyway?'; reinstall = 'Reinstall'; keep = 'Leave it'
    downloading = 'Downloading'; verifying = 'Verifying the package'; extracting = 'Unpacking'; closing = 'Closing the running {0}'
    placing = 'Putting the files in place'; registering = 'Start menu and Apps entry'
    running = 'Running the setup program'; uac = "Approve Windows' permission prompt"
    qAutostart = 'Start {0} automatically when Windows starts?'; yes = 'Yes'; no = 'No'
    qStart = 'Open {0} now?'
    doneNew = 'All set! {0} {1} is installed'; doneUpd = 'All set! {0} is updated to {1}'
    doneBody = "In the Start menu: {0}`nTo update, run the same command again.`nTo remove it: Settings > Apps > {0}"
    doneCli = "Open a new terminal and type '{1}'.`nTo update, run the same command again.`nTo remove it: Settings > Apps > {0}"
    other = '{0} is also installed another way on this computer ({1}). To keep the two copies apart you can remove that one in Settings > Apps.'
    errTitle = "That didn't work, but don't worry"
    errBody = "The install got stuck at '{0}'. Nothing was left half-done: the changes were undone."
    errDetail = 'Details'; errLog = 'Log'
    errRetry = "You can try again by running the same command. If it keeps happening, please share the log:`nhttps://github.com/$($App.Repo)/issues"
    netTitle = "We couldn't reach GitHub"; netBody = 'Check your connection and run the same command again. Nothing on your computer was changed.'
    cancelTitle = 'Install cancelled'; cancelBody = 'Everything is back to how it was; nothing on your computer was changed.'
    uacTitle = 'Permission was not given'; uacBody = 'The install needs administrator permission. Nothing was changed; run the same command again when you are ready.'
    badPkg = 'The downloaded package looks damaged (the SHA-256 does not match).'; noExe = '{0} is missing from the package.'; setupCode = 'The setup program ended with code {0}.'
    retrying = 'connection dropped, resuming in {0} s ({1}/5)'
    plainPick = 'Type a number and press Enter'
    unTitle = 'Remove {0}?'; unGo = 'Remove'; notInstalled = '{0} is not installed on this computer.'; removed = '{0} was removed.'
} }
}
$tr = (Get-UICulture).Name -like 'tr*'
if ((Opt 'LANGUAGE') -in 'tr', 'en') { $tr = (Opt 'LANGUAGE') -eq 'tr' }
$T = Get-Texts $tr

# ---------------------------------------------------------------- drawing
$COL = @{ accent = $App.Accent; text = '#e6e0e9'; dim = '#938f99'; ok = '#a8dab5'; err = '#f2b8b5'; warn = '#ffb77c' }
function Fg([string]$hex) { $h = $hex.TrimStart('#'); "$ESC[38;2;$([Convert]::ToInt32($h.Substring(0, 2), 16));$([Convert]::ToInt32($h.Substring(2, 2), 16));$([Convert]::ToInt32($h.Substring(4, 2), 16))m" }
$RESET = "$ESC[0m"
# The classic console draws only what its font has (WGL4); modern terminals fill in the rest
$GL = if ($env:WT_SESSION -or $env:TERM_PROGRAM) {
    @{ ok = '✓'; fail = '✗'; cursor = '❯'; wait = '◌'; fill = '━'; tl = '╭'; tr = '╮'; bl = '╰'; br = '╯'; spin = '⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏' }
} else {
    @{ ok = '√'; fail = 'x'; cursor = '►'; wait = '○'; fill = '─'; tl = '┌'; tr = '┐'; bl = '└'; br = '┘'; spin = '|', '/', '-', '\' }
}
function Paint([string]$hex, [string]$s) { (Fg $hex) + $s + $RESET }
function Width { try { [Math]::Max(40, [Math]::Min(76, [Console]::WindowWidth - 4)) } catch { 72 } }
function Wrap([string]$text, [int]$w) {
    $out = New-Object Collections.Generic.List[string]
    foreach ($para in (($text -replace "`r", '').TrimEnd() -split "`n")) {
        if ($para.Length -le $w) { $out.Add($para); continue }
        $line = ''
        $words = foreach ($wd in ($para -split ' ')) { for ($k = 0; $k -lt [Math]::Max(1, $wd.Length); $k += $w) { $wd.Substring($k, [Math]::Min($w, [Math]::Max(0, $wd.Length - $k))) } }
        foreach ($word in $words) {
            if ($line.Length -eq 0) { $line = $word }
            elseif (($line.Length + 1 + $word.Length) -le $w) { $line += ' ' + $word }
            else { $out.Add($line); $line = $word }
        }
        $out.Add($line)
    }
    return $out
}
function Box([string]$color, [string]$title, [string]$body) {
    if ($Driver) {
        $kind = if ($color -eq $COL.ok) { 'ok' } elseif ($color -eq $COL.err) { 'error' } elseif ($color -eq $COL.warn) { 'warn' } else { 'info' }
        if (-not $title) { Report @{ notes = @($DriverStatus.notes | Where-Object { $_ }) + $body } }
        elseif ($kind -ne 'info') { Report @{ result = $kind; title = $title; body = $body } }
    }
    $w = Width; $in = $w - 4; $b = Fg $color
    Write-Host ''
    Write-Host ("  $b$($GL.tl)" + ('─' * ($w - 2)) + "$($GL.tr)$RESET")
    if ($title) {
        Write-Host ("  $b│$RESET " + "$ESC[1m" + (Fg $color) + $title.PadRight($in) + "$RESET $b│$RESET")
        Write-Host ("  $b│$RESET " + (' ' * $in) + " $b│$RESET")
    }
    foreach ($l in (Wrap $body $in)) { Write-Host ("  $b│$RESET " + (Fg $COL.text) + $l.PadRight($in) + "$RESET $b│$RESET") }
    Write-Host ("  $b$($GL.bl)" + ('─' * ($w - 2)) + "$($GL.br)$RESET")
}
function Banner {
    Write-Host ''
    Write-Host ('  ' + "$ESC[1m" + (Paint $COL.accent $App.Name))
    Write-Host ('  ' + (Paint $COL.dim $T.tagline))
}
function Say([string]$sym, [string]$color, [string]$text) { Report @{ say = $text }; Write-Host ('  ' + (Paint $color $sym) + ' ' + (Paint $COL.text $text)) }
function Human([double]$b) { if ($b -ge 1MB) { '{0:0.0} MB' -f ($b / 1MB) } else { '{0:0} KB' -f ($b / 1KB) } }
function Bar([double]$frac, [int]$width, [int]$tick) {
    $fill = [int][Math]::Floor($frac * $width); $s = ''
    for ($i = 0; $i -lt $width; $i++) {
        if ($i -lt $fill) { $s += $(if ((($i - $tick) % 24 + 24) % 24 -lt 3) { (Fg '#f0eaff') } else { (Fg $COL.accent) }) + $GL.fill }
        elseif ($i -eq $fill) { $s += (Fg $COL.accent) + '╸' }
        else { $s += (Fg '#49454f') + '─' }
    }
    return $s + $RESET
}
function Log([string]$m) { try { Add-Content -LiteralPath $LogFile -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss ') + $m) -Encoding UTF8 } catch {} }
# ---------------------------------------------------------------- the windowed setup app (installer\gui)
# It sets <ENV>_DRIVER to a folder of its own, shows status.json from there and drops a "cancel" file in it to stop
# (the finally block below undoes everything, the same as Ctrl+C). Without it these do nothing.
$Driver = Opt 'DRIVER'
$DriverStatus = @{ steps = @() }
function Report([hashtable]$fields) {
    if (-not $Driver) { return }
    foreach ($k in @($fields.Keys)) { $DriverStatus[$k] = $fields[$k] }
    try { [IO.File]::WriteAllText((Join-Path $Driver 'status.json'), (ConvertTo-Json $DriverStatus -Compress -Depth 4), (New-Object Text.UTF8Encoding $false)) } catch {}
}
function Report-Stage([string]$label) { if ($Driver) { Report @{ steps = @($DriverStatus.steps) + $label; state = 'running'; percent = -1 } } }
function Test-Cancel { if ($Driver -and (Test-Path -LiteralPath (Join-Path $Driver 'cancel'))) { throw (New-Object OperationCanceledException) } }

# ---------------------------------------------------------------- input
$interactive = (-not (Opt 'DEFAULTS')) -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected
# Arrow keys + Enter (numbers in a plain console); returns the value of the picked item
function Choose([string]$header, [object[]]$items, [string]$default) {
    if (-not $interactive) { return $default }
    $sel = [Math]::Max(0, [Array]::IndexOf(@($items | ForEach-Object { $_[1] }), $default))
    $raw = $true
    try { [void][Console]::KeyAvailable; [Console]::CursorVisible = $false } catch { $raw = $false }
    if (-not $raw) {
        Write-Host "  $header"
        for ($i = 0; $i -lt $items.Count; $i++) { Write-Host "  $($i + 1). $($items[$i][0])" }
        while ($true) {
            $a = (Read-Host "  $($T.plainPick) [$($sel + 1)]").Trim()
            if (-not $a) { return $items[$sel][1] }
            $n = 0
            if ([int]::TryParse($a, [ref]$n) -and $n -ge 1 -and $n -le $items.Count) { return $items[$n - 1][1] }
        }
    }
    Write-Host ''
    Write-Host ('  ' + (Paint $COL.accent '?') + ' ' + "$ESC[1m" + (Paint $COL.text $header))
    $first = $true
    try {
        while ($true) {
            if (-not $first) { Write-Host -NoNewline "$ESC[$($items.Count)A" }
            $first = $false
            for ($i = 0; $i -lt $items.Count; $i++) {
                $line = if ($i -eq $sel) { '  ' + (Paint $COL.accent ($GL.cursor + ' ' + $items[$i][0])) } else { '    ' + (Paint $COL.dim $items[$i][0]) }
                Write-Host ("`r" + $line + "$ESC[K")
            }
            $k = [Console]::ReadKey($true)
            switch ($k.Key) {
                'UpArrow' { $sel = ($sel - 1 + $items.Count) % $items.Count }
                'DownArrow' { $sel = ($sel + 1) % $items.Count }
                'Enter' { return $items[$sel][1] }
                'Escape' { throw (New-Object OperationCanceledException) }
                default {
                    $n = 0
                    if ([int]::TryParse([string]$k.KeyChar, [ref]$n) -and $n -ge 1 -and $n -le $items.Count) { $sel = $n - 1 }
                }
            }
        }
    }
    finally { try { [Console]::CursorVisible = $true } catch {} }
}
function Confirm([string]$q, [string]$yes, [string]$no, [bool]$default = $true) {
    (Choose $q @(@($yes, 'y'), @($no, 'n')) $(if ($default) { 'y' } else { 'n' })) -eq 'y'
}

# ---------------------------------------------------------------- download with a progress bar
function Get-WithBar([string]$url, [string]$dst, [string]$label, [long]$sizeHint) {
    # a dropped connection continues where it stopped (HTTP Range) instead of starting over
    $tick = 0; $last = ''
    Report-Stage $label
    for ($try = 1; $try -le 5; $try++) {
        try {
            $have = if (Test-Path -LiteralPath $dst) { (Get-Item -LiteralPath $dst).Length } else { 0 }
            $req = [Net.HttpWebRequest]::Create($url)
            $req.UserAgent = "$($App.Id)-install"; $req.Timeout = 30000; $req.ReadWriteTimeout = 60000
            if ($have -gt 0) { $req.AddRange([long]$have) }
            $res = $req.GetResponse()
            try {
                if ([int]$res.StatusCode -ne 206) { $have = 0 }
                $total = if ($res.ContentLength -gt 0) { $have + $res.ContentLength } else { $sizeHint }
                $in = $res.GetResponseStream()
                $out = if ($have -gt 0) { New-Object IO.FileStream($dst, [IO.FileMode]::Append) } else { [IO.File]::Create($dst) }
                try {
                    $buf = New-Object byte[] 131072; $done = $have
                    $sw = [Diagnostics.Stopwatch]::StartNew(); $draw = [Diagnostics.Stopwatch]::StartNew()
                    while (($n = $in.Read($buf, 0, $buf.Length)) -gt 0) {
                        $out.Write($buf, 0, $n); $done += $n
                        if ($draw.ElapsedMilliseconds -ge 60) {
                            $draw.Restart(); $tick++
                            $frac = if ($total -gt 0) { [Math]::Min(1.0, [double]$done / $total) } else { 0 }
                            Report @{ percent = $(if ($total -gt 0) { [int]($frac * 100) } else { -1 }); done = $done; total = $total }; Test-Cancel
                            $speed = if ($sw.Elapsed.TotalSeconds -gt 0.3) { (Human (($done - $have) / $sw.Elapsed.TotalSeconds)) + '/s' } else { '' }
                            $pct = if ($total -gt 0) { '{0,3:0}%' -f ($frac * 100) } else { '' }
                            $info = (Human $done) + $(if ($total -gt 0) { ' / ' + (Human $total) }) + '  ' + $speed
                            $bw = 16
                            try { $bw = [Math]::Max(5, [Math]::Min(40, [Console]::WindowWidth - 14 - $label.Length - $pct.Length - $info.Length)) } catch {}
                            Write-Host -NoNewline ("`r  " + (Paint $COL.accent $GL.spin[$tick % $GL.spin.Count]) + ' ' + $label + '  ' + (Bar $frac $bw $tick) + ' ' + (Paint $COL.text $pct) + '  ' + (Paint $COL.dim $info) + "$ESC[K")
                        }
                    }
                }
                finally { $out.Dispose(); $in.Dispose() }
            }
            finally { $res.Dispose() }
            if ($total -gt 0 -and $done -lt $total) { throw "the connection closed at $(Human $done) of $(Human $total)" }
            Report @{ state = 'done'; percent = 100 }
            Write-Host ("`r  " + (Paint $COL.ok $GL.ok) + ' ' + $label + '  ' + (Paint $COL.dim (Human (Get-Item -LiteralPath $dst).Length)) + "$ESC[K")
            return
        }
        catch [OperationCanceledException] { throw }
        catch {
            $last = $_.Exception.Message
            Log "download try ${try}: $last"
            for ($ex = $_.Exception; $ex; $ex = $ex.InnerException) {
                # 416: what is on disk does not fit the file on the server; start over
                if ($ex -is [Net.WebException] -and $ex.Response -and [int]$ex.Response.StatusCode -eq 416) { Remove-Item -LiteralPath $dst -Force -ErrorAction SilentlyContinue }
                # 404 / 403: the file is not there; asking again does not help
                if ($ex -is [Net.WebException] -and $ex.Response -and [int]$ex.Response.StatusCode -in 403, 404, 410) { $try = 5 }
            }
            if ($try -eq 5) { break }
            for ($w = 2 * $try; $w -gt 0; $w--) {
                Write-Host -NoNewline ("`r  " + (Paint $COL.warn '↻') + ' ' + $label + '  ' + (Paint $COL.dim ($T.retrying -f $w, ($try + 1))) + "$ESC[K")
                Start-Sleep -Seconds 1
            }
        }
    }
    Report @{ state = 'error' }
    throw $last
}
# "◌ label" while it runs, then ✓ / ✗ in place
function Step([string]$label, [scriptblock]$sb) {
    $state.stage = $label
    Log "step: $label"
    Test-Cancel; Report-Stage $label
    Write-Host -NoNewline ('  ' + (Paint $COL.accent $GL.wait) + ' ' + $label)
    try { $result = & $sb; Report @{ state = 'done' }; Write-Host ("`r  " + (Paint $COL.ok $GL.ok) + ' ' + $label + "$ESC[K"); return $result }
    catch { Report @{ state = 'error' }; Write-Host ("`r  " + (Paint $COL.err $GL.fail) + ' ' + $label + "$ESC[K"); throw }
}

# ---------------------------------------------------------------- the uninstaller (copied into Program Files\AsenaPlug; Settings > Apps runs it)
$UninstallTemplate = @'
# Removes AsenaPlug from this computer (written by install.ps1; Settings > Apps runs it).
# Tears the tunnel down first (DNS, routes, firewall, kill-switch) with AsenaPlug's own
# scripts\asena-uninstall.ps1, then removes the Apps entry and the Start menu shortcut.
# The Asena identity (%ProgramData%\AsenaPlug\config\config.json) is kept unless -Purge.
#   -Quiet  no questions    -Purge  also delete %ProgramData%\AsenaPlug (identity included)
param([switch]$Quiet, [switch]$Purge)
$ErrorActionPreference = 'Stop'
$tr = (Get-UICulture).Name -like 'tr*'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    # Program Files, scheduled tasks and the network settings need administrator rights
    $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"")
    if ($Quiet) { $a += '-Quiet' }
    if ($Purge) { $a += '-Purge' }
    try { $p = Start-Process powershell.exe -Verb RunAs -ArgumentList $a -PassThru }
    catch { Write-Host $(if ($tr) { 'Yönetici izni verilmedi; hiçbir şey değişmedi.' } else { 'Administrator permission was not given; nothing was changed.' }); exit 1223 }
    $p.WaitForExit()
    exit $p.ExitCode
}
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}
$PF = Join-Path $env:ProgramFiles 'AsenaPlug'
$Data = Join-Path $env:ProgramData 'AsenaPlug'
$ask = (-not $Quiet) -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected
if ($ask) {
    $q = if ($tr) { 'AsenaPlug kaldırılsın mı? [E/h]' } else { 'Remove AsenaPlug? [Y/n]' }
    if ((Read-Host $q).Trim() -match '^(h|n|hayir|hayır|no)$') { exit 0 }
}
Set-Location -LiteralPath $env:TEMP
$un = Join-Path $PF 'scripts\asena-uninstall.ps1'
if (Test-Path -LiteralPath $un) { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $un | Out-Null }
Get-Process -Name 'AsenaPlug', 'usque', 'dnsproxy' -ErrorAction SilentlyContinue | ForEach-Object { try { $_.Kill(); [void]$_.WaitForExit(5000) } catch {} }
'AsenaPlug_Tray', 'AsenaPlug_RouteSync', 'AsenaPlug_Rescue' | ForEach-Object { Unregister-ScheduledTask -TaskName $_ -Confirm:$false -ErrorAction SilentlyContinue }
Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('CommonPrograms')) 'AsenaPlug.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AsenaPlug' -Recurse -Force -ErrorAction SilentlyContinue
# without this flag a later install sets everything up again (tasks, binaries) instead of only refreshing the exe
Remove-Item -LiteralPath (Join-Path $Data 'installed.flag') -Force -ErrorAction SilentlyContinue
if (-not $Purge -and $ask -and (Test-Path -LiteralPath $Data)) {
    $q = if ($tr) { "Asena kimliği ve ayarlar da silinsin mi? ($Data) [e/H]" } else { "Delete the Asena identity and settings too? ($Data) [y/N]" }
    $Purge = (Read-Host $q).Trim() -match '^(e|y|evet|yes)$'
}
if ($Purge) { Remove-Item -LiteralPath $Data -Recurse -Force -ErrorAction SilentlyContinue }
try { if (Test-Path -LiteralPath $PF) { Remove-Item -LiteralPath $PF -Recurse -Force } }
catch { Start-Process cmd.exe -ArgumentList "/c timeout /t 3 /nobreak >nul & rd /s /q `"$PF`"" -WindowStyle Hidden }
if ($ask) { Write-Host $(if ($tr) { 'AsenaPlug kaldırıldı.' } else { 'AsenaPlug was removed.' }) }
exit 0
'@
# ---------------------------------------------------------------- release lookup
function Get-Release {
    $want = Opt 'VERSION'
    $hdr = @{ 'User-Agent' = "$($App.Id)-install"; Accept = 'application/vnd.github+json' }
    $list = Invoke-RestMethod -Uri "https://api.github.com/repos/$($App.Repo)/releases?per_page=40" -Headers $hdr -TimeoutSec 30
    foreach ($rel in @($list)) {
        if ($rel.draft) { continue }
        if ($want) { if ($rel.tag_name -ne "v$want") { continue } }
        elseif ($rel.prerelease) { continue }
        $file = @($rel.assets | Where-Object { $_.name -match $App.Asset }) | Select-Object -First 1
        if (-not $file) { continue }
        $sha = @($rel.assets | Where-Object { $_.name -eq ($file.name + '.sha256') }) | Select-Object -First 1
        return [pscustomobject]@{ Version = ($rel.tag_name -replace '^v', ''); Url = $file.browser_download_url; Name = $file.name; Size = [long]$file.size; Sha = $(if ($sha) { $sha.browser_download_url }) }
    }
    return $null
}
# zip mode: our own Apps entry; setup mode: the entry the setup program writes (machine or user)
function Get-SetupEntry {
    $roots = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall', 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall'
    foreach ($root in $roots) {
        $p = Get-ItemProperty -LiteralPath (Join-Path $root $App.KeyName) -ErrorAction SilentlyContinue
        if ($p) { return $p }
    }
    return $null
}
function Get-Running([string]$where) {
    if (-not $where) { return @() }
    @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($where.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) })
}
function Stop-Running([string]$where) {
    foreach ($p in Get-Running $where) { try { [void]$p.CloseMainWindow() } catch {} }
    Start-Sleep -Milliseconds 1500
    foreach ($p in Get-Running $where) { try { $p.Kill(); [void]$p.WaitForExit(5000) } catch {} }
}
# the same program installed another way (a setup exe, a portable copy registered elsewhere)
function Find-OtherInstall {
    $mine = if ($App.Mode -eq 'setup') { $App.KeyName } else { $App.Id }
    $roots = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall', 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall'
    foreach ($root in $roots) {
        Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue | ForEach-Object {
            $p = Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction SilentlyContinue
            if ($p -and $_.PSChildName -ne $mine -and $p.DisplayName -and ($p.DisplayName -eq $App.Name -or $p.DisplayName -like "$($App.Name) *")) {
                $(if ($p.InstallLocation) { $p.InstallLocation } else { $p.DisplayName })
            }
        }
    }
}

# ---------------------------------------------------------------- uninstall
function Invoke-Uninstall {
    $d = Get-InstallDir
    if (-not $d) { Say $GL.ok $COL.ok ($T.notInstalled -f $App.Name); return }
    if ($interactive -and -not (Confirm ($T.unTitle -f $App.Name) $T.unGo $T.cancel $true)) { return }
    New-Item -ItemType Directory -Force $work | Out-Null
    $script = Join-Path $work 'uninstall.ps1'
    [IO.File]::WriteAllText($script, $UninstallTemplate, (New-Object Text.UTF8Encoding $true))
    $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$script`"", '-Quiet')
    if (Opt 'PURGE') { $a += '-Purge' }
    $code = Step ($T.unGo + ' ' + $App.Name) {
        try { $p = Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList $a -PassThru }
        catch { for ($ex = $_.Exception; $ex; $ex = $ex.InnerException) { if ($ex -is [ComponentModel.Win32Exception] -and $ex.NativeErrorCode -eq 1223) { return 1223 } }; throw }
        $p.WaitForExit(); $p.ExitCode
    }
    if ($code -eq 1223) { Box $COL.warn $T.uacTitle $T.uacBody; return }
    if ($code -ne 0) { throw ($T.setupCode -f $code) }
    Log 'uninstalled'
    Say $GL.ok $COL.ok ($T.removed -f $App.Name)
}

# ---------------------------------------------------------------- the elevated part (one UAC prompt)
# AsenaPlug.exe installs itself: on its first start it copies the tunnel binaries and scripts to
# Program Files\AsenaPlug, registers its scheduled tasks and starts the tray; a newer exe started
# later refreshes the installed copy. This part stops a running copy cleanly (tunnel down first),
# lets the downloaded exe do that, checks the result, then adds the Apps entry and a Start menu
# shortcut. A failure puts the previous exe back (update) or removes the half-done install.
$ElevatedScript = @'
param([string]$Exe, [string]$Version, [string]$Uninstaller, [string]$Result)
$ErrorActionPreference = 'Stop'
$PF = Join-Path $env:ProgramFiles 'AsenaPlug'
$AppExe = Join-Path $PF 'AsenaPlug.exe'
$Key = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AsenaPlug'
$Lnk = Join-Path ([Environment]::GetFolderPath('CommonPrograms')) 'AsenaPlug.lnk'
$Flag = Join-Path $env:ProgramData 'AsenaPlug\installed.flag'
function Done([bool]$ok, [string]$msg) { [IO.File]::WriteAllText($Result, (@{ ok = $ok; message = $msg } | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding $false)) }
$fresh = -not (Test-Path -LiteralPath $Flag)
$backup = $null; $hadKey = Test-Path -LiteralPath $Key; $hadLnk = Test-Path -LiteralPath $Lnk
try {
    if (-not $fresh) {
        # the same teardown the tray does when it quits, so DNS and routes are not left pointing at a dead tunnel
        $off = Join-Path $PF 'scripts\asena-off.ps1'
        if (Test-Path -LiteralPath $off) { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $off | Out-Null }
        Get-Process -Name 'AsenaPlug', 'usque', 'dnsproxy' -ErrorAction SilentlyContinue | ForEach-Object { try { $_.Kill(); [void]$_.WaitForExit(10000) } catch {} }
        if (Test-Path -LiteralPath $AppExe) { $backup = "$AppExe.previous"; Copy-Item -LiteralPath $AppExe $backup -Force }
    }
    # the downloaded exe sets up or refreshes the install, starts the installed tray and exits
    $p = Start-Process -FilePath $Exe -WorkingDirectory (Split-Path $Exe) -PassThru
    if (-not $p.WaitForExit(900000)) { throw 'AsenaPlug.exe did not finish within 15 minutes' }
    if ($p.ExitCode -ne 0) { throw "AsenaPlug.exe ended with code $($p.ExitCode)" }
    if (-not (Test-Path -LiteralPath $AppExe)) { throw "AsenaPlug.exe was not placed in $PF" }
    if ((Get-FileHash -LiteralPath $AppExe).Hash -ne (Get-FileHash -LiteralPath $Exe).Hash) { throw "$AppExe is still the previous version" }

    Copy-Item -LiteralPath $Uninstaller (Join-Path $PF 'uninstall.ps1') -Force
    New-Item -Path $Key -Force | Out-Null
    $un = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $PF 'uninstall.ps1')`""
    $size = [int]((Get-ChildItem -LiteralPath $PF -Recurse -File | Measure-Object Length -Sum).Sum / 1KB)
    $vals = [ordered]@{ DisplayName = 'AsenaPlug'; DisplayVersion = $Version; Publisher = 'Kaan Alper'; DisplayIcon = "$AppExe,0"; InstallLocation = $PF
        InstallDate = (Get-Date -Format 'yyyyMMdd'); URLInfoAbout = 'https://github.com/KaanAlper/AsenaPlug'; UninstallString = $un; QuietUninstallString = "$un -Quiet" }
    foreach ($k in $vals.Keys) { Set-ItemProperty -LiteralPath $Key -Name $k -Value $vals[$k] }
    foreach ($k in 'NoModify', 'NoRepair') { New-ItemProperty -LiteralPath $Key -Name $k -Value 1 -PropertyType DWord -Force | Out-Null }
    New-ItemProperty -LiteralPath $Key -Name 'EstimatedSize' -Value $size -PropertyType DWord -Force | Out-Null
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($Lnk)
    $s.TargetPath = $AppExe; $s.WorkingDirectory = $PF; $s.IconLocation = "$AppExe,0"; $s.Description = 'AsenaPlug'
    $s.Save()
    if ($backup) { Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue }
    Done $true ''
}
catch {
    $msg = $_.Exception.Message
    try {
        if ($backup -and (Test-Path -LiteralPath $backup)) {
            Get-Process -Name 'AsenaPlug' -ErrorAction SilentlyContinue | ForEach-Object { try { $_.Kill(); [void]$_.WaitForExit(10000) } catch {} }
            Move-Item -LiteralPath $backup $AppExe -Force
            Start-ScheduledTask -TaskName 'AsenaPlug_Tray' -ErrorAction SilentlyContinue
        }
        elseif ($fresh) {
            $un = Join-Path $PF 'scripts\asena-uninstall.ps1'
            if (Test-Path -LiteralPath $un) { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $un | Out-Null }
            Remove-Item -LiteralPath $Flag -Force -ErrorAction SilentlyContinue
            if (Test-Path -LiteralPath $PF) { Remove-Item -LiteralPath $PF -Recurse -Force -ErrorAction SilentlyContinue }
        }
        if (-not $hadKey) { Remove-Item -LiteralPath $Key -Recurse -Force -ErrorAction SilentlyContinue }
        if (-not $hadLnk) { Remove-Item -LiteralPath $Lnk -Force -ErrorAction SilentlyContinue }
    } catch { $msg += " (undo: $($_.Exception.Message))" }
    Done $false $msg
}
'@
function Invoke-Elevated([string[]]$arguments) {
    $script = Join-Path $work 'elevated.ps1'
    [IO.File]::WriteAllText($script, $ElevatedScript, (New-Object Text.UTF8Encoding $true))
    $result = Join-Path $work 'result.json'
    $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$script`"") + $arguments + @('-Result', "`"$result`"")
    Log "elevated: $($a -join ' ')"
    # not -Wait: it would also wait for the tray the exe leaves running
    try { $p = Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList $a -PassThru }
    catch {
        # Windows PowerShell wraps the declined prompt (Win32 error 1223) in an InvalidOperationException
        for ($ex = $_.Exception; $ex; $ex = $ex.InnerException) { if ($ex -is [ComponentModel.Win32Exception] -and $ex.NativeErrorCode -eq 1223) { return $null } }
        throw
    }
    $p.WaitForExit()
    if (-not (Test-Path -LiteralPath $result)) { throw "the elevated step ended with code $($p.ExitCode) without a result" }
    return (Get-Content -LiteralPath $result -Raw | ConvertFrom-Json)
}

# the installed version: the exe's own (its updater replaces it without touching the Apps entry)
function Get-InstallDir {
    $e = Get-SetupEntry
    if ($e -and $e.InstallLocation) { return $e.InstallLocation.TrimEnd('\') }
    $pf = Join-Path $env:ProgramFiles 'AsenaPlug'
    if (Test-Path -LiteralPath (Join-Path $pf $App.Exe)) { return $pf }
    return $null
}
function Get-Installed {
    $d = Get-InstallDir
    if ($d) {
        $v = (Get-Item -LiteralPath (Join-Path $d $App.Exe) -ErrorAction SilentlyContinue).VersionInfo.ProductVersion
        if ($v -match '^\d+\.\d+\.\d+') { return $Matches[0] }
    }
    $e = Get-SetupEntry
    if ($e) { return $e.DisplayVersion }
    return $null
}
function Install-Self($rel, [string]$file) {
    $uninstaller = Join-Path $work 'uninstall.ps1'
    [IO.File]::WriteAllText($uninstaller, $UninstallTemplate, (New-Object Text.UTF8Encoding $true))
    $res = Step "$($T.running) ($($T.uac))" { Invoke-Elevated @('-Exe', "`"$file`"", '-Version', $rel.Version, '-Uninstaller', "`"$uninstaller`"") }
    if (-not $res) { $state.declined = $true; throw (New-Object OperationCanceledException) }
    if (-not $res.ok) { throw $res.message }
    return (Join-Path $env:ProgramFiles "AsenaPlug\$($App.Exe)")
}

# ---------------------------------------------------------------- install / update
$work = Join-Path $env:TEMP ($App.Id + '-install-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
$parent = Split-Path $Dir -Parent
$stagingDir = Join-Path $parent ('.' + $App.Id + '-new-' + [Guid]::NewGuid().ToString('N').Substring(0, 6))
$backupDir = Join-Path $parent ('.' + $App.Id + '-old-' + [Guid]::NewGuid().ToString('N').Substring(0, 6))
$undo = New-Object Collections.Generic.List[scriptblock]
# what the steps saw before they changed anything (the undo blocks read it; they run in this scope)
$state = @{ stage = $T.looking; wasRunning = @(); legacy = @() }
$oldOut = [Console]::OutputEncoding
$committed = $false
try {
    [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false
    Log "---- $($App.Name) installer, PowerShell $($PSVersionTable.PSVersion), $([Environment]::OSVersion.VersionString)"
    if ($interactive -and -not (Opt 'LANGUAGE')) {
        Banner
        $tr = (Choose $T.qLang @(@('English', 'en'), @('Türkçe (Turkish)', 'tr')) $(if ($tr) { 'tr' } else { 'en' })) -eq 'tr'
        $T = Get-Texts $tr
        if (-not [Console]::IsOutputRedirected) { Clear-Host }
    }
    Banner
    if (Opt 'UNINSTALL') { Invoke-Uninstall; $committed = $true; return }

    # ------------------------------------------------------------ which release
    $installed = Get-Installed
    $src = Opt 'SOURCE'
    if ($src) {
        $src = (Resolve-Path -LiteralPath $src).Path
        $m = [regex]::Match([IO.Path]::GetFileName($src), '\d+\.\d+\.\d+')
        $rel = [pscustomobject]@{ Version = $(if ($m.Success) { $m.Value } else { '0.0.0' }); Url = $null; Name = [IO.Path]::GetFileName($src); Size = (Get-Item -LiteralPath $src).Length; Sha = $null }
    }
    else {
        try { $rel = Step $T.looking { Get-Release } }
        catch { Log "release lookup: $($_.Exception.Message)"; Box $COL.err $T.netTitle ($T.netBody + "`n`n$($T.errDetail): $($_.Exception.Message)"); return }
        if (-not $rel) { Box $COL.warn $T.errTitle $T.noRelease; return }
    }
    Log "release $($rel.Version) ($($rel.Name)), installed: $installed"
    Report @{ version = $rel.Version; size = $rel.Size }
    if ($installed -and $installed -eq $rel.Version -and -not (Opt 'FORCE') -and -not $src) {
        Say $GL.ok $COL.ok ($T.upToDate -f $App.Name, $installed)
        if (-not ($interactive -and (Confirm $T.qReinstall $T.reinstall $T.keep $false))) { return }
    }
    $update = [bool]$installed
    $title = if ($update) { $T.welcomeUpd -f $App.Name } else { $T.welcomeNew -f $App.Name }
    $where = Get-InstallDir
    $body = ($T.body -f $rel.Version, (Human $rel.Size), $(if ($where) { $where } elseif ($App.Mode -eq 'setup') { $App.DefaultDir } else { $Dir })) + "`n`n" + $(if ($App.Admin) { $T.bodyAdmin } else { $T.bodyUser })
    if ($installed) { $body = ($T.current -f $installed) + "`n" + $body }
    Box $COL.accent $title $body
    foreach ($o in @(Find-OtherInstall | Select-Object -Unique)) { Box $COL.warn '' ($T.other -f $App.Name, $o) }
    if ($interactive -and -not (Confirm $T.qGo $(if ($update) { $T.goUpd } else { $T.go }) $T.cancel $true)) { throw (New-Object OperationCanceledException) }
    $autostart = $false
    if ($App.Mode -ne 'setup' -and $App.Autostart -eq 'ask') {
        $prev = (Get-ItemProperty -LiteralPath $RunKey -ErrorAction SilentlyContinue).($App.Id)
        $autostart = if ($update) { [bool]$prev } else { Confirm ($T.qAutostart -f $App.Name) $T.yes $T.no $false }
    }
    Write-Host ''

    # ------------------------------------------------------------ download and verify
    New-Item -ItemType Directory -Force $work | Out-Null
    $file = Join-Path $work $rel.Name
    if ($src) { Copy-Item -LiteralPath $src $file }
    else {
        $state.stage = $T.downloading
        Get-WithBar $rel.Url $file "$($T.downloading) $($App.Name) $($rel.Version)" $rel.Size
        if ($rel.Sha) {
            Step $T.verifying {
                $want = ([string](Invoke-RestMethod -Uri $rel.Sha -Headers @{ 'User-Agent' = "$($App.Id)-install" } -TimeoutSec 30) -split '\s+' | Where-Object { $_ })[0].ToLower()
                $got = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLower()
                Log "sha256 want $want got $got"
                if ($want -ne $got) { throw $T.badPkg }
            }
        }
    }

    $exe = Install-Self $rel $file
    $committed = $true
    Log "installed $($rel.Version)"
    if (Test-Path -LiteralPath $backupDir) { Remove-Item -LiteralPath $backupDir -Recurse -Force -ErrorAction SilentlyContinue }

    Report @{ exe = [string]$exe; version = $rel.Version }
    $done = if ($update) { $T.doneUpd -f $App.Name, $rel.Version } else { $T.doneNew -f $App.Name, $rel.Version }
    Box $COL.ok $done $(if ($App.Command) { $T.doneCli -f $App.Name, $App.Command } else { $T.doneBody -f $App.Name })
    # what was running before the update runs again; a new install asks
    if ($App.Launch -and $exe -and (Test-Path -LiteralPath $exe)) {
        if ($state.wasRunning.Count) { Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe) }
        elseif (-not $update -and $interactive -and (Confirm ($T.qStart -f $App.Name) $T.yes $T.no $true)) { Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe) }
    }
}
catch [OperationCanceledException] {
    Log $(if ($state.declined) { 'permission declined' } else { 'cancelled' })
    Write-Host ''
    if ($state.declined) { Box $COL.warn $T.uacTitle $T.uacBody } else { Box $COL.warn $T.cancelTitle $T.cancelBody }
}
catch {
    Log "error at '$($state.stage)': $($_.Exception.Message)`n$($_.ScriptStackTrace)"
    Write-Host ''
    Box $COL.err $T.errTitle (($T.errBody -f $state.stage) + "`n`n$($T.errDetail): $($_.Exception.Message)`n$($T.errLog): $LogFile`n`n" + $T.errRetry)
}
finally {
    # Ctrl+C lands here too: undo in reverse order, then start what was running before
    if (-not $committed) {
        for ($i = $undo.Count - 1; $i -ge 0; $i--) { try { & $undo[$i] } catch { Log "undo: $($_.Exception.Message)" } }
        if ($undo.Count) { Log 'rolled back' }
        foreach ($p in $state.wasRunning) { if (Test-Path -LiteralPath $p) { try { Start-Process -FilePath $p -WorkingDirectory (Split-Path $p) } catch {} } }
    }
    if (Test-Path -LiteralPath $stagingDir) { Remove-Item -LiteralPath $stagingDir -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue }
    try { [Console]::OutputEncoding = $oldOut } catch {}
    Report @{ finished = $true }
    Write-Host -NoNewline $RESET
    Write-Host ''
}
}
