$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$geoHome = Join-Path $projectRoot "runtime\windows\geoserver"
$jdkHome = Join-Path $projectRoot "runtime\windows\jdk"
$geoData = Join-Path $projectRoot "runtime\data\geoserver-data"
$shutdown = Join-Path $geoHome "bin\shutdown.bat"

if (Test-Path $shutdown) {
    try {
        $env:GEOSERVER_HOME = $geoHome
        $env:GEOSERVER_DATA_DIR = $geoData
        $env:JAVA_HOME = $jdkHome
        $env:PATH = (Join-Path $jdkHome "bin") + ";" + $env:PATH
        & $shutdown
        exit 0
    } catch {
        Write-Host "GeoServer shutdown.bat failed: $($_.Exception.Message)"
    }
}

Write-Host "GeoServer shutdown.bat was not found. If GeoServer was started with start.jar, stop the related java process manually."
