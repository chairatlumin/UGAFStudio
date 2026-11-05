[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("OpenCode", "Hermes")]
    [string]$Runtime,
    [Parameter(Mandatory = $true)]
    [string]$Request,
    [string]$Repo = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path -LiteralPath $Repo).Path
$validator = Join-Path $Repo "scripts/validate_qa_team.py"
& python $validator
if ($LASTEXITCODE -ne 0) { throw "QA specialist setup validation failed." }

if ($Runtime -eq "OpenCode") {
    $opencode = Get-Command opencode -ErrorAction Stop
    & $opencode.Source run --dir $Repo --agent fmv-qa-orchestrator --command qa-campaign $Request
    exit $LASTEXITCODE
}

$hermes = Get-Command hermes -ErrorAction Stop
$prompt = @"
Use the project-local game-qa-orchestra skill to run this QA request. Work in $Repo. Delegate the specialist roles defined by the skill with complete, self-contained context. Do not execute gameplay unless this request explicitly authorizes a supervised run and all safety gates are satisfied. Request: $Request
"@
$tempPrompt = Join-Path ([System.IO.Path]::GetTempPath()) ("ugaf-qa-" + [guid]::NewGuid().ToString("N") + ".txt")
try {
    [System.IO.File]::WriteAllText($tempPrompt, $prompt, [System.Text.UTF8Encoding]::new($false))
    Write-Host "If Hermes reports this project skill as untrusted, review it and run: hermes skills trust `"$Repo`""
    & $hermes.Source chat --query-file $tempPrompt --oneshot --max-turns 30 --run-budget 900 `
        --toolsets coding --in $Repo --skills game-qa-orchestra
    exit $LASTEXITCODE
}
finally {
    Remove-Item -LiteralPath $tempPrompt -Force -ErrorAction SilentlyContinue
}
