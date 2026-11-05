# UGAFStudio OpenCode Bridge v1

param(
    [Parameter(Mandatory = $true)]
    [string]$Prompt,

    [string]$SessionId,

    [switch]$NewSession,

    [string]$ServerUrl = "http://127.0.0.1:4096",

    [string]$Title = "UGAFStudio ChatGPT Bridge",

    [int]$TimeoutSec = 300
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http

function ConvertTo-Utf8JsonBytes {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Object
    )

    $json = $Object | ConvertTo-Json -Depth 30 -Compress
    return [System.Text.Encoding]::UTF8.GetBytes($json)
}

function Invoke-OpenCodeJson {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("GET", "POST")]
        [string]$Method,

        [Parameter(Mandatory = $true)]
        [string]$Uri,

        [object]$Body
    )

    $client = New-Object System.Net.Http.HttpClient
    $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSec)

    try {
        if ($Method -eq "POST") {
            $json = $Body | ConvertTo-Json -Depth 30 -Compress

            $content = New-Object System.Net.Http.StringContent(
                $json,
                [System.Text.Encoding]::UTF8,
                "application/json"
            )

            $response = $client.PostAsync(
                $Uri,
                $content
            ).GetAwaiter().GetResult()
        }
        else {
            $response = $client.GetAsync(
                $Uri
            ).GetAwaiter().GetResult()
        }

        $responseText = $response.Content.ReadAsStringAsync().
            GetAwaiter().GetResult()

        if (-not $response.IsSuccessStatusCode) {
            throw "OpenCode HTTP $([int]$response.StatusCode): $responseText"
        }

        if ([string]::IsNullOrWhiteSpace($responseText)) {
            return $null
        }

        return $responseText | ConvertFrom-Json
    }
    finally {
        $client.Dispose()
    }
}
function Get-OpenCodeHealth {
    try {
        return Invoke-OpenCodeJson `
            -Method "GET" `
            -Uri "$ServerUrl/global/health"
    }
    catch {
        throw "Cannot connect to OpenCode at $ServerUrl. $($_.Exception.Message)"
    }
}

function New-OpenCodeSession {
    $body = @{
        title = $Title
    }

    return Invoke-OpenCodeJson `
        -Method "POST" `
        -Uri "$ServerUrl/session" `
        -Body $body
}

function Send-OpenCodeMessage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetSessionId
    )

    $body = @{
        parts = @(
            @{
                type = "text"
                text = $Prompt
            }
        )
    }

    return Invoke-OpenCodeJson `
        -Method "POST" `
        -Uri "$ServerUrl/session/$TargetSessionId/message" `
        -Body $body
}

function Get-AssistantText {
    param(
        [Parameter(Mandatory = $true)]
        [object]$MessageResponse
    )

    $texts = @()

    if ($MessageResponse.parts) {
        foreach ($part in @($MessageResponse.parts)) {
            if ($part.type -eq "text" -and $null -ne $part.text) {
                $texts += [string]$part.text
            }
        }
    }

    return ($texts -join "`n")
}

# Health
$health = Get-OpenCodeHealth

if (-not $health.healthy) {
    throw "OpenCode server reported unhealthy."
}

# Session
if ($NewSession) {
    $session = New-OpenCodeSession
    $SessionId = $session.id
}
elseif ([string]::IsNullOrWhiteSpace($SessionId)) {
    $session = New-OpenCodeSession
    $SessionId = $session.id
}

if ([string]::IsNullOrWhiteSpace($SessionId)) {
    throw "OpenCode session ID is empty."
}

# Message
$response = Send-OpenCodeMessage -TargetSessionId $SessionId

# Response text
$text = Get-AssistantText -MessageResponse $response

# Result
[PSCustomObject]@{
    Success   = $true
    SessionId = $SessionId
    Server    = $ServerUrl
    Healthy   = $health.healthy
    Version   = $health.version
    Model     = if ($response.info) { $response.info.modelID } else { $null }
    Provider  = if ($response.info) { $response.info.providerID } else { $null }
    Agent     = if ($response.info) { $response.info.agent } else { $null }
    Finish    = if ($response.info) { $response.info.finish } else { $null }
    Response  = $text
}



