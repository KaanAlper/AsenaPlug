# Builds the windowed setup app (<file>-Setup-x64.exe and -x86.exe, names from setup.json) with the C# compiler that
# comes with Windows (.NET Framework 4.8). install.ps1 is embedded: the setup app runs the same install as the one-line command.
#   .\installer\gui\build.ps1 [-Out dist] [-Shots] [-Smoke uninstall|install]
#   -Shots   also draws every page to <Out>\shots
#   -Smoke   starts both exes with --smoke (CI): "uninstall" runs install.ps1's uninstall through the window (changes
#            nothing when the app is not installed); "install" installs with the x64 exe (<ENV>_SOURCE must point at a
#            local package) and removes it again with the x86 one
param([string]$Out = (Join-Path $PSScriptRoot '..\..\dist'), [switch]$Shots, [ValidateSet('', 'uninstall', 'install')][string]$Smoke = '')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$cfg = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'setup.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path $csc)) { throw "C# compiler not found: $csc" }
New-Item -ItemType Directory -Force $Out | Out-Null
$Out = (Resolve-Path $Out).Path
$exes = @{}
foreach ($arch in 'x64', 'x86') {
    $exe = Join-Path $Out "$($cfg.file)-Setup-$arch.exe"
    & $csc /nologo /codepage:65001 /target:winexe /optimize+ "/platform:$arch" "/out:$exe" `
        "/win32icon:$PSScriptRoot\app.ico" "/win32manifest:$PSScriptRoot\app.manifest" `
        "/resource:$root\install.ps1,install.ps1" "/resource:$PSScriptRoot\setup.json,setup.json" "/resource:$PSScriptRoot\logo.png,logo.png" `
        /r:System.Web.Extensions.dll /r:System.Windows.Forms.dll /r:System.Drawing.dll "$PSScriptRoot\Setup.cs"
    if ($LASTEXITCODE) { throw "Setup build failed ($arch)" }
    $name = Split-Path $exe -Leaf
    "$((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLower())  $name" | Set-Content -LiteralPath "$exe.sha256" -Encoding ascii -NoNewline
    $exes[$arch] = $exe
    Write-Host "built $exe"
}

function Start-Setup([string]$exe, [string[]]$arguments, [int]$minutes) {
    $p = Start-Process -FilePath $exe -ArgumentList $arguments -PassThru
    $null = $p.Handle  # keeps the exit code readable after it ends
    if (-not $p.WaitForExit($minutes * 60000)) { try { $p.Kill() } catch {}; throw "$(Split-Path $exe -Leaf) $($arguments[0]) did not finish in $minutes minutes" }
    return $p.ExitCode
}

if ($Shots) {
    $dir = Join-Path $Out 'shots'
    $code = Start-Setup $exes.x64 @('--shots', "`"$dir`"") 5
    if ($code) { throw "Screenshots failed ($code)" }
    Get-ChildItem $dir -Filter *.png | ForEach-Object { Write-Host "shot $($_.Name)" }
}
if ($Smoke) {
    $dir = Join-Path $Out 'smoke'
    foreach ($arch in 'x64', 'x86') {
        $act = if ($Smoke -eq 'install' -and $arch -eq 'x64') { 'install' } else { 'uninstall' }
        $code = Start-Setup $exes[$arch] @('--smoke', "`"$dir`"", $act) 20
        $report = Join-Path $dir "smoke-$arch.txt"
        if (Test-Path $report) { Get-Content $report | ForEach-Object { Write-Host "  $_" } }
        if ($code) { throw "Smoke test failed: $arch $act (exit $code)" }
        Write-Host "smoke $arch ${act}: ok"
    }
}
