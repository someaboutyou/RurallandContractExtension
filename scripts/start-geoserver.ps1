param(
    [int]$Port = 8080,
    [string]$Workspace = "erlunyanbao",
    [string]$NamespaceUri = "http://erlunyanbao",
    [string]$StoreName = "postgis",
    [string]$DefaultLayer = "survey_dk_result",
    [string]$TableName = "survey_dk_result",
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
$stylesDir = Join-Path $projectRoot "datas\geoserver-styles"

$layerDefs = @(
    @{ Name = "survey_dk_result"; Table = "survey_dk_result"; Title = "承包地块"; Srs = "EPSG:4527"; Style = "survey_dk_result"; HasJsonGeom = $false; Visible = $true; Order = 10 },
    @{ Name = "czkfbj";          Table = "czkfbj";          Title = "村庄开发边界";       Srs = "EPSG:4527"; Style = "czkfbj";          HasJsonGeom = $false; GeomCol = "Shape";  Visible = $false; Order = 20 },
    @{ Name = "dltb";            Table = "dltb";            Title = "地类图斑";           Srs = "EPSG:4527"; Style = "dltb";            HasJsonGeom = $false; GeomCol = "Shape";  Visible = $false; Order = 30 },
    @{ Name = "gdbhmb";          Table = "gdbhmb";          Title = "耕地保护目标";       Srs = "EPSG:4527"; Style = "gdbhmb";          HasJsonGeom = $false; GeomCol = "Shape";  Visible = $false; Order = 40 },
    @{ Name = "stbhhx";          Table = "stbhhx";          Title = "生态保护红线";       Srs = "EPSG:4490"; Style = "stbhhx";          HasJsonGeom = $false; GeomCol = "Shape";  Visible = $false; Order = 50 },
    @{ Name = "xzq";             Table = "xzq";             Title = "行政区";             Srs = "EPSG:4527"; Style = "xzq";             HasJsonGeom = $false; GeomCol = "SHAPE";  Visible = $false; Order = 60 },
    @{ Name = "xzqjx";           Table = "xzqjx";           Title = "行政区界线";         Srs = "EPSG:4527"; Style = "xzqjx";           HasJsonGeom = $false; GeomCol = "SHAPE";  Visible = $false; Order = 70 },
    @{ Name = "yjjbntbhtb";      Table = "yjjbntbhtb";      Title = "永久基本农田保护图斑"; Srs = "EPSG:4527"; Style = "yjjbntbhtb";      HasJsonGeom = $false; GeomCol = "Shape";  Visible = $false; Order = 80 }
)

$layerGroupName = "rural_land_layers"
$layerGroupTitle = "农村承包经营权调查图层组"
$runtimeRoot = Join-Path $projectRoot "runtime"
$jdkHome = Join-Path $runtimeRoot "windows\jdk"
$geoHome = Join-Path $runtimeRoot "windows\geoserver"
$geoData = Join-Path $runtimeRoot "data\geoserver-data"
$logDir = Join-Path $runtimeRoot "logs"
$runtimeEnvFile = Join-Path $runtimeRoot ".state\runtime.env"
$javaExe = Join-Path $jdkHome "bin\java.exe"
$startup = Join-Path $geoHome "bin\startup.bat"
$startJar = Join-Path $geoHome "start.jar"
$psql = Join-Path $runtimeRoot "windows\postgresql\bin\psql.exe"

function Read-RuntimeEnv([string]$Path) {
    $values = @{}
    if (-not (Test-Path $Path)) {
        return $values
    }
    foreach ($line in Get-Content $Path -Encoding UTF8) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith("#")) {
            continue
        }
        $parts = $line -split "=", 2
        if ($parts.Count -eq 2) {
            $values[$parts[0]] = $parts[1]
        }
    }
    return $values
}

$runtimeEnv = Read-RuntimeEnv $runtimeEnvFile
if ($runtimeEnv.ContainsKey("DATABASE_HOST") -and $DbHost -eq "127.0.0.1") { $DbHost = $runtimeEnv["DATABASE_HOST"] }
if ($runtimeEnv.ContainsKey("DATABASE_PORT") -and $DbPort -eq 15432) { $DbPort = [int]$runtimeEnv["DATABASE_PORT"] }
if ($runtimeEnv.ContainsKey("DATABASE_NAME") -and $DbName -eq "erlunyanbao") { $DbName = $runtimeEnv["DATABASE_NAME"] }
if ($runtimeEnv.ContainsKey("DATABASE_USER") -and $DbUser -eq "RurallandContractExtension") { $DbUser = $runtimeEnv["DATABASE_USER"] }
if ($runtimeEnv.ContainsKey("DATABASE_PASSWORD") -and $DbPassword -eq "RurallandContractExtension") { $DbPassword = $runtimeEnv["DATABASE_PASSWORD"] }
if ($runtimeEnv.ContainsKey("GEOSERVER_PORT") -and $Port -eq 8080) { $Port = [int]$runtimeEnv["GEOSERVER_PORT"] }

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
    $bodyBytes = [Text.Encoding]::UTF8.GetBytes($json)
    Invoke-RestMethod -Uri $Url -Headers $Headers -Method $Method -ContentType "application/json; charset=utf-8" -Body $bodyBytes -TimeoutSec 15 | Out-Null
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

function Invoke-PsqlScalar(
    [string]$HostName,
    [int]$Port,
    [string]$Database,
    [string]$User,
    [string]$Password,
    [string]$Sql
) {
    $previousPassword = $env:PGPASSWORD
    $env:PGPASSWORD = $Password
    try {
        $result = & $psql "-h" $HostName "-p" "$Port" "-U" $User "-d" $Database "-tAc" $Sql
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        return (($result | Out-String).Trim())
    } finally {
        $env:PGPASSWORD = $previousPassword
    }
}

function Get-EpsgCode([string]$Srs) {
    if ($Srs -match "EPSG:(\d+)") {
        return $Matches[1]
    }
    return "4326"
}

function Resolve-PostgisPublishTable(
    [string]$HostName,
    [int]$Port,
    [string]$Database,
    [string]$User,
    [string]$Password,
    [string]$Schema,
    [string]$Table,
    [string]$Srs
) {
    return $Table
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
  AND t.table_type IN ('BASE TABLE', 'VIEW');
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

function Recalculate-GeoServerFeatureTypeBounds(
    [string]$LayerName,
    [hashtable]$Headers
) {
    $recalculateUrl = "$restUrl/workspaces/$Workspace/datastores/$StoreName/featuretypes/$LayerName.json?recalculate=nativebbox,latlonbbox"
    try {
        Invoke-GeoServerJson $recalculateUrl $Headers "Put" @{ featureType = @{ name = $LayerName } }
        Write-Host "  Feature type bounds recalculated: $($Workspace):$LayerName"
    } catch {
        Write-Host "  Feature type bounds recalculation failed: $($Workspace):$LayerName - $($_.Exception.Message)"
    }
}

function Publish-GeoServerStyle(
    [string]$StyleName,
    [string]$SldPath,
    [hashtable]$Headers
) {
    if (-not (Test-Path $SldPath)) {
        Write-Host "  SLD file not found: $SldPath — style '$StyleName' skipped"
        return
    }
    $sldContent = Get-Content -Path $SldPath -Raw -Encoding UTF8
    $createStyleUrl = "$restUrl/workspaces/$Workspace/styles?name=$StyleName"
    $updateStyleUrl = "$restUrl/workspaces/$Workspace/styles/$StyleName"
    $checkUrl = "$restUrl/workspaces/$Workspace/styles/$StyleName.json"
    if (Test-GeoServerEndpoint $checkUrl $Headers) {
        try {
            Invoke-RestMethod -Uri $updateStyleUrl -Headers $Headers -Method Put -ContentType "application/vnd.ogc.sld+xml" -Body $sldContent -TimeoutSec 15 | Out-Null
            Write-Host "  Style updated: $StyleName"
        } catch {
            Write-Host "  Style update failed: $StyleName — $($_.Exception.Message)"
        }
    } else {
        try {
            Invoke-RestMethod -Uri $createStyleUrl -Headers $Headers -Method Post -ContentType "application/vnd.ogc.sld+xml" -Body $sldContent -TimeoutSec 15 | Out-Null
            Write-Host "  Style created: $StyleName"
        } catch {
            Write-Host "  Style creation failed: $StyleName — $($_.Exception.Message)"
        }
    }
}

function Publish-GeoServerFeatureType(
    [hashtable]$LayerDef,
    [hashtable]$Headers
) {
    $layerName = $LayerDef.Name
    $tableName = $LayerDef.Table
    $publishTableName = $tableName
    if ($LayerDef.HasJsonGeom) {
        $publishTableName = Resolve-PostgisPublishTable $DbHost $DbPort $DbName $DbUser $DbPassword $DbSchema $tableName $LayerDef.Srs
    }
    if (-not (Test-PostgisFeatureTable $DbHost $DbPort $DbName $DbUser $DbPassword $DbSchema $publishTableName)) {
        Write-Host "  PostGIS table skipped (no geometry): $DbSchema.$tableName"
        return $false
    }
    $featureTypeUrl = "$restUrl/workspaces/$Workspace/datastores/$StoreName/featuretypes/$layerName.json"
    if (Test-GeoServerEndpoint $featureTypeUrl $headers) {
        Write-Host "  Feature type exists: $($Workspace):$($layerName)"
        try {
            $updateBody = @{
                featureType = @{
                    nativeName = $publishTableName
                    title = $LayerDef.Title
                    srs = $LayerDef.Srs
                    projectionPolicy = "FORCE_DECLARED"
                    enabled = $true
                }
            }
            Invoke-GeoServerJson $featureTypeUrl $Headers "Put" $updateBody
            Write-Host "  Feature type updated: $($LayerDef.Title) -> $publishTableName"
        } catch {
            Write-Host "  Feature type update failed: $($Workspace):$($layerName) - $($_.Exception.Message)"
        }
    } else {
        $featureBody = @{
            featureType = @{
                name = $layerName
                nativeName = $publishTableName
                title = $LayerDef.Title
                srs = $LayerDef.Srs
                projectionPolicy = "FORCE_DECLARED"
                enabled = $true
            }
        }
        try {
            $createUrl = "$restUrl/workspaces/$Workspace/datastores/$StoreName/featuretypes"
            if ($LayerDef.ContainsKey("GeomCol")) {
                $createUrl += "?configure=all"
            }
            Invoke-GeoServerJson $createUrl $Headers "Post" $featureBody
            Write-Host "  Feature type published: $($Workspace):$($layerName)"
        } catch {
            # Retry with native CRS for non-standard projection
            if ($LayerDef.Srs -ne "EPSG:4527") {
                try {
                    $nativeFeatureBody = @{
                        featureType = @{
                            name = $layerName
                            nativeName = $publishTableName
                            title = $LayerDef.Title
                            srs = $LayerDef.Srs
                            nativeCRS = $LayerDef.Srs
                            projectionPolicy = "REPROJECT_TO_DECLARED"
                            enabled = $true
                        }
                    }
                    Invoke-GeoServerJson $createUrl $Headers "Post" $nativeFeatureBody
                    Write-Host "  Feature type published (native CRS): $($Workspace):$($layerName)"
                } catch {
                    Write-Host "  Feature type publish failed: $($Workspace):$($layerName) - $($_.Exception.Message)"
                    return $false
                }
            } else {
                Write-Host "  Feature type publish failed: $($Workspace):$($layerName) - $($_.Exception.Message)"
                return $false
            }
        }
    }
    Recalculate-GeoServerFeatureTypeBounds -LayerName $layerName -Headers $Headers
    # Assign default style
    $styleName = $LayerDef.Style
    $layerUrl = "$restUrl/layers/$($Workspace):$($layerName).json"
    if (Test-GeoServerEndpoint $layerUrl $Headers) {
        try {
            $styleBody = @{ layer = @{ defaultStyle = @{ name = $styleName } } }
            Invoke-GeoServerJson $layerUrl $Headers "Put" $styleBody
            Write-Host "  Default style set: $styleName"
        } catch {
            Write-Host "  Style assignment failed for $($Workspace):$($layerName): $($_.Exception.Message)"
        }
    }
    return $true
}

function Publish-GeoServerLayerGroup(
    [string]$GroupName,
    [string]$GroupTitle,
    [hashtable]$Headers,
    [array]$PublishedLayerNames
) {
    if ($PublishedLayerNames.Count -eq 0) {
        Write-Host "No layers to add to layer group — layer group creation skipped."
        return
    }
    $groupUrl = "$restUrl/workspaces/$Workspace/layergroups/$GroupName.json"
    $publishedItems = @()
    foreach ($name in $PublishedLayerNames) {
        $publishedItems += @{
            "@type" = "layer"
            name = "${Workspace}:$name"
        }
    }
    $groupBody = @{
        layerGroup = @{
            name = $GroupName
            mode = "SINGLE"
            title = $GroupTitle
            publishables = @{
                published = $publishedItems
            }
        }
    }
    if (Test-GeoServerEndpoint $groupUrl $Headers) {
        try {
            Invoke-GeoServerJson $groupUrl $Headers "Put" $groupBody
            Write-Host "Layer group updated: $GroupName ($($PublishedLayerNames.Count) layers)"
        } catch {
            Write-Host "Layer group update failed: $GroupName — $($_.Exception.Message)"
        }
    } else {
        try {
            Invoke-GeoServerJson "$restUrl/workspaces/$Workspace/layergroups" $Headers "Post" $groupBody
            Write-Host "Layer group created: $GroupName ($($PublishedLayerNames.Count) layers, SINGLE mode)"
        } catch {
            Write-Host "Layer group creation failed: $GroupName — $($_.Exception.Message)"
            Write-Host "  You can create it manually in GeoServer admin: Layer Groups → Add new"
        }
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

# ── Workspace ──
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

# ── PostGIS Store ──
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

# ── Upload SLD Styles ──
Write-Host "Uploading SLD styles..."
foreach ($layerDef in $layerDefs) {
    $sldPath = Join-Path $stylesDir "$($layerDef.Style).sld"
    Publish-GeoServerStyle -StyleName $layerDef.Style -SldPath $sldPath -Headers $headers
}

# ── Publish Feature Types (Layers) ──
Write-Host "Publishing GeoServer layers..."
$publishedLayerNames = @()
$hasDefaultLayer = $false
foreach ($layerDef in $layerDefs) {
    Write-Host "Layer: ${Workspace}:$($layerDef.Name)"
    $success = Publish-GeoServerFeatureType -LayerDef $layerDef -Headers $headers
    if ($success) {
        $publishedLayerNames += $layerDef.Name
        if ($layerDef.Name -eq $DefaultLayer) {
            $hasDefaultLayer = $true
        }
    }
}

if ($publishedLayerNames.Count -eq 0) {
    $msg = "No spatial layers were found in the database. Ensure at least survey_dk_result has a PostGIS geometry column."
    if ($RequireDefaultLayer) { throw $msg }
    Write-Host $msg
    Write-Host "GeoServer ready: $baseUrl"
    return
}

# ── Layer Group ──
Write-Host "Creating layer group..."
Publish-GeoServerLayerGroup -GroupName $layerGroupName -GroupTitle $layerGroupTitle -Headers $headers -PublishedLayerNames $publishedLayerNames

# ── Summary ──
Write-Host ""
Write-Host "GeoServer layer summary:"
foreach ($name in $publishedLayerNames) {
    Write-Host "  ✓ ${Workspace}:$name"
}
Write-Host "  Layer group: ${Workspace}:$layerGroupName (SINGLE mode)"
Write-Host "GeoServer ready: $baseUrl"
