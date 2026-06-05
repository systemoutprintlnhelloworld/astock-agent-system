param(
    [ValidateSet("status", "storage", "offline", "online", "bench", "dashboard", "backend", "frontend", "modern-ui", "scheduler", "docs")]
    [string]$Mode = "status",
    [string]$Models = "",
    [string]$BenchModel = "",
    [int]$MaxCount = 1,
    [int]$Days = 12,
    [int]$Port = 8501,
    [int]$BackendPort = 8000,
    [switch]$NoDocker
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Import-LocalEnv {
    $envPath = Join-Path $PSScriptRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath)) {
        Write-Host "No .env found; using current shell environment and config/config.yaml defaults." -ForegroundColor Yellow
        return
    }

    Get-Content -LiteralPath $envPath | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }
        $parts = $line.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($value.Length -ge 2 -and (($value[0] -eq '"' -and $value[-1] -eq '"') -or ($value[0] -eq "'" -and $value[-1] -eq "'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if ($name) {
            Set-Item -Path ("Env:" + $name) -Value $value
        }
    }
}

function Invoke-AStockCli {
    param([string[]]$CliArgs)
    & python -m astock_agent_system.cli @CliArgs
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Start-Storage {
    if (-not $NoDocker) {
        Write-Step "Starting MongoDB and Redis with Docker Compose"
        docker compose up -d
    }
    Write-Step "Checking MongoDB and Redis"
    Invoke-AStockCli @("storage", "status", "--strict")
}

function Get-PortOccupant {
    param([int]$Port)

    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if (-not $connections) {
        return $null
    }

    $connection = $connections | Select-Object -First 1
    $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
    $processDetail = $null
    try {
        $processDetail = Get-CimInstance Win32_Process -Filter "ProcessId = $($connection.OwningProcess)" -ErrorAction Stop
    }
    catch {
        $processDetail = $null
    }

    [PSCustomObject]@{
        Port = $Port
        ProcessId = $connection.OwningProcess
        ProcessName = if ($process) { $process.ProcessName } elseif ($processDetail) { $processDetail.Name } else { "unknown" }
        State = $connection.State
        Path = if ($processDetail) { $processDetail.ExecutablePath } else { $null }
        CommandLine = if ($processDetail) { $processDetail.CommandLine } else { $null }
    }
}

function Test-IsProjectBackendProcess {
    param([object]$ProcessInfo)

    if (-not $ProcessInfo -or -not $ProcessInfo.CommandLine) {
        return $false
    }

    $commandLine = $ProcessInfo.CommandLine.Replace("/", "\\")
    return $commandLine -match 'uvicorn\s+apps\.backend\.app:app' -or $commandLine -match '-m\s+uvicorn\s+apps\.backend\.app:app'
}

function Test-IsProjectFrontendProcess {
    param(
        [object]$ProcessInfo,
        [string]$FrontendDirectory
    )

    if (-not $ProcessInfo -or -not $ProcessInfo.CommandLine) {
        return $false
    }

    $commandLine = $ProcessInfo.CommandLine.Replace("/", "\\")
    $frontendMatch = $commandLine -match [Regex]::Escape($FrontendDirectory.Replace("/", "\\"))
    $nextMatch = $commandLine -match 'next(\.cmd)?\s+dev' -or $commandLine -match 'next\\dist\\server\\lib\\start-server\.js'
    return $frontendMatch -and $nextMatch
}

function Ensure-PortAvailable {
    param(
        [int]$Port,
        [string]$Purpose
    )

    $occupant = Get-PortOccupant -Port $Port
    if (-not $occupant) {
        return
    }

    Write-Host "Port $Port is already used by $Purpose." -ForegroundColor Yellow
    Write-Host "  PID: $($occupant.ProcessId)" -ForegroundColor Yellow
    Write-Host "  Process: $($occupant.ProcessName)" -ForegroundColor Yellow
    if ($occupant.Path) {
        Write-Host "  Path: $($occupant.Path)" -ForegroundColor Yellow
    }
    if ($occupant.CommandLine) {
        Write-Host "  Command: $($occupant.CommandLine)" -ForegroundColor DarkYellow
    }

    $confirmation = Read-Host "Terminate this process and continue? [y/N]"
    if ($confirmation -notmatch '^(y|yes)$') {
        throw "Startup cancelled because port $Port is occupied."
    }

    Stop-Process -Id $occupant.ProcessId -Force -ErrorAction Stop
    Start-Sleep -Milliseconds 800

    if (Get-PortOccupant -Port $Port) {
        throw "Port $Port is still occupied after trying to stop PID $($occupant.ProcessId)."
    }
}

function Get-NextDevProcesses {
    param([string]$FrontendDirectory)

    $normalizedDirectory = $FrontendDirectory.Replace("/", "\\")
    $escapedDirectory = [Regex]::Escape($normalizedDirectory)

    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            if ($_.ProcessId -eq $PID -or -not $_.CommandLine) {
                return $false
            }

            $normalizedCommand = $_.CommandLine.Replace("/", "\\")
            $normalizedCommand -match $escapedDirectory -and
            (
                $normalizedCommand -match 'next(\.cmd)?\s+dev' -or
                $normalizedCommand -match 'next\\dist\\server\\lib\\start-server\.js'
            )
        } |
        ForEach-Object {
            [PSCustomObject]@{
                ProcessId = $_.ProcessId
                ProcessName = $_.Name
                ParentProcessId = $_.ParentProcessId
                Path = $_.ExecutablePath
                CommandLine = $_.CommandLine
            }
        }
}

function Ensure-NoExistingNextDevServer {
    param([string]$FrontendDirectory)

    $processes = @(Get-NextDevProcesses -FrontendDirectory $FrontendDirectory)
    if (-not $processes.Count) {
        return
    }

    Write-Host "Another Next.js dev server is already running for $FrontendDirectory." -ForegroundColor Yellow
    foreach ($process in $processes) {
        Write-Host "  PID: $($process.ProcessId)" -ForegroundColor Yellow
        Write-Host "  Process: $($process.ProcessName)" -ForegroundColor Yellow
        if ($process.Path) {
            Write-Host "  Path: $($process.Path)" -ForegroundColor Yellow
        }
        if ($process.CommandLine) {
            Write-Host "  Command: $($process.CommandLine)" -ForegroundColor DarkYellow
        }
    }

    $confirmation = Read-Host "Terminate these Next.js dev processes and continue? [y/N]"
    if ($confirmation -notmatch '^(y|yes)$') {
        throw "Startup cancelled because another Next.js dev server is already running."
    }

    $processes | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
    }
    Start-Sleep -Milliseconds 1000

    if ((@(Get-NextDevProcesses -FrontendDirectory $FrontendDirectory)).Count -gt 0) {
        throw "A Next.js dev server is still running for $FrontendDirectory after termination."
    }
}

function Wait-ForHttpReady {
    param(
        [string]$Url,
        [string]$ServiceName,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                Write-Step "$ServiceName is ready"
                return
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    throw "$ServiceName did not become ready within $TimeoutSeconds seconds: $Url"
}

Set-Location $PSScriptRoot
Import-LocalEnv

switch ($Mode) {
    "status" {
        Write-Step "Effective non-secret configuration"
        Invoke-AStockCli @("config")
        Write-Step "Storage health"
        Invoke-AStockCli @("storage", "status")
    }
    "storage" {
        Start-Storage
    }
    "offline" {
        Start-Storage
        Write-Step "Running offline automatic paper-investment round"
        Invoke-AStockCli @("scheduler", "run-auto-investment", "--offline", "--max-count", "$MaxCount", "--days", "$Days")
    }
    "online" {
        Start-Storage
        $selectedModels = $Models
        if (-not $selectedModels) {
            $selectedModels = $env:SCHEDULER_MODELS
        }
        if (-not $selectedModels) {
            $selectedModels = "rule-baseline"
        }
        Write-Step "Running online automatic paper-investment round"
        Invoke-AStockCli @("scheduler", "run-auto-investment", "--models", $selectedModels, "--max-count", "$MaxCount", "--days", "$Days")
    }
    "bench" {
        if ($BenchModel) {
            Write-Step "Running one-model LLM bench"
            Invoke-AStockCli @("bench", "--models", $BenchModel, "--limit", "1")
        } else {
            Write-Step "Listing LLM gateway models"
            Invoke-AStockCli @("bench", "--list-models")
        }
    }
    "dashboard" {
        Ensure-PortAvailable -Port $Port -Purpose "Streamlit dashboard"
        Write-Step "Starting Streamlit dashboard"
        streamlit run src/astock_agent_system/ui/streamlit_app.py --server.port $Port
    }
    "backend" {
        $backendOccupant = Get-PortOccupant -Port $Port
        if (Test-IsProjectBackendProcess -ProcessInfo $backendOccupant) {
            Write-Step "Reusing existing FastAPI backend adapter on port $Port"
            Wait-ForHttpReady -Url "http://127.0.0.1:$Port/api/health" -ServiceName "Backend API" -TimeoutSeconds 30
            break
        }

        Ensure-PortAvailable -Port $Port -Purpose "FastAPI backend adapter"
        Write-Step "Starting FastAPI backend adapter"
        python -m uvicorn apps.backend.app:app --host 127.0.0.1 --port $Port
    }
    "frontend" {
        $frontendDirectory = Join-Path $PSScriptRoot "apps/frontend"
        $frontendOccupant = Get-PortOccupant -Port $Port
        if (Test-IsProjectFrontendProcess -ProcessInfo $frontendOccupant -FrontendDirectory $frontendDirectory) {
            Write-Step "Reusing existing Next.js modern UI on port $Port"
            Wait-ForHttpReady -Url "http://127.0.0.1:$Port" -ServiceName "Frontend UI" -TimeoutSeconds 30
            break
        }

        Ensure-NoExistingNextDevServer -FrontendDirectory $frontendDirectory
        Ensure-PortAvailable -Port $Port -Purpose "Next.js modern UI"
        Write-Step "Starting Next.js modern UI"
        Push-Location $frontendDirectory
        try {
            $desiredBackendUrl = "http://127.0.0.1:$BackendPort"
            if ($env:NEXT_PUBLIC_BACKEND_URL -and $env:NEXT_PUBLIC_BACKEND_URL -ne $desiredBackendUrl) {
                Write-Host "Overriding NEXT_PUBLIC_BACKEND_URL for local modern UI preview: $desiredBackendUrl" -ForegroundColor Yellow
            }
            $env:NEXT_PUBLIC_BACKEND_URL = $desiredBackendUrl
            npx next dev --hostname 127.0.0.1 --port $Port
        }
        finally {
            Pop-Location
        }
    }
    "modern-ui" {
        $frontendDirectory = Join-Path $PSScriptRoot "apps/frontend"
        $backendOccupant = Get-PortOccupant -Port $BackendPort
        $reuseBackend = Test-IsProjectBackendProcess -ProcessInfo $backendOccupant
        $frontendOccupant = Get-PortOccupant -Port $Port
        $reuseFrontend = Test-IsProjectFrontendProcess -ProcessInfo $frontendOccupant -FrontendDirectory $frontendDirectory

        if (-not $reuseFrontend) {
            Ensure-NoExistingNextDevServer -FrontendDirectory $frontendDirectory
        }
        if (-not $reuseBackend) {
            Ensure-PortAvailable -Port $BackendPort -Purpose "FastAPI backend adapter"
        }
        if (-not $reuseFrontend) {
            Ensure-PortAvailable -Port $Port -Purpose "Next.js modern UI"
        }

        $backendScript = Join-Path $PSScriptRoot "start.ps1"
        $backendProcess = $null
        if ($reuseBackend) {
            Write-Step "Reusing existing backend adapter on port $BackendPort"
        }
        else {
            Write-Step "Starting backend sidecar preview in new window"
            $backendProcess = Start-Process powershell -PassThru -ArgumentList @(
                "-NoExit",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "& '$backendScript' -Mode backend -Port $BackendPort"
            )
        }

        Wait-ForHttpReady -Url "http://127.0.0.1:$BackendPort/api/health" -ServiceName "Backend API" -TimeoutSeconds 60

        $frontendProcess = $null
        if ($reuseFrontend) {
            Write-Step "Reusing existing Next.js modern UI on port $Port"
        }
        else {
            Write-Step "Starting Next.js modern UI in new window"
            $frontendProcess = Start-Process powershell -PassThru -ArgumentList @(
                "-NoExit",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "`$env:NEXT_PUBLIC_BACKEND_URL='http://127.0.0.1:$BackendPort'; & '$backendScript' -Mode frontend -Port $Port -BackendPort $BackendPort"
            )
        }

        Wait-ForHttpReady -Url "http://127.0.0.1:$Port" -ServiceName "Frontend UI" -TimeoutSeconds 90

        Write-Step "Modern UI is ready"
        Write-Host "Frontend: http://127.0.0.1:$Port" -ForegroundColor Green
        Write-Host "Backend:  http://127.0.0.1:$BackendPort/api/health" -ForegroundColor Green
        if ($frontendProcess) {
            Write-Host "Frontend window PID: $($frontendProcess.Id)" -ForegroundColor DarkGreen
        }
        if ($backendProcess) {
            Write-Host "Backend window PID:  $($backendProcess.Id)" -ForegroundColor DarkGreen
        }
    }
    "scheduler" {
        Write-Step "Starting long-running scheduler"
        Invoke-AStockCli @("scheduler", "start")
    }
    "docs" {
        if (-not (Get-Command mkdocs -ErrorAction SilentlyContinue)) {
            throw "MkDocs is not installed. Run: python -m pip install -e `".[docs]`""
        }
        Write-Step "Starting documentation preview"
        mkdocs serve
    }
}
