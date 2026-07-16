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
    Çıktı: dist\AsenaPlug.exe
#>
param(
    [string]$Python = "",
    [switch]$NoInstall,
    # Code signing (opsiyonel): sertifika thumbprint'i verilirse build sonrası imzalar.
    # SmartScreen mavi uyarısını ancak İMZA + itibar kaldırır (imzasız kalıcı uyarı).
    [string]$CertThumbprint = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com"
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

    # --- Kill-switch helper (Go/WFP) -> bundled\asena-killswitch.exe ---
    # OPSİYONEL: Go yoksa UYAR + atla; kill-switch kullanılamaz ama gerisi build olur.
    $ksOut = Join-Path $PSScriptRoot "bundled\asena-killswitch.exe"
    if (Get-Command go -ErrorAction SilentlyContinue) {
        Write-Host "Kill-switch helper derleniyor (go build, windows/amd64)..." -ForegroundColor Cyan
        Push-Location (Join-Path $PSScriptRoot "killswitch")
        try {
            $env:GOOS = "windows"; $env:GOARCH = "amd64"
            & go build -o $ksOut .
            if ($LASTEXITCODE -ne 0) { throw "go build (kill-switch) başarısız (exit $LASTEXITCODE)" }
            Write-Host "kill-switch -> $ksOut" -ForegroundColor Green
        } finally { Pop-Location }
    } else {
        Write-Host "UYARI: 'go' yok -> kill-switch helper derlenmedi (kill-switch kullanılamaz; gerisi çalışır)." -ForegroundColor Yellow
    }

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

    # --- Sürüm metadata'sı (exe'ye gömülür) ---
    # SmartScreen'i KALDIRMAZ ama exe'yi "isimsiz/şüpheli" olmaktan çıkarır: UAC
    # dialogu + dosya özelliklerinde CompanyName/ProductName/Version görünür.
    # Sürüm paths.py APP_VERSION'dan alınır (CI bunu 1.0.<run#> yapar) -> tutarlı.
    $pathsPy = Join-Path $PSScriptRoot "asenaplug\paths.py"
    $appVer = "1.0.0"
    if (Test-Path $pathsPy) {
        $m = Select-String -Path $pathsPy -Pattern 'APP_VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
        if ($m) { $appVer = $m.Matches[0].Groups[1].Value }
    }
    $vp = @($appVer -split '\.') + @('0', '0', '0', '0')
    $fv = "$([int]$vp[0]), $([int]$vp[1]), $([int]$vp[2]), 0"
    $VersionInfo = Join-Path $PSScriptRoot "version_info.txt"
    @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($fv), prodvers=($fv),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'AsenaPlug'),
      StringStruct('FileDescription', 'AsenaPlug - WARP/MASQUE tray'),
      StringStruct('FileVersion', '$appVer'),
      StringStruct('InternalName', 'AsenaPlug'),
      StringStruct('OriginalFilename', 'AsenaPlug.exe'),
      StringStruct('ProductName', 'AsenaPlug'),
      StringStruct('ProductVersion', '$appVer'),
      StringStruct('LegalCopyright', 'MIT License')
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@ | Set-Content -Path $VersionInfo -Encoding UTF8
    Write-Host "Sürüm metadata: $appVer" -ForegroundColor Cyan

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
        --version-file "$VersionInfo" `
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

    # --- Opsiyonel code signing ---
    # Sertifika thumbprint'i verilirse imzala. SmartScreen'i kaldıran ASIL adım budur
    # (imzasız exe kalıcı mavi uyarı verir). signtool Windows SDK ile gelir, PATH'te olmalı.
    if ($CertThumbprint) {
        $exe = Join-Path $PSScriptRoot "dist\AsenaPlug.exe"
        Write-Host "İmzalanıyor (signtool, thumbprint $CertThumbprint)..." -ForegroundColor Cyan
        & signtool sign /sha1 $CertThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 "$exe"
        if ($LASTEXITCODE -ne 0) { throw "signtool imzalama başarısız (exit $LASTEXITCODE)" }
        & signtool verify /pa "$exe" | Out-Null
        Write-Host "İmzalandı + doğrulandı." -ForegroundColor Green
    } else {
        Write-Host "NOT: exe İMZASIZ -> kullanıcılarda SmartScreen mavi uyarısı çıkar." -ForegroundColor Yellow
        Write-Host "     Kaldırmak için: -CertThumbprint <thumbprint> ile imzala (bkz. README)." -ForegroundColor Yellow
    }

    Write-Host "`nTamam -> dist\AsenaPlug.exe" -ForegroundColor Green
}
finally {
    Pop-Location
}
