#Requires -Version 5.1
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Suite,
    [string]$OutputDir = "reports/robot",
    [string[]]$Include = @(),
    [string[]]$Exclude = @(),
    [string[]]$Variable = @(),
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$exe = Join-Path $root "dist\UGAF-QA\UGAF-QA.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "UGAF-QA.exe is missing. Build it first with scripts/build_qa_exe.ps1."
}

Set-Location -LiteralPath $root
$suitePath = if ([IO.Path]::IsPathRooted($Suite)) {
    [IO.Path]::GetFullPath($Suite)
} else {
    [IO.Path]::GetFullPath((Join-Path $root $Suite))
}
$outputRoot = if ([IO.Path]::IsPathRooted($OutputDir)) {
    [IO.Path]::GetFullPath($OutputDir)
} else {
    [IO.Path]::GetFullPath((Join-Path $root $OutputDir))
}
if (-not (Test-Path -LiteralPath $suitePath)) { throw "Robot suite path does not exist: $suitePath" }
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
$workerArgs = @("--qa-worker", "qa_framework.robot.cli", $suitePath, "--output-dir", $outputRoot)
foreach ($tag in $Include) { $workerArgs += @("--include", $tag) }
foreach ($tag in $Exclude) { $workerArgs += @("--exclude", $tag) }
foreach ($item in $Variable) { $workerArgs += @("--variable", $item) }
if ($DryRun) { $workerArgs += "--dry-run" }

$quotedArgs = $workerArgs | ForEach-Object { '"' + $_.Replace('"', '\"') + '"' }
$process = Start-Process -FilePath $exe -ArgumentList $quotedArgs -WorkingDirectory $root -WindowStyle Hidden -Wait -PassThru

$manifest = Get-ChildItem -LiteralPath $outputRoot -Filter "run_manifest.json" -File -Recurse |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
if (-not $manifest) {
    throw "Robot worker did not create a run manifest (process exit $($process.ExitCode)). Check $root\dist\UGAF-QA\logs."
}

$result = Get-Content -LiteralPath $manifest.FullName -Raw | ConvertFrom-Json
Write-Host "Robot status : $($result.status)"
Write-Host "Tests        : $($result.test_count) (passed $($result.passed), failed $($result.failed), skipped $($result.skipped))"
Write-Host "QA status    : $($result.qa_status)"
Write-Host "Report       : $($result.report_html)"
Write-Host "Manifest     : $($manifest.FullName)"

if ($result.status -in @("PASS", "DRY_RUN")) { exit 0 }
if ($result.status -eq "FAIL") { exit 1 }
exit 2
