# UGAFStudio Dev Runtime bootstrap
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\start-ugaf.ps1
#
# Ensures the local development runtime is up:
#   - Docker Engine (via `docker version`)
#   - Docker MCP client for OpenCode is connected (MCP_DOCKER)
#   - OpenCode server (127.0.0.1:4096)
#
# Architecture:
#   Docker MCP (global client) -> OpenCode -> MCP_DOCKER ->
#   `docker mcp gateway run --profile ugaf_dev` -> GitHub MCP
#
#   The gateway is managed by OpenCode itself. This script only verifies the
#   integration through the Docker MCP client configuration/status; it never
#   starts the gateway, creates profiles, runs oauth/connect, or modifies
#   MCP or OpenCode configuration.
#
# Idempotent: existing healthy services are reused, never duplicated.
# Non-destructive: kills nothing, touches no source, tests, OpenCode
# commands, git state, or configuration, and never binds a port publicly.
#
# Requires Docker MCP client for OpenCode to be connected. If MCP_DOCKER is
# missing, re-run this after:
#   docker mcp client connect opencode --global --profile ugaf_dev

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$OpenCodePort = 4096
$OpenCodeHealthUrl = "http://127.0.0.1:$OpenCodePort/global/health"
$DockerWaitTimeoutSec = 300
$MCPWaitTimeoutSec = 300
$OpenCodeWaitTimeoutSec = 30

# ---- State collected for the final summary ----
$dockerStatus = 'FAIL'
$mcpStatus = 'FAIL'
$ocStatus = 'FAIL'
$projectStatus = 'FAIL'
$ocVersion = $null
$failReasons = @()

function Write-Log {
    param([string]$Message)
    Write-Host $Message
}

function Get-OpenCodeHealth {
    try {
        $r = Invoke-WebRequest -Uri $OpenCodeHealthUrl -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) {
            return ($r.Content | ConvertFrom-Json)
        }
    }
    catch {
        return $null
    }
    return $null
}

function Wait-OpenCodeHealth {
    param([int]$TimeoutSec = $OpenCodeWaitTimeoutSec)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        $h = Get-OpenCodeHealth
        if ($h -and $h.healthy) { return $h }
        Start-Sleep -Milliseconds 500
    }
    return $null
}

function Test-DockerEngine {
    $output = (& docker version 2>&1) | Out-String
    if ($LASTEXITCODE -ne 0) { return $false }
    return $output -match 'Server:'
}

# Polls `docker version` until the Docker Engine responds or the timeout
# elapses. Poll interval: 2 seconds.
function Wait-DockerEngine {
    param([int]$TimeoutSec = $DockerWaitTimeoutSec)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        if (Test-DockerEngine) { return $true }
        Start-Sleep -Seconds 2
    }
    return (Test-DockerEngine)
}

# Returns the global OpenCode entry from `docker mcp client ls --json --global`
# (falling back to the project-wide entry if the global entry is absent).
function Get-DockerMCPOpenCodeConfig {
    $args = @('mcp', 'client', 'ls', '--json', '--global')
    $raw = (& docker $args 2>&1) | Out-String
    if ($LASTEXITCODE -eq 0) {
        try {
            $obj = $raw | ConvertFrom-Json
            if ($obj.opencode) { return $obj.opencode }
        }
        catch {
            # fall through to project-wide lookup
        }
    }
    $raw = (& docker mcp client ls --json 2>&1) | Out-String
    if ($LASTEXITCODE -eq 0) {
        try {
            $obj = $raw | ConvertFrom-Json
            if ($obj.opencode) { return $obj.opencode }
        }
        catch {
            return $null
        }
    }
    return $null
}

# True when the Docker MCP client is connected to OpenCode with MCP_DOCKER
# and the Docker MCP Catalog is connected.
function Test-DockerMCPOpenCode {
    $entry = Get-DockerMCPOpenCodeConfig
    if (-not $entry) { return $false }
    if ($entry.dockerMCPCatalogConnected -ne $true) { return $false }
    $names = @()
    if ($entry.Cfg -and $entry.Cfg.STDIOServers) {
        $names = @($entry.Cfg.STDIOServers | ForEach-Object { $_.name })
    }
    return ($names -contains 'MCP_DOCKER')
}

# Polls the Docker MCP client/OpenCode integration until it reports ready
# or the timeout elapses. Poll interval: 2 seconds.
function Wait-DockerMCPOpenCode {
    param([int]$TimeoutSec = $MCPWaitTimeoutSec)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        if (Test-DockerMCPOpenCode) { return $true }
        Start-Sleep -Seconds 2
    }
    return (Test-DockerMCPOpenCode)
}

# ---- A. Verify the working directory is the UGAFStudio repository ----
if (-not (Test-Path (Join-Path $RepoRoot 'AGENTS.md')) -or
    -not (Test-Path (Join-Path $RepoRoot 'pyproject.toml'))) {
    Write-Log 'ERROR: working directory is not the UGAFStudio repository.'
    Write-Log "Expected UGAFStudio files under: $RepoRoot"
    exit 10
}
$projectStatus = 'OK'

# ---- B. Docker ----
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    $failReasons += 'Docker CLI not found on PATH.'
}
elseif (Wait-DockerEngine) {
    $dockerStatus = 'OK'
}
else {
    $failReasons += "Docker Engine did not become ready within ${DockerWaitTimeoutSec} seconds (polled every 2s). Please start Docker Desktop and re-run this script."
}

# Docker must be ready before MCP_DOCKER and OpenCode are checked.
if ($dockerStatus -ne 'OK') {
    Write-Log ''
    Write-Log 'Runtime NOT ready. Docker Engine is required before checking MCP_DOCKER and OpenCode.'
    foreach ($reason in ($failReasons | Select-Object -Unique)) {
        Write-Log ("  - {0}" -f $reason)
    }
    exit 1
}

# ---- C. Docker MCP / OpenCode integration ----
if (Wait-DockerMCPOpenCode) {
    $mcpStatus = 'OK'
}
else {
    $mcpStatus = 'FAIL'
    $failReasons += "Docker MCP client did not become ready within ${MCPWaitTimeoutSec} seconds."
    $failReasons += 'Docker MCP client is not connected to OpenCode (MCP_DOCKER / Docker MCP Catalog not connected).'
    $failReasons += 'Connect it and re-run this script:  docker mcp client connect opencode --global --profile ugaf_dev'
    $failReasons += 'MCP configuration is not modified automatically.'
}

# MCP_DOCKER must be ready before OpenCode is started.
if ($mcpStatus -ne 'OK') {
    Write-Log ''
    Write-Log 'Runtime NOT ready. Docker MCP (MCP_DOCKER) is required before starting OpenCode.'
    foreach ($reason in ($failReasons | Select-Object -Unique)) {
        Write-Log ("  - {0}" -f $reason)
    }
    exit 2
}

# ---- D. OpenCode ----
$ocCli = Get-Command opencode -ErrorAction SilentlyContinue
if (-not $ocCli) {
    $failReasons += 'OpenCode CLI not found on PATH.'
}
else {
    $ocHealth = Get-OpenCodeHealth
    if ($ocHealth -and $ocHealth.healthy) {
        $ocStatus = 'OK'
        Write-Log "OpenCode server already healthy at $OpenCodeHealthUrl"
    }
    else {
        Write-Log 'Starting OpenCode server on 127.0.0.1:4096...'
        $logDir = Join-Path $env:TEMP 'ugaf-dev-runtime'
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        $ocOut = Join-Path $logDir 'opencode.out.log'
        $ocErr = Join-Path $logDir 'opencode.err.log'
        $ocArgs = @('serve', '--hostname', '127.0.0.1', '--port', "$OpenCodePort")
        $started = $false
        try {
            # Resolve the real OpenCode executable. On Windows the PATH shim
            # is usually opencode.ps1; the npm-installed binary lives at
            # <shim dir>\node_modules\opencode-ai\bin\opencode.exe. When found,
            # launch it directly instead of wrapping the shim in powershell.exe.
            $ocExe = $null
            $ocShim = $ocCli.Source
            if ($ocShim) {
                $candidate = Join-Path (Split-Path -Parent $ocShim) 'node_modules\opencode-ai\bin\opencode.exe'
                if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                    $ocExe = $candidate
                }
            }
            if (-not $ocExe) {
                $ocExe = (Get-Command opencode.cmd -ErrorAction SilentlyContinue).Source
            }
            if (-not $ocExe) { $ocExe = $ocShim }
            if ($ocExe -match '\.ps1$') {
                Start-Process -FilePath 'powershell.exe' `
                    -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', "& '$ocExe' $($ocArgs -join ' ')") `
                    -WorkingDirectory $RepoRoot `
                    -RedirectStandardOutput $ocOut `
                    -RedirectStandardError $ocErr `
                    -WindowStyle Hidden | Out-Null
                $started = $true
            }
            else {
                Start-Process -FilePath $ocExe -ArgumentList $ocArgs `
                    -WorkingDirectory $RepoRoot `
                    -RedirectStandardOutput $ocOut `
                    -RedirectStandardError $ocErr `
                    -WindowStyle Hidden | Out-Null
                $started = $true
            }
        }
        catch {
            $failReasons += "Failed to launch OpenCode server: $($_.Exception.Message)"
        }
        if ($started) {
            $ocHealth = Wait-OpenCodeHealth
            if ($ocHealth -and $ocHealth.healthy) {
                $ocStatus = 'OK'
            }
            else {
                $failReasons += 'OpenCode server did not become healthy on 127.0.0.1:4096.'
                if (Test-Path $ocErr) {
                    $errTail = (Get-Content -LiteralPath $ocErr -Tail 5 -ErrorAction SilentlyContinue) -join ' '
                    if ($errTail) { $failReasons += "OpenCode log: $errTail" }
                }
            }
        }
    }
    if ($ocStatus -eq 'OK') {
        if ($ocHealth -and $ocHealth.version) {
            $ocVersion = $ocHealth.version
        }
        elseif ($ocCli) {
            try { $ocVersion = (& opencode --version 2>&1 | Out-String).Trim() } catch { $ocVersion = $null }
        }
    }
}

# ---- E. Final verification ----
if ($dockerStatus -eq 'OK' -and -not (Test-DockerEngine)) {
    $dockerStatus = 'FAIL'
    $failReasons += 'Docker Engine became unavailable during startup.'
}
if ($mcpStatus -eq 'OK' -and -not (Test-DockerMCPOpenCode)) {
    $mcpStatus = 'FAIL'
    $failReasons += 'MCP_DOCKER configuration for OpenCode is no longer present.'
}
if ($ocStatus -eq 'OK') {
    $ocHealth = Get-OpenCodeHealth
    if (-not ($ocHealth -and $ocHealth.healthy)) {
        $ocStatus = 'FAIL'
        $failReasons += 'OpenCode server is not returning healthy=true on /global/health.'
    }
}

# ---- Summary ----
$allOk = ($dockerStatus -eq 'OK') -and
         ($mcpStatus -eq 'OK') -and
         ($ocStatus -eq 'OK') -and
         ($projectStatus -eq 'OK')

$bar = '================================'
Write-Log $bar
Write-Log ' UGAFStudio Dev Runtime'
Write-Log $bar
Write-Log ''
Write-Log ('Docker             {0}' -f $dockerStatus)
Write-Log ('MCP_DOCKER         {0}' -f $mcpStatus)
Write-Log ('OpenCode            {0} :{1}' -f $ocStatus, $OpenCodePort)
Write-Log ('UGAFStudio          {0}' -f $projectStatus)
Write-Log ''
if ($allOk) {
    Write-Log 'Runtime READY'
}
Write-Log $bar

if ($allOk) {
    if ($ocVersion) {
        Write-Log ("OpenCode version: {0}" -f $ocVersion)
    }
    exit 0
}

Write-Log ''
Write-Log 'Runtime NOT ready. The following component(s) failed:'
foreach ($reason in ($failReasons | Select-Object -Unique)) {
    Write-Log ("  - {0}" -f $reason)
}
if ($dockerStatus -ne 'OK') { exit 1 }
if ($mcpStatus -ne 'OK') { exit 2 }
if ($ocStatus -ne 'OK') { exit 3 }
exit 4
