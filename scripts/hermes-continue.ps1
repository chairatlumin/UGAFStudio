# Continue Hermes from the shared Codex handoff without routine manual prompts.
[CmdletBinding()]
param(
    [string]$Repo,
    [string]$ServerUrl = "http://127.0.0.1:4096",
    [string]$SessionId,
    [int]$TimeoutSec = 900
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($Repo)) { $Repo = Split-Path -Parent $PSScriptRoot }
$opencode = (Get-Command opencode -ErrorAction Stop).Source
$serverReady = $false

function Test-HermesServer {
    try {
        $health = Invoke-RestMethod -Uri "$ServerUrl/global/health" -TimeoutSec 3
        return [bool]$health.healthy
    }
    catch {
        return $false
    }
}

if (-not (Test-HermesServer)) {
    $command = if ($opencode.EndsWith(".ps1")) {
        Join-Path (Split-Path $opencode) "opencode.cmd"
    } else {
        $opencode
    }
    Start-Process -FilePath $command `
        -ArgumentList @("serve", "--port", "4096", "--hostname", "127.0.0.1") `
        -WorkingDirectory $Repo `
        -WindowStyle Hidden | Out-Null

    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        if (Test-HermesServer) {
            $serverReady = $true
            break
        }
        Start-Sleep -Milliseconds 500
    }
} else {
    $serverReady = $true
}

if (-not $serverReady) {
    throw "Hermes/OpenCode server did not become ready at $ServerUrl."
}

$prompt = @"
Continue the UGAF Studio implementation from the shared Codex/Hermes handoff.

Read first:
- AGENTS.md
- .ai/PLAN.md
- .ai/ACCEPTANCE.md
- .ai/AUTO_REVIEW_POLICY.md
- .ai/RESULT.md
- .ai/REVIEW.md

Then:
1. Inspect the current git diff and identify the next active task in .ai/PLAN.md.
2. Implement the next task directly in this repository when work remains.
3. Run the relevant quality gates using the project's configured Python environment.
4. Update .ai/RESULT.md with exact commands and results.
5. Update .ai/REVIEW.md and .ai/PLAN.md when the task is complete.

Operate autonomously for routine implementation, test, formatting, and review work. Do not ask the user to say "ทำต่อ" or approve ordinary follow-ups. Stop only for the critical gates in .ai/AUTO_REVIEW_POLICY.md. Do not commit, push, merge, delete user data, or perform external writes. Do not launch live Steam games unless the active task explicitly requires a new live run.

If no implementation task remains, perform the next safe review/quality improvement and record that outcome instead of waiting.
"@

$bridgeArgs = @{
    Prompt = $prompt
    ServerUrl = $ServerUrl
    Title = "UGAFStudio Hermes Auto-Continue"
    TimeoutSec = $TimeoutSec
}
if ([string]::IsNullOrWhiteSpace($SessionId)) {
    $bridgeArgs.NewSession = $true
} else {
    $bridgeArgs.SessionId = $SessionId
}
& (Join-Path $PSScriptRoot "opencode-bridge.ps1") @bridgeArgs
