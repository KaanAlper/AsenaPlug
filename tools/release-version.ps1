# The next release version (semantic versioning), the same rule as Logical Lunge's releases.
# MAJOR when a commit since the last release is breaking ("type!:" or a "BREAKING CHANGE: <text>" footer),
# MINOR when one adds a feature ("feat:"), PATCH otherwise. -Bump patch|minor|major forces the level.
# A version any tag already used (failed or draft attempts too) is never reused.
#   ./tools/release-version.ps1 -BaseVersion 1.0.0 -Tags (git tag --list 'v*') -Commits <subjects+bodies> [-Bump auto]
param([string]$BaseVersion, [string[]]$Tags, [string[]]$Commits, [string]$Bump = 'auto')

function Get-BumpLevel([string[]]$commits) {
    $level = 'patch'
    foreach ($c in $commits) {
        if (-not $c) { continue }
        # the type (and its "!") is only the subject line's; a footer line must be "BREAKING CHANGE: <text>"
        $subject = ($c -split "`n", 2)[0].Trim()
        if ($subject -match '^\w+(\([^)]*\))?!:' -or $c -match '(?m)^BREAKING[ -]CHANGE: \S') { return 'major' }
        if ($subject -match '^feat(\([^)]*\))?:') { $level = 'minor' }
    }
    $level
}

function Step-Version([version]$v, [string]$level) {
    switch ($level) {
        'major' { [version]::new($v.Major + 1, 0, 0) }
        'minor' { [version]::new($v.Major, $v.Minor + 1, 0) }
        default { [version]::new($v.Major, $v.Minor, $v.Build + 1) }
    }
}

function Get-NextReleaseVersion([string]$base, [string[]]$tags, [string[]]$commits, [string]$bump) {
    if ($base -notmatch '^\d+\.\d+\.\d+$') { throw "Invalid base version: $base" }
    if ($bump -notin @('auto', 'patch', 'minor', 'major')) { throw "Invalid bump: $bump" }
    $used = @($tags | Where-Object { $_ -match '^v\d+\.\d+\.\d+$' } | ForEach-Object { [version]($_ -replace '^v', '') })
    if ($used.Count -eq 0) { return ([version]$base).ToString(3) }
    $last = ($used | Sort-Object -Descending)[0]
    $level = if ($bump -eq 'auto') { Get-BumpLevel $commits } else { $bump }
    $next = Step-Version $last $level
    if ([version]$base -gt $next) { $next = [version]$base }
    while ($used -contains $next) { $next = Step-Version $next 'patch' }
    $next.ToString(3)
}

if ($BaseVersion) { Get-NextReleaseVersion $BaseVersion $Tags $Commits $Bump }
