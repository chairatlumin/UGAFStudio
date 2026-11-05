$ErrorActionPreference = 'Stop'
$prompt = Get-Content -Raw -LiteralPath "C:\Users\Admin\UGAFStudio\scripts\_hermes_task_prompt.txt"
& "C:\Users\Admin\UGAFStudio\scripts\opencode-bridge.ps1" `
    -Prompt $prompt `
    -NewSession `
    -Title "Hermes RuffFormat Followup" `
    -TimeoutSec 1800 | Out-String -Width 4096 | Set-Content -LiteralPath "C:\Users\Admin\AppData\Local\Temp\opencode\hermes_task_result.txt" -Encoding UTF8
