[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet("hml", "prod")]
    [string]$Environment,
    [string]$ConfirmProdPublish = "",
    [string]$RepoRoot,
    [string]$Destination,
    [string]$BackupRoot = "C:\srv\controle-treinamentos\frontend-backup",
    [string]$EnvFile,
    [string]$BuildDir = "",
    [switch]$SkipBuild,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

$HmlDestination = "C:\srv\controle-treinamentos\frontend\hml"
$ProdDestination = "C:\srv\controle-treinamentos\frontend\prod"
$HmlEnvFile = "C:\srv\controle-treinamentos\env\hml.env"
$ProdEnvFile = "C:\srv\controle-treinamentos\env\prod.env"

function Resolve-RepoRoot {
    param([string]$ExplicitRoot)
    if ($ExplicitRoot) {
        return (Resolve-Path -LiteralPath $ExplicitRoot).Path
    }
    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Assert-SafePath {
    param(
        [string]$Path,
        [string]$Purpose
    )

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetPathRoot($fullPath)
    if ($fullPath.TrimEnd("\") -eq $root.TrimEnd("\")) {
        throw "$Purpose nao pode apontar para a raiz do drive: $fullPath"
    }
    return $fullPath
}

function Test-IsPath {
    param(
        [string]$Actual,
        [string]$Expected
    )

    $actualPath = [System.IO.Path]::GetFullPath($Actual).TrimEnd("\")
    $expectedPath = [System.IO.Path]::GetFullPath($Expected).TrimEnd("\")
    return $actualPath.Equals($expectedPath, [System.StringComparison]::OrdinalIgnoreCase)
}

function Test-IsProductionDestination {
    param([string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
    $normalized = $fullPath.Replace("/", "\")
    return (
        $normalized.Equals($ProdDestination, [System.StringComparison]::OrdinalIgnoreCase) -or
        $normalized -like "*\frontend\prod" -or
        $normalized -like "*\frontend\prod\*"
    )
}

function Resolve-PublishConfiguration {
    param(
        [string]$RequestedEnvironment,
        [string]$RequestedDestination,
        [string]$RequestedEnvFile,
        [string]$RequestedConfirmProdPublish
    )

    if (-not $RequestedEnvironment) {
        throw "Environment ausente. Informe -Environment hml ou -Environment prod."
    }

    if ($RequestedEnvironment -eq "hml") {
        $effectiveDestination = if ($RequestedDestination) { $RequestedDestination } else { $HmlDestination }
        $effectiveEnvFile = if ($RequestedEnvFile) { $RequestedEnvFile } else { $HmlEnvFile }

        if (Test-IsProductionDestination -Path $effectiveDestination) {
            throw "Environment=hml nao pode publicar em destino de producao: $effectiveDestination"
        }
        if (-not (Test-IsPath -Actual $effectiveDestination -Expected $HmlDestination)) {
            throw "Destination incompativel com Environment=hml. Use $HmlDestination."
        }
        if (Test-IsPath -Actual $effectiveEnvFile -Expected $ProdEnvFile) {
            throw "EnvFile incompativel: Environment=hml nao pode usar prod.env."
        }
        if (-not (Test-IsPath -Actual $effectiveEnvFile -Expected $HmlEnvFile)) {
            throw "EnvFile incompativel com Environment=hml. Use $HmlEnvFile."
        }
    } elseif ($RequestedEnvironment -eq "prod") {
        $effectiveDestination = if ($RequestedDestination) { $RequestedDestination } else { $ProdDestination }
        $effectiveEnvFile = if ($RequestedEnvFile) { $RequestedEnvFile } else { $ProdEnvFile }

        if ($RequestedConfirmProdPublish -ne "publish-prod") {
            throw 'Environment=prod exige -ConfirmProdPublish "publish-prod".'
        }
        if (-not (Test-IsPath -Actual $effectiveDestination -Expected $ProdDestination)) {
            throw "Destination incompativel com Environment=prod. Use $ProdDestination."
        }
        if (Test-IsPath -Actual $effectiveEnvFile -Expected $HmlEnvFile) {
            throw "EnvFile incompativel: Environment=prod nao pode usar hml.env."
        }
        if (-not (Test-IsPath -Actual $effectiveEnvFile -Expected $ProdEnvFile)) {
            throw "EnvFile incompativel com Environment=prod. Use $ProdEnvFile."
        }
    } else {
        throw "Environment invalido. Use hml ou prod."
    }

    return [pscustomobject]@{
        Environment = $RequestedEnvironment
        Destination = [System.IO.Path]::GetFullPath($effectiveDestination)
        EnvFile     = [System.IO.Path]::GetFullPath($effectiveEnvFile)
    }
}

function Invoke-RobocopyChecked {
    param(
        [string]$Source,
        [string]$Target,
        [string[]]$ExtraArgs
    )

    $args = @($Source, $Target) + $ExtraArgs
    & robocopy @args | Out-Null
    $exitCode = $LASTEXITCODE
    if ($exitCode -gt 7) {
        throw "Robocopy falhou com exit code $exitCode"
    }
    return $exitCode
}

function Get-JsonPropertyValue {
    param(
        [object]$Object,
        [string]$Name
    )

    if (-not $Object) {
        return $null
    }

    $property = $Object.PSObject.Properties[$Name]
    if (-not $property) {
        return $null
    }
    return $property.Value
}

function Test-FingerprintedAssetPath {
    param(
        [string]$AssetPath,
        [string]$ExpectedExtension
    )

    if (-not $AssetPath) {
        return $false
    }

    $normalized = $AssetPath -replace "\\", "/"
    return $normalized -match "\.[0-9]{8}-[0-9]{6}\.[0-9a-f]{12}\.$ExpectedExtension$"
}

function Assert-NoQueryVersioning {
    param([string]$Root)

    $violations = New-Object System.Collections.Generic.List[string]
    Get-ChildItem -LiteralPath $Root -Recurse -File | Where-Object { $_.Extension.ToLowerInvariant() -in @(".html", ".js", ".css") } | ForEach-Object {
        $content = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8
        if ($content -match "\?v=") {
            [void]$violations.Add($_.FullName)
        }
    }

    if ($violations.Count -gt 0) {
        $joined = ($violations | Sort-Object) -join ", "
        throw "Build ainda usa query string de versionamento (?v=): $joined"
    }
}

function Get-FrontendRelativePath {
    param(
        [string]$Root,
        [string]$FullName
    )

    $rootPath = [System.IO.Path]::GetFullPath($Root).TrimEnd("\") + "\"
    $filePath = [System.IO.Path]::GetFullPath($FullName)
    if (-not $filePath.StartsWith($rootPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Arquivo fora da arvore frontend validada: $filePath"
    }
    return $filePath.Substring($rootPath.Length).Replace("\", "/")
}

function Normalize-FrontendReference {
    param(
        [string]$Reference,
        [string]$BasePath = "index.html"
    )

    $cleanReference = ((([string]$Reference) -split "\?", 2)[0] -split "#", 2)[0].Trim()
    if (-not $cleanReference) {
        return ""
    }
    if ($cleanReference -match "^(?:https?:|data:|#)") {
        return ""
    }

    $normalizedBase = $BasePath.Replace("\", "/")
    $rawBaseDir = [System.IO.Path]::GetDirectoryName($normalizedBase)
    $baseDir = if ($rawBaseDir) { $rawBaseDir.Replace("\", "/") } else { "" }
    if ($cleanReference.StartsWith("/")) {
        return $cleanReference.TrimStart("/")
    }
    $joined = if ($baseDir) { "$baseDir/$cleanReference" } else { $cleanReference }
    $segments = New-Object System.Collections.Generic.List[string]
    foreach ($segment in $joined.Replace("\", "/").Split("/")) {
        if (-not $segment -or $segment -eq ".") {
            continue
        }
        if ($segment -eq "..") {
            if ($segments.Count -gt 0) {
                $segments.RemoveAt($segments.Count - 1)
            }
            continue
        }
        [void]$segments.Add($segment)
    }
    return ($segments -join "/")
}

function Assert-NoOrphanFrontendAssets {
    param(
        [string]$Root,
        [object]$Manifest
    )

    $assetsObject = $Manifest.fingerprinted_assets
    if (-not $assetsObject) {
        throw "Manifest sem fingerprinted_assets para validacao anti-stale."
    }

    $allowedAssets = @{}
    foreach ($property in @($assetsObject.PSObject.Properties)) {
        $value = ([string]$property.Value).Replace("\", "/")
        if ($value) {
            $allowedAssets[$value] = $true
        }
    }

    $orphanAssets = New-Object System.Collections.Generic.List[string]
    Get-ChildItem -LiteralPath $Root -Recurse -File | Where-Object { $_.Extension.ToLowerInvariant() -in @(".js", ".css") } | ForEach-Object {
        $relativePath = Get-FrontendRelativePath -Root $Root -FullName $_.FullName
        if (-not $allowedAssets.ContainsKey($relativePath)) {
            [void]$orphanAssets.Add($relativePath)
        }
    }

    if ($orphanAssets.Count -gt 0) {
        $joined = ($orphanAssets | Sort-Object) -join ", "
        throw "Build contem JS/CSS fora do asset-manifest.json; possivel mistura stale de grafo: $joined"
    }
}

function Assert-IndexReferencesManifestGraph {
    param(
        [string]$Root,
        [object]$Manifest
    )

    $entrypoints = $Manifest.entrypoints
    $entryAppJs = Get-JsonPropertyValue -Object $entrypoints -Name "app.js"
    $entryAppCss = Get-JsonPropertyValue -Object $entrypoints -Name "app.css"
    $entryConfigJs = Get-JsonPropertyValue -Object $entrypoints -Name "config.js"

    $allowedReferences = @{}
    foreach ($entrypoint in @($entryAppJs, $entryAppCss, $entryConfigJs)) {
        if ($entrypoint) {
            $allowedReferences[[string]$entrypoint] = $true
        }
    }

    $indexPath = Join-Path $Root "index.html"
    $indexHtml = Get-Content -LiteralPath $indexPath -Raw -Encoding UTF8
    foreach ($entrypoint in @($entryAppJs, $entryAppCss, $entryConfigJs)) {
        if ($indexHtml -notmatch [regex]::Escape($entrypoint)) {
            throw "index.html nao referencia entrypoint do manifest: $entrypoint"
        }
    }

    $unexpectedReferences = New-Object System.Collections.Generic.List[string]
    $referencePattern = "(?i)(?:src|href)\s*=\s*['""](?<path>[^'""]+\.(?:js|css)(?:\?[^'""]*)?)['""]"
    foreach ($match in [regex]::Matches($indexHtml, $referencePattern)) {
        $reference = Normalize-FrontendReference -Reference $match.Groups["path"].Value -BasePath "index.html"
        if ($reference -and -not $allowedReferences.ContainsKey($reference)) {
            [void]$unexpectedReferences.Add($reference)
        }
    }

    if ($unexpectedReferences.Count -gt 0) {
        $joined = ($unexpectedReferences | Sort-Object -Unique) -join ", "
        throw "index.html referencia JS/CSS fora dos entrypoints do manifest: $joined"
    }
}

function Assert-FrontendTree {
    param([string]$Root)

    foreach ($relativePath in @("index.html", "asset-manifest.json")) {
        $candidate = Join-Path $Root $relativePath
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw "Arquivo obrigatorio ausente no frontend: $candidate"
        }
    }

    foreach ($relativePath in @("app\app", "features\features", "compat\compat")) {
        $candidate = Join-Path $Root $relativePath
        if (Test-Path -LiteralPath $candidate -PathType Container) {
            throw "Arvore frontend contem diretorio duplicado/orfao: $candidate"
        }
    }

    $manifestPath = Join-Path $Root "asset-manifest.json"
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json

    if ($manifest.schema -ne "frontend_asset_manifest_v1") {
        throw "Schema invalido de manifest: $($manifest.schema)"
    }

    $entrypoints = $manifest.entrypoints
    if (-not $entrypoints) {
        throw "Manifest sem bloco de entrypoints: $manifestPath"
    }

    $entryAppJs = Get-JsonPropertyValue -Object $entrypoints -Name "app.js"
    $entryAppCss = Get-JsonPropertyValue -Object $entrypoints -Name "app.css"
    $entryConfigJs = Get-JsonPropertyValue -Object $entrypoints -Name "config.js"

    if (-not (Test-FingerprintedAssetPath -AssetPath $entryAppJs -ExpectedExtension "js")) {
        throw "Entrypoint app.js sem fingerprint forte no nome: $entryAppJs"
    }
    if (-not (Test-FingerprintedAssetPath -AssetPath $entryAppCss -ExpectedExtension "css")) {
        throw "Entrypoint app.css sem fingerprint forte no nome: $entryAppCss"
    }
    if (-not (Test-FingerprintedAssetPath -AssetPath $entryConfigJs -ExpectedExtension "js")) {
        throw "Entrypoint config.js sem fingerprint forte no nome: $entryConfigJs"
    }

    foreach ($entrypoint in @($entryAppJs, $entryAppCss, $entryConfigJs)) {
        $assetPath = Join-Path $Root $entrypoint
        if (-not (Test-Path -LiteralPath $assetPath -PathType Leaf)) {
            throw "Entrypoint ausente no disco: $assetPath"
        }
    }

    $assetsObject = $manifest.fingerprinted_assets
    if (-not $assetsObject) {
        throw "Manifest sem fingerprinted_assets: $manifestPath"
    }

    $assetProperties = @($assetsObject.PSObject.Properties)
    if ($assetProperties.Count -eq 0) {
        throw "Manifest sem itens em fingerprinted_assets: $manifestPath"
    }

    foreach ($property in $assetProperties) {
        $sourcePath = $property.Name
        $fingerprintedPath = [string]$property.Value
        $extension = [System.IO.Path]::GetExtension($sourcePath).TrimStart(".").ToLowerInvariant()
        if ($extension -notin @("js", "css")) {
            continue
        }
        if (-not (Test-FingerprintedAssetPath -AssetPath $fingerprintedPath -ExpectedExtension $extension)) {
            throw "Asset sem fingerprint forte no nome para ${sourcePath}: $fingerprintedPath"
        }
        $assetPath = Join-Path $Root $fingerprintedPath
        if (-not (Test-Path -LiteralPath $assetPath -PathType Leaf)) {
            throw "Asset fingerprintado ausente no disco: $assetPath"
        }
    }

    $indexPath = Join-Path $Root "index.html"
    $indexHtml = Get-Content -LiteralPath $indexPath -Raw -Encoding UTF8
    foreach ($entrypoint in @($entryAppJs, $entryAppCss, $entryConfigJs)) {
        if ($indexHtml -notmatch [regex]::Escape($entrypoint)) {
            throw "index.html nao referencia entrypoint do manifest: $entrypoint"
        }
    }

    Assert-NoQueryVersioning -Root $Root
    Assert-NoOrphanFrontendAssets -Root $Root -Manifest $manifest
    Assert-IndexReferencesManifestGraph -Root $Root -Manifest $manifest

    $manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash
    return [pscustomobject]@{
        build_version_utc = [string]$manifest.build_version_utc
        manifest_sha256   = $manifestHash
        app_js            = $entryAppJs
        app_css           = $entryAppCss
        config_js         = $entryConfigJs
    }
}

$publishConfig = Resolve-PublishConfiguration `
    -RequestedEnvironment $Environment `
    -RequestedDestination $Destination `
    -RequestedEnvFile $EnvFile `
    -RequestedConfirmProdPublish $ConfirmProdPublish

$Destination = $publishConfig.Destination
$EnvFile = $publishConfig.EnvFile

$resolvedRepoRoot = Resolve-RepoRoot -ExplicitRoot $RepoRoot
$resolvedDestination = Assert-SafePath -Path $Destination -Purpose "Destination"
$resolvedBackupRoot = Assert-SafePath -Path $BackupRoot -Purpose "BackupRoot"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

if ($ValidateOnly) {
    Write-Host "Validacao de publicacao frontend concluida."
    Write-Host "Environment: $($publishConfig.Environment)"
    Write-Host "Destination: $resolvedDestination"
    Write-Host "EnvFile: $EnvFile"
    Write-Host "BackupRoot: $resolvedBackupRoot"
    return
}

if (-not $BuildDir) {
    $BuildDir = Join-Path $resolvedRepoRoot "runtime\tmp\frontend-publish-$timestamp"
}
$resolvedBuildDir = [System.IO.Path]::GetFullPath($BuildDir)

$python = Join-Path $resolvedRepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $python = "python"
}

$buildScript = Join-Path $resolvedRepoRoot "frontend\scripts\build_frontend.py"
if (-not (Test-Path -LiteralPath $buildScript -PathType Leaf)) {
    throw "Build script nao encontrado: $buildScript"
}

if (-not $SkipBuild) {
    $buildArgs = @($buildScript, "--output-dir", $resolvedBuildDir)
    if ($EnvFile -and (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        $buildArgs += @("--env-file", $EnvFile)
    }

    Write-Host "Gerando build frontend em $resolvedBuildDir"
    & $python @buildArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Build frontend falhou com exit code $LASTEXITCODE"
    }
}

$buildInfo = Assert-FrontendTree -Root $resolvedBuildDir

$destinationParent = Split-Path -Parent $resolvedDestination
$destinationLeaf = Split-Path -Leaf $resolvedDestination
if (-not (Test-Path -LiteralPath $destinationParent -PathType Container)) {
    New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null
}

$stagingDir = Join-Path $destinationParent "$destinationLeaf.__staging__-$timestamp"
$previousDir = Join-Path $destinationParent "$destinationLeaf.__previous__-$timestamp"
if (Test-Path -LiteralPath $stagingDir) {
    throw "Diretorio de staging ja existe: $stagingDir"
}
if (Test-Path -LiteralPath $previousDir) {
    throw "Diretorio de release anterior ja existe para este timestamp: $previousDir"
}

$stageExit = $null
$stagedInfo = $null
if ($PSCmdlet.ShouldProcess($stagingDir, "Preparar release frontend em staging")) {
    New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null
    $stageExit = Invoke-RobocopyChecked -Source $resolvedBuildDir -Target $stagingDir -ExtraArgs @("/MIR", "/R:2", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
    $stagedInfo = Assert-FrontendTree -Root $stagingDir
    if ($stagedInfo.manifest_sha256 -ne $buildInfo.manifest_sha256) {
        throw "Manifesto do staging diverge do build validado."
    }
}

$switchedPrevious = $false
$publishedInfo = $null
if ($PSCmdlet.ShouldProcess($resolvedDestination, "Trocar release frontend por swap atomico")) {
    if (Test-Path -LiteralPath $resolvedDestination -PathType Container) {
        Rename-Item -LiteralPath $resolvedDestination -NewName (Split-Path -Leaf $previousDir)
        $switchedPrevious = $true
    }

    try {
        Rename-Item -LiteralPath $stagingDir -NewName $destinationLeaf
    } catch {
        if ($switchedPrevious -and -not (Test-Path -LiteralPath $resolvedDestination -PathType Container) -and (Test-Path -LiteralPath $previousDir -PathType Container)) {
            Rename-Item -LiteralPath $previousDir -NewName $destinationLeaf
        }
        throw
    }

    $publishedInfo = Assert-FrontendTree -Root $resolvedDestination
    if ($publishedInfo.manifest_sha256 -ne $stagedInfo.manifest_sha256) {
        throw "Manifesto publicado diverge do staging validado."
    }
}

$backupDir = $null
$backupExit = $null
if ($switchedPrevious -and (Test-Path -LiteralPath $previousDir -PathType Container)) {
    $backupDir = Join-Path $resolvedBackupRoot "prod-before-frontend-publish-$timestamp"
    if ($PSCmdlet.ShouldProcess($backupDir, "Criar backup do release frontend anterior")) {
        New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
        $backupExit = Invoke-RobocopyChecked -Source $previousDir -Target $backupDir -ExtraArgs @("/MIR", "/R:2", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
    }
}

if ($publishedInfo) {
    Write-Host "Frontend publicado com sucesso."
    Write-Host "Destino ativo: $resolvedDestination"
    Write-Host "Build version (UTC): $($publishedInfo.build_version_utc)"
    Write-Host "Manifest SHA-256: $($publishedInfo.manifest_sha256)"
    Write-Host "Staging robocopy exit: $stageExit"
    if ($backupDir) {
        Write-Host "Backup release anterior: $backupDir"
        Write-Host "Backup robocopy exit: $backupExit"
    }
    if ($switchedPrevious -and (Test-Path -LiteralPath $previousDir -PathType Container)) {
        Write-Host "Release anterior preservado para rollback rapido em: $previousDir"
    }
}
