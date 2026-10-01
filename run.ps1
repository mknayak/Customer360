$ErrorActionPreference = "Stop"

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $rootDir ".env"
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            $name = $Matches[1]
            $value = $Matches[2]
            if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

$windowsPython = Join-Path $rootDir ".venv\Scripts\python.exe"
$unixPython = Join-Path $rootDir ".venv/bin/python"
$python = if (Test-Path $windowsPython) { $windowsPython } else { $unixPython }
$hostAddress = if ($env:SERVICE_HOST) { $env:SERVICE_HOST } else { "127.0.0.1" }
$crmPort = if ($env:CRM_PORT) { [int]$env:CRM_PORT } else { 8001 }
$productPort = if ($env:PRODUCT_PORT) { [int]$env:PRODUCT_PORT } else { 8002 }
$shoppingPort = if ($env:SHOPPING_PORT) { [int]$env:SHOPPING_PORT } else { 8003 }
$sitePort = if ($env:SITE_PORT) { [int]$env:SITE_PORT } else { 8004 }
$feedbackPort = if ($env:FEEDBACK_PORT) { [int]$env:FEEDBACK_PORT } else { 8005 }
$marketingPort = if ($env:MARKETING_PORT) { [int]$env:MARKETING_PORT } else { 8006 }
$eventsPort = if ($env:EVENTS_PORT) { [int]$env:EVENTS_PORT } else { 8007 }
$orchestrationPort = if ($env:ORCHESTRATION_PORT) { [int]$env:ORCHESTRATION_PORT } else { 8008 }
$agentAppPort = if ($env:AGENT_APP_PORT) { [int]$env:AGENT_APP_PORT } else { 8009 }
$dataPlatformPort = if ($env:DATA_PLATFORM_PORT) { [int]$env:DATA_PLATFORM_PORT } else { 8010 }
$simulatorPort = if ($env:SIMULATOR_PORT) { [int]$env:SIMULATOR_PORT } else { 8080 }
$env:EVENT_SERVICE_URL = if ($env:EVENT_SERVICE_URL) { $env:EVENT_SERVICE_URL } else { "http://${hostAddress}:$eventsPort" }
$env:SIMULATOR_PORT = "$simulatorPort"
$env:PYTHONUNBUFFERED = "1"
$processes = @()
$services = @(
    @{ Name = "crm"; Module = "crm_service.app:app"; Port = $crmPort },
    @{ Name = "product"; Module = "product_service.app:app"; Port = $productPort },
    @{ Name = "shopping"; Module = "shopping_service.app:app"; Port = $shoppingPort },
    @{ Name = "site"; Module = "site_service.app:app"; Port = $sitePort },
    @{ Name = "feedback"; Module = "feedback_service.app:app"; Port = $feedbackPort },
    @{ Name = "marketing"; Module = "marketing_service.app:app"; Port = $marketingPort },
    @{ Name = "events"; Module = "event_service.app:app"; Port = $eventsPort },
    @{ Name = "orchestration"; Module = "orchestration_service.app:app"; Port = $orchestrationPort }
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

    Stop-PortProcess -Port $simulatorPort
    Write-Host "Starting simulator on http://$hostAddress`:$simulatorPort"
    $process = Start-Process -FilePath $python -ArgumentList @($serverFile) -WorkingDirectory $simulatorDir -PassThru
    $script:processes += $process
}

function Start-AgentAppProcess {
    Stop-PortProcess -Port $agentAppPort
    Write-Host "Starting agent app on http://$hostAddress`:$agentAppPort"
    $arguments = @(
        "-m", "uvicorn", "Agent.app.main:app",
        "--app-dir", $rootDir,
        "--host", $hostAddress,
        "--port", $agentAppPort
    )
    $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $rootDir -PassThru
    $script:processes += $process
}

function Start-DataPlatformProcess {
    $dataPlatformDir = Join-Path $rootDir "Enterprise/DataPlatform"
    Stop-PortProcess -Port $dataPlatformPort
    Write-Host "Starting data platform on http://$hostAddress`:$dataPlatformPort"
    $arguments = @(
        "-m", "uvicorn", "data_platform.app:app",
        "--app-dir", $dataPlatformDir,
        "--host", $hostAddress,
        "--port", $dataPlatformPort
    )
    $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $dataPlatformDir -PassThru
    $script:processes += $process
}

try {
    foreach ($service in $services) {
        Start-ServiceProcess -Name $service.Name -Module $service.Module -Port $service.Port
    }
    Start-SimulatorProcess
    Start-AgentAppProcess
    Start-DataPlatformProcess

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