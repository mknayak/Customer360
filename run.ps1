$ErrorActionPreference = "Stop"

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$windowsPython = Join-Path $rootDir ".venv\Scripts\python.exe"
$unixPython = Join-Path $rootDir ".venv/bin/python"
$python = if (Test-Path $windowsPython) { $windowsPython } else { $unixPython }
$hostAddress = if ($env:SERVICE_HOST) { $env:SERVICE_HOST } else { "127.0.0.1" }
$processes = @()

if (-not (Test-Path $python)) {
    throw "Shared Python environment not found: $python. Create it with: python3 -m venv .venv"
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

    Write-Host "Starting simulator on http://$hostAddress`:8080"
    $process = Start-Process -FilePath $python -ArgumentList @($serverFile) -WorkingDirectory $simulatorDir -PassThru
    $script:processes += $process
}

try {
    Start-ServiceProcess -Name "crm" -Module "crm_service.app:app" -Port 8001
    Start-ServiceProcess -Name "product" -Module "product_service.app:app" -Port 8002
    Start-ServiceProcess -Name "shopping" -Module "shopping_service.app:app" -Port 8003
    Start-ServiceProcess -Name "site" -Module "site_service.app:app" -Port 8004
    Start-ServiceProcess -Name "feedback" -Module "feedback_service.app:app" -Port 8005
    Start-ServiceProcess -Name "marketing" -Module "marketing_service.app:app" -Port 8006
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