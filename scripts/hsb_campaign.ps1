# Run the High School Blood demo across the language matrix and visual-choice
# settings. Every invocation gets a unique evidence directory. A successful
# harness sequence is still UNASSERTED; this script never reports QA PASS.
[CmdletBinding()]
param(
    [string]$Python = "C:\Python314\python.exe",
    [int]$MaxMinutes = 30,
    [int]$IdleMinutes = 3,
    [string]$Only = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$flow = Join-Path $PSScriptRoot "hsb_flow.py"
$outRoot = $env:UGAF_FMV_CAMPAIGN_OUTPUT_DIR
if (-not $outRoot) {
    $outRoot = Join-Path $repo "reports\fmv_harness\campaign"
}
$outRoot = [System.IO.Path]::GetFullPath($outRoot)
$campaignId = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")
$campaignDir = Join-Path $outRoot $campaignId
$campaignManifestPath = Join-Path $campaignDir "campaign_manifest.json"
$env:PYTHONPATH = $repo

# subtitle language, choice language, visual choice
$combos = @(
    @("english", "english", "on"),
    @("thai", "english", "on"),
    @("english", "thai", "on"),
    @("thai", "thai", "on"),
    @("english", "english", "off"),
    @("thai", "thai", "off")
)

$validSelections = @($combos | ForEach-Object { "$($_[0])-$($_[1])-$($_[2])" })
if ($Only -and $Only -notin $validSelections) {
    throw "Unknown -Only '$Only'. Choose one of: $($validSelections -join ', ')"
}

New-Item -ItemType Directory -Force -Path $campaignDir | Out-Null
$selectedCombos = @($combos | Where-Object { -not $Only -or $Only -eq "$($_[0])-$($_[1])-$($_[2])" })
$campaign = [ordered]@{
    campaign_id = $campaignId
    game = "High School Blood Demo"
    profile = "highschoolblood-demo"
    started_at_utc = [DateTime]::UtcNow.ToString("o")
    finished_at_utc = $null
    status = "RUNNING"
    qa_status = "UNASSERTED"
    selected = $Only
    runs = [System.Collections.Generic.List[object]]::new()
}

function Save-Json {
    param([string]$Path, [object]$Value)
    $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Path -Encoding utf8
}

function Save-Campaign {
    Save-Json -Path $campaignManifestPath -Value $campaign
}

function Invoke-FlowStep {
    param(
        [System.Collections.IDictionary]$RunManifest,
        [string]$RunManifestPath,
        [string]$RunDirectory,
        [string]$Name,
        [string[]]$FlowArgs
    )

    $logPath = Join-Path $RunDirectory "$Name.log"
    $step = [ordered]@{
        name = $Name
        command = @($Python, $flow) + $FlowArgs
        started_at_utc = [DateTime]::UtcNow.ToString("o")
        finished_at_utc = $null
        exit_code = $null
        status = "RUNNING"
        log = "$Name.log"
    }
    $RunManifest.steps.Add($step)
    Save-Json -Path $RunManifestPath -Value $RunManifest

    & $Python $flow @FlowArgs 2>&1 | Tee-Object -FilePath $logPath
    $exitCode = $LASTEXITCODE
    $step.exit_code = $exitCode
    $step.finished_at_utc = [DateTime]::UtcNow.ToString("o")
    $step.status = if ($exitCode -eq 0) { "COMPLETED" } else { "FAILED" }
    Save-Json -Path $RunManifestPath -Value $RunManifest
    if ($exitCode -ne 0) {
        throw "FMV step '$Name' exited with code $exitCode. See $logPath"
    }
}

Save-Campaign
try {
    foreach ($combo in $selectedCombos) {
        $subs, $choice, $visual = $combo
        $name = "subs-${subs}_choice-${choice}_visual-${visual}"
        $runDir = Join-Path $campaignDir $name
        New-Item -ItemType Directory -Force -Path $runDir | Out-Null
        $manifestPath = Join-Path $runDir "run_manifest.json"
        $run = [ordered]@{
            run_id = "$campaignId-$name"
            campaign_id = $campaignId
            game = "High School Blood Demo"
            profile = "highschoolblood-demo"
            settings = [ordered]@{ subtitle_language = $subs; choice_language = $choice; visual_choice = $visual }
            started_at_utc = [DateTime]::UtcNow.ToString("o")
            finished_at_utc = $null
            status = "RUNNING"
            qa_status = "UNASSERTED"
            steps = [System.Collections.Generic.List[object]]::new()
        }
        $campaign.runs.Add([ordered]@{ run_id = $run.run_id; directory = $name; status = "RUNNING"; qa_status = "UNASSERTED" })
        Save-Campaign
        Save-Json -Path $manifestPath -Value $run
        Write-Host "=== $name $($run.started_at_utc) ===" -ForegroundColor Cyan

        try {
            Invoke-FlowStep $run $manifestPath $runDir "fullscreen" @("fullscreen")
            Invoke-FlowStep $run $manifestPath $runDir "newgame-before-settings" @("newgame", "--evidence", $runDir)
            Invoke-FlowStep $run $manifestPath $runDir "apply-settings" @("settings", "--subtitles", $subs, "--choice", $choice,
                "--visual-choice", $visual, "--evidence", $runDir)
            Invoke-FlowStep $run $manifestPath $runDir "newgame-with-settings" @("newgame", "--evidence", $runDir)
            Invoke-FlowStep $run $manifestPath $runDir "play" @("play", "--max-minutes", $MaxMinutes, "--idle-minutes", $IdleMinutes,
                "--evidence", $runDir)
            $run.status = "COMPLETED_UNASSERTED"
        } catch {
            $run.status = "FAILED"
            $run.error = $_.Exception.Message
            throw
        } finally {
            $run.finished_at_utc = [DateTime]::UtcNow.ToString("o")
            Save-Json -Path $manifestPath -Value $run
            $campaign.runs[$campaign.runs.Count - 1].status = $run.status
            Save-Campaign
        }
    }
    $campaign.status = "COMPLETED_UNASSERTED"
    Write-Host "campaign sequence completed without testcase assertions; QA status remains UNASSERTED" -ForegroundColor Yellow
} catch {
    $campaign.status = "FAILED"
    $campaign.error = $_.Exception.Message
    throw
} finally {
    $campaign.finished_at_utc = [DateTime]::UtcNow.ToString("o")
    Save-Campaign
    Write-Host "Campaign manifest: $campaignManifestPath"
}
