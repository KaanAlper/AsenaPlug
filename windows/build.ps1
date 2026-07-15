<#
.SYNOPSIS
    asena.exe üret (PyInstaller, tek dosya, konsolsuz).

.DESCRIPTION
    Uygun bir CPython yorumlayıcısı otomatik seçilir (PyPy reddedilir — PySide6/
    PyInstaller PyPy'de çalışmaz). Bağımlılıklar SEÇİLEN yorumlayıcıya kurulur
    (python/pip uyuşmazlığı böyle elenir). Build başarısızsa script hata verir.

.PARAMETER Python
    Kullanılacak Python'u elle belirt. Örn:
      .\build.ps1 -Python "$env:USERPROFILE\anaconda3\python.exe"

.PARAMETER NoInstall
    requirements.txt kurulumunu atla (zaten kuruluysa).

.NOTES
    Çıktı: dist\asena.exe
#>
param(
    [string]$Python = "",
    [switch]$NoInstall
)
Set-StrictMode -Version 1.0
$ErrorActionPreference = "Stop"

function Test-CPython([string]$exe, [string[]]$pre) {
    try {
        $out = & $exe @pre -c "import sys;print(sys.implementation.name)" 2>$null
        if ($LASTEXITCODE -eq 0 -and "$out".Trim() -eq "cpython") { return $true }
    } catch {}
    return $false
}

Push-Location $PSScriptRoot
try {
    foreach ($f in @("bundled\usque.exe", "bundled\wintun.dll", "bundled\dnsproxy.exe")) {
        if (-not (Test-Path $f)) { throw "Eksik bundle dosyası: $f" }
    }
    if (-not (Test-Path "requirements.txt")) { throw "requirements.txt yok." }
    # İkon MUTLAK yolla verilir (PyInstaller CWD'si farklı olursa sessizce atlamasın)
    $IconPath = Join-Path $PSScriptRoot "assets\AsenaPlug.ico"
    if (-not (Test-Path $IconPath)) { throw "İkon yok: $IconPath" }
    Write-Host "İkon: $IconPath" -ForegroundColor Cyan

    # --- Uygun CPython seç (PyPy DEĞİL) ---
    $candidates = @()
    if ($Python) { $candidates += ,@($Python, @()) }
    $candidates += ,@("py", @("-3"))
    $candidates += ,@("python", @())
    $candidates += ,@("$env:USERPROFILE\anaconda3\python.exe", @())

    $pyExe = $null; $pyPre = @()
    foreach ($c in $candidates) {
        if (Test-CPython $c[0] $c[1]) { $pyExe = $c[0]; $pyPre = $c[1]; break }
    }
    if (-not $pyExe) {
        throw ("Uygun CPython bulunamadı (PyPy kabul edilmez).`n" +
               "CPython 3.10+ kur (python.org) veya elle belirt:`n" +
               "  .\build.ps1 -Python C:\path\to\python.exe")
    }
    $ver = (& $pyExe @pyPre -c "import sys;print('.'.join(map(str,sys.version_info[:3])))").Trim()
    Write-Host "Python: $pyExe $($pyPre -join ' ')  [CPython $ver]" -ForegroundColor Cyan

    # --- Bağımlılıklar (SEÇİLEN yorumlayıcıya) ---
    if (-not $NoInstall) {
        Write-Host "Bağımlılıklar kuruluyor (requirements.txt)..." -ForegroundColor Cyan
        & $pyExe @pyPre -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw "pip install başarısız (exit $LASTEXITCODE)" }
    }

    # Tray yalnız QtWidgets/QtGui/QtCore kullanır. PyInstaller bazı ağır Qt
    # modüllerini dolaylı çeker; bunları dışla -> exe küçülür -> onefile extract
    # (autostart açılış gecikmesi) kısalır. Bunlar import EDİLMİYOR, güvenli.
    $exclude = @(
        "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
        "PySide6.QtQuickWidgets", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel", "PySide6.QtWebSockets",
        "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtCharts", "PySide6.QtGraphs",
        "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
        "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtPositioning", "PySide6.QtLocation",
        "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSensors", "PySide6.QtSerialPort",
        "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtTextToSpeech",
        "PySide6.QtHttpServer", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
        "PySide6.QtStateMachine", "tkinter", "unittest", "pydoc", "test"
    )
    $excludeArgs = @()
    foreach ($m in $exclude) { $excludeArgs += "--exclude-module"; $excludeArgs += $m }

    # --- Build ---
    Write-Host "PyInstaller çalışıyor..." -ForegroundColor Cyan
    & $pyExe @pyPre -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name AsenaPlug `
        --icon "$IconPath" `
        --paths . `
        --add-data "bundled;bundled" `
        --add-data "scripts;scripts" `
        --add-data "assets;assets" `
        --hidden-import asenaplug `
        --hidden-import asenaplug.paths `
        --hidden-import asenaplug.win `
        --hidden-import asenaplug.state `
        --hidden-import asenaplug.install `
        --hidden-import asenaplug.tray `
        --hidden-import asenaplug.i18n `
        --hidden-import asenaplug.update `
        --hidden-import winotify `
        @excludeArgs `
        "AsenaPlug.pyw"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller başarısız (exit $LASTEXITCODE)" }

    Write-Host "`nTamam -> dist\AsenaPlug.exe" -ForegroundColor Green
}
finally {
    Pop-Location
}
