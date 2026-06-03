param(
    [ValidateSet("status", "storage", "offline", "online", "bench", "dashboard", "scheduler", "docs")]
    [string]$Mode = "status",
    [string]$Models = "",
    [string]$BenchModel = "",
    [int]$MaxCount = 1,
    [int]$Days = 12,
    [int]$Port = 8501,
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
        Write-Step "Starting Streamlit dashboard"
        streamlit run src/astock_agent_system/ui/streamlit_app.py --server.port $Port
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
