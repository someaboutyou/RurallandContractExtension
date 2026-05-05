param(
    [int]$Port = 8080,
    [string]$Workspace = "erlunyanbao",
    [string]$NamespaceUri = "http://erlunyanbao",
    [string]$StoreName = "postgis",
    [string]$DefaultLayer = "DK3213242017",
    [string]$TableName = "DK3213242017",
    [string]$DbHost = "127.0.0.1",
    [int]$DbPort = 15432,
    [string]$DbName = "erlunyanbao",
    [string]$DbUser = "RurallandContractExtension",
    [string]$DbPassword = "RurallandContractExtension",
    [string]$DbSchema = "public",
    [string]$LayerSrs = "EPSG:4527",
    [string]$AdminUser = "admin",
    [string]$AdminPassword = "geoserver",
    [switch]$RequireDefaultLayer,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot "runtime"
$jdkHome = Join-Path $runtimeRoot "windows\jdk"
$geoHome = Join-Path $runtimeRoot "windows\geoserver"
$geoData = Join-Path $runtimeRoot "data\geoserver-data"
$logDir = Join-Path $runtimeRoot "logs"
$javaExe = Join-Path $jdkHome "bin\java.exe"
$startup = Join-Path $geoHome "bin\startup.bat"
$startJar = Join-Path $geoHome "start.jar"
$psql = Join-Path $runtimeRoot "windows\postgresql\bin\psql.exe"

function Read-Choice([string]$Prompt, [string[]]$Allowed, [string]$Default) {
    if ($NonInteractive) {
        return $Default
    }

    while ($true) {
        $answer = Read-Host $Prompt
        if ([string]::IsNullOrWhiteSpace($answer)) {
            $answer = $Default
        }
        if ($Allowed -contains $answer) {
            return $answer
        }
        Write-Host "Please enter: $($Allowed -join '/')"
    }
}

function Get-BasicAuthHeader([string]$User, [string]$Password) {
    $token = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${User}:${Password}"))
    return @{ Authorization = "Basic $token" }
}

function Test-GeoServerEndpoint([string]$Url, [hashtable]$Headers) {
    try {
        Invoke-WebRequest -Uri $Url -Headers $Headers -UseBasicParsing -TimeoutSec 5 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Invoke-GeoServerJson([string]$Url, [hashtable]$Headers, [string]$Method, [object]$Body) {
    $json = $Body | ConvertTo-Json -Depth 10
    Invoke-RestMethod -Uri $Url -Headers $Headers -Method $Method -ContentType "application/json" -Body $json -TimeoutSec 15 | Out-Null
}

function New-ConnectionEntry([string]$Key, [string]$Value) {
    return @{
        "@key" = $Key
        '$' = $Value
    }
}

function ConvertTo-SqlLiteral([string]$Value) {
    return $Value.Replace("'", "''")
}

function Test-PostgisFeatureTable(
    [string]$HostName,
    [int]$Port,
    [string]$Database,
    [string]$User,
    [string]$Password,
    [string]$Schema,
    [string]$Table
) {
    if (-not (Test-Path $psql)) {
        return $false
    }

    $schemaLiteral = ConvertTo-SqlLiteral $Schema
    $tableLiteral = ConvertTo-SqlLiteral $Table
    $sql = @"
SELECT count(*)
FROM information_schema.tables t
JOIN geometry_columns g
  ON g.f_table_schema = t.table_schema
 AND g.f_table_name = t.table_name
WHERE t.table_schema = '$schemaLiteral'
  AND t.table_name = '$tableLiteral'
  AND t.table_type = 'BASE TABLE';
"@
    $previousPassword = $env:PGPASSWORD
    $env:PGPASSWORD = $Password
    try {
        $result = & $psql "-h" $HostName "-p" "$Port" "-U" $User "-d" $Database "-tAc" $sql
        if ($LASTEXITCODE -ne 0) {
            return $false
        }
        return (($result | Out-String).Trim()) -ne "0"
    } finally {
        $env:PGPASSWORD = $previousPassword
    }
}

if (-not (Test-Path $javaExe)) {
    throw "JDK not found: $javaExe. Put portable Windows JDK under runtime\windows\jdk."
}
if (-not (Test-Path $startup) -and -not (Test-Path $startJar)) {
    throw "GeoServer startup file not found. Put GeoServer under runtime\windows\geoserver."
}

New-Item -ItemType Directory -Force -Path $geoData, $logDir | Out-Null
if ((Get-ChildItem -Force $geoData -ErrorAction SilentlyContinue | Measure-Object).Count -eq 0) {
    $sourceData = Join-Path $geoHome "data_dir"
    if (Test-Path $sourceData) {
        Copy-Item -Path (Join-Path $sourceData "*") -Destination $geoData -Recurse -Force
    }
}

$env:JAVA_HOME = $jdkHome
$env:PATH = (Join-Path $jdkHome "bin") + ";" + $env:PATH
$env:GEOSERVER_HOME = $geoHome
$env:GEOSERVER_DATA_DIR = $geoData
$env:GEOSERVER_OPTS = "-DGEOSERVER_DATA_DIR=$geoData -Djetty.port=$Port"

$baseUrl = "http://127.0.0.1:$Port/geoserver"
$webUrl = "$baseUrl/web/"
$restUrl = "$baseUrl/rest"

try {
    Invoke-WebRequest -Uri $webUrl -UseBasicParsing -TimeoutSec 3 | Out-Null
    Write-Host "GeoServer is already running: $baseUrl"
    $started = $true
} catch {
    $started = $false
}

if (-not $started) {
    if (Test-Path $startup) {
        Start-Process -FilePath $startup -WorkingDirectory (Split-Path -Parent $startup) -WindowStyle Hidden
    } else {
        $geoOutLog = Join-Path $logDir "geoserver.out.log"
        $geoErrLog = Join-Path $logDir "geoserver.err.log"
        Start-Process -FilePath $javaExe -ArgumentList @("-DGEOSERVER_DATA_DIR=$geoData", "-Djetty.port=$Port", "-jar", $startJar) -WorkingDirectory $geoHome -RedirectStandardOutput $geoOutLog -RedirectStandardError $geoErrLog -WindowStyle Hidden
    }

    Write-Host "GeoServer starting: $baseUrl"
}

if (-not $started) {
    for ($i = 0; $i -lt 60; $i++) {
        try {
            Invoke-WebRequest -Uri $webUrl -UseBasicParsing -TimeoutSec 3 | Out-Null
            $started = $true
            break
        } catch {
            Start-Sleep -Seconds 2
        }
    }
}

if (-not $started) {
    throw "GeoServer startup timed out. Check runtime\logs or GeoServer console output."
}

$headers = Get-BasicAuthHeader $AdminUser $AdminPassword
$workspaceUrl = "$restUrl/workspaces/$Workspace.json"
$storeUrl = "$restUrl/workspaces/$Workspace/datastores/$StoreName.json"
$featureTypeUrl = "$restUrl/workspaces/$Workspace/datastores/$StoreName/featuretypes/$DefaultLayer.json"
$layerUrl = "$restUrl/layers/${Workspace}:$DefaultLayer.json"

if (-not (Test-GeoServerEndpoint $workspaceUrl $headers)) {
    Write-Host "GeoServer workspace not found: $Workspace"
    try {
        Invoke-GeoServerJson "$restUrl/workspaces" $headers "Post" @{ workspace = @{ name = $Workspace } }
        Write-Host "GeoServer workspace created: $Workspace"
    } catch {
        Write-Host "Failed to create GeoServer workspace automatically: $($_.Exception.Message)"
        if (-not $NonInteractive) {
            $choice = Read-Choice "Open GeoServer admin page so you can create the workspace manually? [Y/n]" @("Y", "y", "N", "n") "Y"
            if ($choice -in @("Y", "y")) {
                Start-Process $webUrl
            }
        }
        throw "Create workspace $Workspace in GeoServer, then rerun this script."
    }
}

$storeBody = @{
    dataStore = @{
        name = $StoreName
        enabled = $true
        type = "PostGIS"
        connectionParameters = @{
            entry = @(
                (New-ConnectionEntry "dbtype" "postgis"),
                (New-ConnectionEntry "host" $DbHost),
                (New-ConnectionEntry "port" "$DbPort"),
                (New-ConnectionEntry "database" $DbName),
                (New-ConnectionEntry "schema" $DbSchema),
                (New-ConnectionEntry "namespace" $NamespaceUri),
                (New-ConnectionEntry "user" $DbUser),
                (New-ConnectionEntry "passwd" $DbPassword),
                (New-ConnectionEntry "Expose primary keys" "true"),
                (New-ConnectionEntry "validate connections" "true")
            )
        }
    }
}

if (-not (Test-GeoServerEndpoint $storeUrl $headers)) {
    Write-Host "GeoServer PostGIS store not found: $Workspace/$StoreName"
    try {
        Invoke-GeoServerJson "$restUrl/workspaces/$Workspace/datastores" $headers "Post" $storeBody
        Write-Host "GeoServer PostGIS store created: $Workspace/$StoreName -> ${DbHost}:$DbPort/$DbName"
    } catch {
        throw "Failed to create GeoServer PostGIS store $Workspace/$StoreName. $($_.Exception.Message)"
    }
} else {
    try {
        Invoke-GeoServerJson $storeUrl $headers "Put" $storeBody
        Write-Host "GeoServer PostGIS store updated: $Workspace/$StoreName -> ${DbHost}:$DbPort/$DbName"
    } catch {
        throw "Failed to update GeoServer PostGIS store $Workspace/$StoreName. $($_.Exception.Message)"
    }
}

if (-not (Test-PostgisFeatureTable $DbHost $DbPort $DbName $DbUser $DbPassword $DbSchema $TableName)) {
    $message = "PostGIS feature table was not found or has no geometry column: $DbSchema.$TableName. Add its DDL to scripts\sql\init-postgis-schema.sql, rerun init, then publish ${Workspace}:$DefaultLayer."
    if ($RequireDefaultLayer) {
        throw $message
    }
    Write-Host $message
    Write-Host "GeoServer layer publishing skipped; backend startup will continue."
    Write-Host "GeoServer ready: $baseUrl"
    return
}

if (-not (Test-GeoServerEndpoint $featureTypeUrl $headers)) {
    Write-Host "GeoServer feature type not found: $Workspace/$StoreName/$DefaultLayer"
    $featureBody = @{
        featureType = @{
            name = $DefaultLayer
            nativeName = $TableName
            title = $DefaultLayer
            srs = $LayerSrs
            projectionPolicy = "FORCE_DECLARED"
            enabled = $true
        }
    }
    try {
        Invoke-GeoServerJson "$restUrl/workspaces/$Workspace/datastores/$StoreName/featuretypes" $headers "Post" $featureBody
        Write-Host "GeoServer feature type published: ${Workspace}:$DefaultLayer from table $DbSchema.$TableName"
    } catch {
        throw "Failed to publish GeoServer layer ${Workspace}:$DefaultLayer from table $DbSchema.$TableName. Ensure the PostGIS table exists and has a geometry column. $($_.Exception.Message)"
    }
}

if (-not (Test-GeoServerEndpoint $layerUrl $headers)) {
    $message = "GeoServer feature type was created, but layer endpoint is still unavailable: ${Workspace}:$DefaultLayer"
    if ($RequireDefaultLayer) {
        throw $message
    }
    Write-Host $message
} else {
    Write-Host "GeoServer default layer exists: ${Workspace}:$DefaultLayer"
}

Write-Host "GeoServer ready: $baseUrl"
