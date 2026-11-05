#Requires -Version 5.1
param(
    [string]$OutputDirectory = "dist",
    [switch]$IncludeSourceReports
)
<#
Reproducible Windows one-directory build of the QA Workbench:
  dist/UGAF-QA/UGAF-QA.exe

Run from the repo root:  powershell -ExecutionPolicy Bypass -File scripts/build_qa_exe.ps1
Use -OutputDirectory dist/UGAF-QA-Next to create a side-by-side candidate.
No signing or installer. Game installs + local VLM endpoint still required at runtime.
#>
$ErrorActionPreference = "Stop"
$ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $ROOT
$outputRoot = if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    [System.IO.Path]::GetFullPath($OutputDirectory)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $ROOT $OutputDirectory))
}
$outputName = [System.IO.Path]::GetFileName($outputRoot.TrimEnd('\'))
$workRoot = Join-Path $ROOT ("build\pyinstaller-" + $outputName)
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

$python = Join-Path $ROOT ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}
& $python --version
& $python -m pip --version
& $python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('PyInstaller') else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller (build-only)..."
    & $python -m pip install "pyinstaller>=6.0"
}
& $python -c "import robot; import pyautogui" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing Robot Framework support for the standalone build..."
    & $python -m pip install "robotframework>=7.3,<8" "pyautogui>=0.9.54"
}

$sep = ";"
$datas = @(
    "scripts/game_profiles.json${sep}scripts",
    "qa_framework/testcases/catalog.json${sep}qa_framework/testcases",
    "qa_framework/testcases/highschool_blood_cases.json${sep}qa_framework/testcases",
    "docs/qa-workbench-exe.md${sep}docs",
    "docs/studio-framework-comfyui.md${sep}docs",
    "docs/game-memory-and-sheets.md${sep}docs",
    "docs/robot-framework.md${sep}docs",
    "docs/unreal-telemetry-bridge.md${sep}docs",
    "docs/ta-optimize-unreal-graph.md${sep}docs",
    "qa_framework/workflows/comfyui_sdxl_image_review_api.json${sep}qa_framework/workflows",
    "qa_framework/workflows/ugaf_ta_optimize_mockup_api.json${sep}qa_framework/workflows",
    "qa_framework/robot/examples/screen_smoke.robot${sep}qa_framework/robot/examples",
    "qa_framework/robot/examples/decision_api_preflight.robot${sep}qa_framework/robot/examples"
)
if (Test-Path -LiteralPath "qa_framework/testcases/local_cases.json") {
    $datas += "qa_framework/testcases/local_cases.json${sep}qa_framework/testcases"
}

$hidden = @(
    "fastmcp", "mcp", "docx", "PySide6", "cv2", "mss", "PIL", "loguru",
    "pytesseract", "numpy", "robot", "qa_framework.robot.cli", "qa_framework.robot.decision_api",
    "scripts.fmv_harness", "scripts.live_gameplay_agent",
    "scripts.session_report", "qa_framework.mcp_server", "qa_framework.mcp_tools",
    "app.database.database"
)

$args = @("--onedir", "--windowed", "--name", "UGAF-QA", "--paths", ".", "--noconfirm")
foreach ($d in $datas) { $args += @("--add-data", $d) }
foreach ($h in $hidden) { $args += @("--hidden-import", $h) }
foreach ($m in @("qa_framework", "app", "scripts", "tools", "robot")) {
    $args += @("--collect-submodules", $m)
}
$args += @("--collect-data", "robot")
$args += "main.py"

$originalPath = $env:PATH
$packageRoot = Join-Path $outputRoot "UGAF-QA"
$specPath = Join-Path $ROOT "UGAF-QA.spec"
$specExisted = Test-Path -LiteralPath $specPath
$specBackup = Join-Path $workRoot "UGAF-QA.spec.preserved"
$specBackupReady = $false
$null = New-Item -ItemType Directory -Path $workRoot -Force
if ($specExisted) {
    Copy-Item -LiteralPath $specPath -Destination $specBackup -Force
    $specBackupReady = $true
}
$mutableDirs = @("data", "reports", "logs", "screenshots", "config")
$preserveRoot = $null
foreach ($name in $mutableDirs) {
    $sourceDir = Join-Path $packageRoot $name
    if (Test-Path -LiteralPath $sourceDir) {
        if (-not $preserveRoot) {
            $preserveRoot = Join-Path $ROOT ("build\qa-user-data-preserve-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
            New-Item -ItemType Directory -Path $preserveRoot -Force | Out-Null
        }
        Copy-Item -LiteralPath $sourceDir -Destination $preserveRoot -Recurse -Force
        Write-Host "Preserved packaged mutable directory: $name"
    }
}
$systemDllDirectory = [System.IO.Path]::GetFullPath((Join-Path $env:WINDIR "System32")).TrimEnd('\')
$buildPath = @()
foreach ($entry in ($originalPath -split [System.IO.Path]::PathSeparator)) {
    if (-not $entry) { continue }
    try {
        $resolvedEntry = [System.IO.Path]::GetFullPath($entry).TrimEnd('\')
        $icuDll = Join-Path $resolvedEntry "icuuc.dll"
        if ((Test-Path -LiteralPath $icuDll) -and
            -not $resolvedEntry.Equals($systemDllDirectory, [System.StringComparison]::OrdinalIgnoreCase)) {
            Write-Host "Ignoring external ICU DLL during build: $icuDll"
            continue
        }
    } catch {
        # Preserve unusual PATH entries; PyInstaller will report genuine load issues.
    }
    $buildPath += $entry
}

try {
    # Qt6Core imports icuuc.dll. Do not let unrelated application ICU copies
    # (for example Poppler on PATH) override the Windows ICU used at runtime.
    $env:PATH = $buildPath -join [System.IO.Path]::PathSeparator
    & $python -m PyInstaller --distpath $outputRoot --workpath $workRoot @args
} finally {
    $env:PATH = $originalPath
    if ($specBackupReady -and (Test-Path -LiteralPath $specBackup)) {
        Copy-Item -LiteralPath $specBackup -Destination $specPath -Force
    } elseif (-not $specExisted -and (Test-Path -LiteralPath $specPath)) {
        Remove-Item -LiteralPath $specPath -Force
    }
}
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed with exit $LASTEXITCODE" }

# The onedir target is recreated by PyInstaller. Restore mutable user data and
# config, then seed source snapshots only when they are newer or not present.
$packageRoot = Join-Path $outputRoot "UGAF-QA"
foreach ($name in $mutableDirs) {
    $targetDir = Join-Path $packageRoot $name
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    $savedDir = if ($preserveRoot) { Join-Path $preserveRoot $name } else { $null }
    if ($savedDir -and (Test-Path -LiteralPath $savedDir)) {
        Copy-Item -LiteralPath $savedDir -Destination $packageRoot -Recurse -Force
    }
}
$packageData = Join-Path $packageRoot "data"
$sourceData = Join-Path $ROOT "data"
foreach ($sourceFile in (Get-ChildItem -LiteralPath $sourceData -File -Recurse -ErrorAction SilentlyContinue)) {
    $relative = $sourceFile.FullName.Substring($sourceData.TrimEnd('\').Length).TrimStart('\')
    $destination = Join-Path $packageData $relative
    if (-not (Test-Path -LiteralPath $destination) -or
        $sourceFile.LastWriteTimeUtc -gt (Get-Item -LiteralPath $destination).LastWriteTimeUtc) {
        $destinationDirectory = Split-Path -Parent $destination
        New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
        Copy-Item -LiteralPath $sourceFile.FullName -Destination $destination -Force
    }
}
$packageReports = Join-Path $packageRoot "reports"
New-Item -ItemType Directory -Path $packageReports -Force | Out-Null
if ($IncludeSourceReports) {
    $sourceReports = Join-Path $ROOT "reports"
    foreach ($sourceFile in (Get-ChildItem -LiteralPath $sourceReports -File -Recurse -ErrorAction SilentlyContinue)) {
        $relative = $sourceFile.FullName.Substring($sourceReports.TrimEnd('\').Length).TrimStart('\')
        $destination = Join-Path $packageReports $relative
        if (-not (Test-Path -LiteralPath $destination) -or
            $sourceFile.LastWriteTimeUtc -gt (Get-Item -LiteralPath $destination).LastWriteTimeUtc) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
            Copy-Item -LiteralPath $sourceFile.FullName -Destination $destination -Force
        }
    }
}
$sourceConfig = Join-Path $ROOT "config\config.toml"
$packageConfig = Join-Path $packageRoot "config\config.toml"
if (-not (Test-Path -LiteralPath $packageConfig) -and (Test-Path -LiteralPath $sourceConfig)) {
    Copy-Item -LiteralPath $sourceConfig -Destination $packageConfig -Force
}

$exe = Join-Path $packageRoot "UGAF-QA.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "Expected exe not found: $exe" }
Write-Host "Build OK: $exe"
Write-Host "Run:  `"$exe`" --qa-workbench"
