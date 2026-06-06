param()

$ErrorActionPreference = "Stop"

function Write-HookJson {
    param([hashtable]$Payload)
    $Payload | ConvertTo-Json -Compress | Write-Output
}

try {
    [Console]::In.ReadToEnd() | Out-Null

    $repoRoot = Resolve-Path (Join-Path $PSScriptRoot "../..")
    Set-Location $repoRoot

    $statusLines = @(git status --porcelain=v1)
    $branchLine = (git status --short --branch | Select-Object -First 1)

    $changedFiles = @()
    foreach ($line in $statusLines) {
        if (-not $line -or $line.Length -lt 4) {
            continue
        }

        $path = $line.Substring(3).Trim()
        if ($path -match " -> ") {
            $path = ($path -replace "^.* -> ", "")
        }
        $changedFiles += $path.Replace("\", "/")
    }

    $codeChanges = @($changedFiles | Where-Object {
        ($_ -match "^src/" -or
        $_ -match "^apps/backend/" -or
        $_ -match "^apps/frontend/src/" -or
        $_ -match "^apps/frontend/scripts/" -or
        $_ -match "^apps/desktop/src-tauri/" -or
        $_ -match "^start\.(ps1|bat)$" -or
        $_ -match "^config/" -or
        $_ -match "^\.cursor/hooks\.json$" -or
        $_ -match "^\.cursor/hooks/" -or
        $_ -match "^\.husky/") -and
        $_ -notmatch "^apps/desktop/README\.md$"
    })
    $docChanges = @($changedFiles | Where-Object {
        $_ -match "^docs/" -or
        $_ -match "^README\.md$" -or
        $_ -match "^DOCUMENTATION_MAP\.md$" -or
        $_ -match "^FINAL_DELIVERY\.md$" -or
        $_ -match "^AGENTS\.md$" -or
        $_ -match "^apps/desktop/README\.md$" -or
        $_ -match "^\.cursor/skills/"
    })

    $followups = @()
    if ($codeChanges.Count -gt 0 -and $docChanges.Count -eq 0) {
        $followups += "Code changed but no developer/user documentation file changed. Update the relevant docs before ending this development session."
        $followups += "Changed code files:"
        $followups += ($codeChanges | ForEach-Object { "- $_" })
    }

    if ($statusLines.Count -gt 0) {
        $followups += "The working tree still has uncommitted changes. Stage and commit the final state before ending this development session."
    }

    if ($branchLine -match "\[ahead\s+\d+") {
        $followups += "The current branch is ahead of its upstream. Push the committed work to GitHub before ending this development session."
    }

    if ($followups.Count -gt 0) {
        Write-HookJson @{
            followup_message = @"
AStock delivery gate is not satisfied yet.

$($followups -join "`n")

Required close-out sequence:
1. Update affected docs for any code/product behavior changes.
2. Run the relevant validation command, usually .\start.bat -Mode delivery-check.
3. Commit the final changes.
4. Push the branch to GitHub. If push fails because of network/TLS, retry and report the blocker explicitly.
"@
        }
        exit 0
    }

    Write-HookJson @{}
}
catch {
    Write-HookJson @{
        followup_message = "AStock delivery gate failed to run: $($_.Exception.Message). Inspect .cursor/hooks/enforce-session-end.ps1 before ending the session."
    }
    exit 0
}
