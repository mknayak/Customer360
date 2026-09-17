$ErrorActionPreference = "Stop"

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$windowsPython = Join-Path $rootDir ".venv\Scripts\python.exe"
$unixPython = Join-Path $rootDir ".venv/bin/python"
$python = if (Test-Path $windowsPython) { $windowsPython } else { $unixPython }
$hostAddress = if ($env:SERVICE_HOST) { $env:SERVICE_HOST } else { "127.0.0.1" }
$processes = @()
$services = @(
    @{ Name = "crm"; Module = "crm_service.app:app"; Port = 8001 },
    @{ Name = "product"; Module = "product_service.app:app"; Port = 8002 },
    @{ Name = "shopping"; Module = "shopping_service.app:app"; Port = 8003 },
    @{ Name = "site"; Module = "site_service.app:app"; Port = 8004 },
    @{ Name = "feedback"; Module = "feedback_service.app:app"; Port = 8005 },
    @{ Name = "marketing"; Module = "marketing_service.app:app"; Port = 8006 }
)

if (-not (Test-Path $python)) {
    throw "Shared Python environment not found: $python. Create it with: python3 -m venv .venv"
}

function Stop-PortProcess {
    param([int]$Port)

    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        foreach ($listener in $listeners) {
            $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
            if ($process) {
                Write-Host "Force-stopping process using port $Port`: $($process.Id)"
                Stop-Process -Id $process.Id -Force
            }
        }
        return
    }

    if (Get-Command lsof -ErrorAction SilentlyContinue) {
        $pids = & lsof -tiTCP:$Port -sTCP:LISTEN 2>$null
        foreach ($processId in $pids) {
            if ($processId) {
                Write-Host "Force-stopping process using port $Port`: $processId"
                Stop-Process -Id ([int]$processId) -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

function Start-ServiceProcess {
    param(
        [string]$Name,
        [string]$Module,
        [int]$Port
    )

    $serviceDir = Join-Path $rootDir "Enterprise/Services/$Name"
    $moduleName = $Module.Split(':')[0]
    $appFile = Join-Path $serviceDir (($moduleName -replace '\.', '/') + ".py")

    if (-not (Test-Path $appFile)) {
        Write-Warning "Skipping $Name`: $appFile does not exist yet"
        return
    }

    Stop-PortProcess -Port $Port
    Write-Host "Starting $Name on http://$hostAddress`:$Port"
    $arguments = @(
        "-m", "uvicorn", $Module,
        "--app-dir", $serviceDir,
        "--host", $hostAddress,
        "--port", $Port
    )
    $process = Start-Process -FilePath $python -ArgumentList $arguments -PassThru
    $script:processes += $process
}

function Start-SimulatorProcess {
    $simulatorDir = Join-Path $rootDir "Enterprise/Simulator"
    $serverFile = Join-Path $simulatorDir "server.py"

    if (-not (Test-Path $serverFile)) {
        Write-Warning "Skipping simulator`: $serverFile does not exist yet"
        return
    }

    Stop-PortProcess -Port 8080
    Write-Host "Starting simulator on http://$hostAddress`:8080"
    $process = Start-Process -FilePath $python -ArgumentList @($serverFile) -WorkingDirectory $simulatorDir -PassThru
    $script:processes += $process
}

try {
    foreach ($service in $services) {
        Start-ServiceProcess -Name $service.Name -Module $service.Module -Port $service.Port
    }
    Start-SimulatorProcess

    if ($processes.Count -eq 0) {
        throw "No implemented services were found."
    }

    Write-Host "Services are running. Press Ctrl+C to stop them."
    while ($true) {
        foreach ($process in $processes) {
            $process.Refresh()
            if ($process.HasExited) {
                throw "Service process $($process.Id) stopped unexpectedly."
            }
        }
        Start-Sleep -Seconds 1
    }
}
finally {
    foreach ($process in $processes) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
        }
        $process.Dispose()
    }
}