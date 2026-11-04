#Requires -Version 7.2
<#
    SYNTHETIC DATA · for training only · no OSFI data
    ------------------------------------------------------------------
    FdaCommon.ps1
    Shared helpers for the FDA (Fabric Data Analysts) demo kit scripts. Dot-source it:
        . (Join-Path $PSScriptRoot 'FdaCommon.ps1')

    Same proven patterns as the previous session's kit:
      - Az.Accounts tokens per resource (Fabric, Power BI, SQL, OneLake), MFA/Conditional Access retry
      - Fabric REST with 429/5xx retry, long-running operation (202) polling, continuationUri paging
      - item create-or-update with inline base64 definition parts
      - Invoke-Sqlcmd -AccessToken for the SQL analytics endpoint and the warehouse
    No secrets are stored anywhere; tokens live in memory only.
#>

$ErrorActionPreference = 'Stop'
$script:FabricApi       = 'https://api.fabric.microsoft.com'
$script:FabricResource  = 'https://api.fabric.microsoft.com'
$script:PbiApi          = 'https://api.powerbi.com/v1.0/myorg'
$script:PbiResource     = 'https://analysis.windows.net/powerbi/api'
$script:SqlResource     = 'https://database.windows.net/'
$script:StorageResource = 'https://storage.azure.com/'
$script:KitRoot         = Split-Path $PSScriptRoot -Parent

function Write-Step([string]$Message) { Write-Host "[step] $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message)   { Write-Host "  [ok] $Message" -ForegroundColor Green }
function Write-Info([string]$Message) { Write-Host "  [..] $Message" -ForegroundColor Gray }
function Write-Warn([string]$Message) { Write-Host "  [warn] $Message" -ForegroundColor Yellow }

# ================================================================== configuration
function Read-FdaConfig([string]$ConfigPath) {
    $defaults = [ordered]@{
        tenantId          = $null
        capacityId        = $null
        presenterUpn      = $null
        devWorkspaceName  = 'FDA-Analyst-Dev'
        testWorkspaceName = 'FDA-Analyst-Test'
        scaleFactor       = 1.0
        testScaleFactor   = 0.25
    }
    if (Test-Path $ConfigPath) {
        $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        foreach ($k in @($defaults.Keys)) {
            if ($cfg.PSObject.Properties[$k] -and $null -ne $cfg.$k -and "$($cfg.$k)" -ne '' -and "$($cfg.$k)" -notmatch '^0{8}-0{4}-') {
                $defaults[$k] = $cfg.$k
            }
        }
    }
    else { Write-Warn "config not found: $ConfigPath (copy config.sample.json to config.json)" }
    return $defaults
}

function Assert-Modules([string[]]$Names) {
    foreach ($m in $Names) {
        if (-not (Get-Module -ListAvailable -Name $m)) { throw "Module $m not found. Install-Module $m -Scope CurrentUser" }
        Import-Module $m -ErrorAction Stop
    }
    if ($Names -contains 'SqlServer' -and -not (Get-Command Invoke-Sqlcmd).Parameters.ContainsKey('AccessToken')) {
        throw 'SqlServer module v22+ is required (Invoke-Sqlcmd -AccessToken).'
    }
}

# ================================================================== auth
$script:ReauthDone = @{}
$script:TenantIdForAuth = $null
$script:UseDeviceAuth = $false

function Connect-Fda([string]$TenantId, [switch]$UseDeviceAuthentication) {
    $script:TenantIdForAuth = $TenantId
    $script:UseDeviceAuth = [bool]$UseDeviceAuthentication
    $ctx = Get-AzContext -ErrorAction SilentlyContinue
    if (-not $ctx -or ($TenantId -and $ctx.Tenant.Id -ne $TenantId)) {
        $p = @{ ErrorAction = 'Stop'; AuthScope = $script:FabricResource }
        if ($TenantId) { $p.Tenant = $TenantId }
        if ($UseDeviceAuthentication) { $p.UseDeviceAuthentication = $true }
        Connect-AzAccount @p | Out-Null
        $ctx = Get-AzContext
    }
    Write-Ok "signed in as $($ctx.Account.Id) (tenant $($ctx.Tenant.Id))"
    return $ctx
}

function Get-Token([string]$ResourceUrl) {
    # Newer Az.Accounts returns Token as SecureString; older returns a string.
    # If Conditional Access (MFA) needs interaction for a resource, sign in once more with -AuthScope.
    $t = $null
    try {
        $t = Get-AzAccessToken -ResourceUrl $ResourceUrl -ErrorAction Stop -WarningAction SilentlyContinue
    }
    catch {
        $msg = $_.Exception.Message
        if ($msg -notmatch 'interaction|AuthScope|multi-factor|MFA|AADSTS50076|AADSTS50079|AADSTS53003|claims') { throw }
        if ($script:ReauthDone[$ResourceUrl]) { throw }
        Write-Info "Conditional Access needs an interactive sign-in for $ResourceUrl - opening sign-in..."
        $re = @{ AuthScope = $ResourceUrl; ErrorAction = 'Stop' }
        if ($script:TenantIdForAuth) { $re.Tenant = $script:TenantIdForAuth }
        if ($script:UseDeviceAuth) { $re.UseDeviceAuthentication = $true }
        Connect-AzAccount @re -WarningAction SilentlyContinue | Out-Null
        $script:ReauthDone[$ResourceUrl] = $true
        $t = Get-AzAccessToken -ResourceUrl $ResourceUrl -ErrorAction Stop -WarningAction SilentlyContinue
    }
    if ($t.Token -is [System.Security.SecureString]) {
        return [System.Net.NetworkCredential]::new('', $t.Token).Password
    }
    return [string]$t.Token
}

function Get-AuthHeader([string]$ResourceUrl) {
    return @{ Authorization = ('Bearer ' + (Get-Token $ResourceUrl)) }
}

# ================================================================== Fabric REST
function Get-HeaderValue($Response, [string]$Name) {
    foreach ($k in $Response.Headers.Keys) {
        if ($k -ieq $Name) { return [string]($Response.Headers[$k] | Select-Object -First 1) }
    }
    return $null
}

function Get-RetryAfter($Response, [int]$Default = 5) {
    $v = Get-HeaderValue $Response 'Retry-After'
    $n = 0
    if ($v -and [int]::TryParse($v, [ref]$n)) { return [Math]::Min([Math]::Max($n, 2), 60) }
    return $Default
}

function ConvertFrom-FabricContent($Response) {
    $c = $Response.Content
    if ($c -is [byte[]]) { $c = [System.Text.Encoding]::UTF8.GetString($c) }
    if ([string]::IsNullOrWhiteSpace($c)) { return $null }
    try { return $c | ConvertFrom-Json } catch { return $c }
}

function Invoke-Fabric {
    <#
      Calls the Fabric REST API (or any absolute URL with -Resource).
      - 429 and 5xx: retried with Retry-After.
      - 202: long-running operation; polls Location / x-ms-operation-id, returns the result when available.
      - -Raw returns the raw response (no error/LRO handling), e.g. for job scheduler calls.
    #>
    [CmdletBinding()]
    param(
        [ValidateSet('GET', 'POST', 'PUT', 'PATCH', 'DELETE')][string]$Method = 'GET',
        [Parameter(Mandatory)][string]$Path,
        $Body,
        [switch]$Raw,
        [string]$Resource = $script:FabricResource,
        [int]$MaxAttempts = 8,
        [int]$LroTimeoutMinutes = 30
    )
    $uri = if ($Path -match '^https?://') { $Path } else { "$script:FabricApi$Path" }
    $json = $null
    if ($null -ne $Body) { $json = if ($Body -is [string]) { $Body } else { $Body | ConvertTo-Json -Depth 64 -Compress } }

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        $req = @{
            Method             = $Method
            Uri                = $uri
            Headers            = (Get-AuthHeader $Resource)
            SkipHttpErrorCheck = $true
            ErrorAction        = 'Stop'
        }
        if ($null -ne $json) {
            $req.Body = [System.Text.Encoding]::UTF8.GetBytes($json)
            $req.ContentType = 'application/json; charset=utf-8'
        }
        $resp = Invoke-WebRequest @req
        $code = [int]$resp.StatusCode
        if (($code -eq 429 -or $code -ge 500) -and $attempt -lt $MaxAttempts) {
            $wait = Get-RetryAfter $resp (5 * $attempt)
            Write-Info "HTTP $code on $Method $uri - retry $attempt/$MaxAttempts in $wait s"
            Start-Sleep -Seconds $wait
            continue
        }
        if ($Raw) { return $resp }
        if ($code -ge 400) {
            $detail = ConvertFrom-FabricContent $resp
            $text = if ($detail -is [string]) { $detail } else { $detail | ConvertTo-Json -Depth 10 -Compress }
            $ex = [System.Exception]::new("$Method $uri -> HTTP $code $text")
            $ex.Data['StatusCode'] = $code
            throw $ex
        }
        if ($code -eq 202 -and $Resource -eq $script:FabricResource) { return Wait-FabricOperation -Response $resp -TimeoutMinutes $LroTimeoutMinutes }
        return ConvertFrom-FabricContent $resp
    }
}

function Wait-FabricOperation {
    param($Response, [int]$TimeoutMinutes = 30)
    $opId = Get-HeaderValue $Response 'x-ms-operation-id'
    $location = Get-HeaderValue $Response 'Location'
    if (-not $location -and $opId) { $location = "$script:FabricApi/v1/operations/$opId" }
    if (-not $location) { return ConvertFrom-FabricContent $Response }

    $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
    $delay = Get-RetryAfter $Response 5
    while ($true) {
        Start-Sleep -Seconds $delay
        $poll = Invoke-Fabric -Method GET -Path $location -Raw
        if ([int]$poll.StatusCode -ge 400) { throw "Operation poll failed: HTTP $([int]$poll.StatusCode) $($poll.Content)" }
        $state = ConvertFrom-FabricContent $poll
        $status = if ($state -and $state.PSObject.Properties['status']) { [string]$state.status } else { 'Unknown' }
        switch ($status) {
            'Succeeded' {
                if ($opId) {
                    $res = Invoke-Fabric -Method GET -Path "/v1/operations/$opId/result" -Raw
                    if ([int]$res.StatusCode -lt 300) { return ConvertFrom-FabricContent $res }
                }
                return $state
            }
            { $_ -in 'Failed', 'Cancelled' } {
                $err = if ($state.PSObject.Properties['error']) { $state.error | ConvertTo-Json -Depth 10 -Compress } else { '' }
                throw "Long-running operation $opId $($status): $err"
            }
            default {
                if ((Get-Date) -gt $deadline) { throw "Long-running operation $opId timed out after $TimeoutMinutes min (last status $status)" }
                $pct = if ($state -and $state.PSObject.Properties['percentComplete']) { " $($state.percentComplete)%" } else { '' }
                Write-Info "operation $($status)$pct ..."
                $delay = Get-RetryAfter $poll 5
            }
        }
    }
}

function Get-FabricList([string]$Path) {
    # Follows continuationUri paging; returns all "value" entries.
    $all = [System.Collections.Generic.List[object]]::new()
    $next = $Path
    while ($next) {
        $r = Invoke-Fabric -Path $next
        if ($r -and $r.PSObject.Properties['value']) { foreach ($v in $r.value) { $all.Add($v) } }
        $next = if ($r -and $r.PSObject.Properties['continuationUri'] -and $r.continuationUri) { $r.continuationUri } else { $null }
    }
    return $all.ToArray()
}

function Find-Workspace([string]$Name) {
    return Get-FabricList '/v1/workspaces' | Where-Object { $_.displayName -eq $Name } | Select-Object -First 1
}

function Get-OrNewWorkspace([string]$Name, [string]$CapacityId, [string]$Description) {
    $ws = Find-Workspace $Name
    if (-not $ws) {
        $ws = Invoke-Fabric -Method POST -Path '/v1/workspaces' -Body @{ displayName = $Name; capacityId = $CapacityId; description = $Description }
        Write-Ok "created workspace $Name ($($ws.id))"
        return $ws
    }
    Write-Info "workspace $Name exists ($($ws.id))"
    if (-not $ws.PSObject.Properties['capacityId'] -or $ws.capacityId -ne $CapacityId) {
        Invoke-Fabric -Method POST -Path "/v1/workspaces/$($ws.id)/assignToCapacity" -Body @{ capacityId = $CapacityId } | Out-Null
        Write-Ok "assigned $Name to capacity $CapacityId"
    }
    return $ws
}

function Find-FabricItem([string]$WorkspaceId, [string]$Type, [string]$Name) {
    return Get-FabricList "/v1/workspaces/$WorkspaceId/items?type=$Type" |
        Where-Object { $_.displayName -eq $Name } | Select-Object -First 1
}

function New-OrGetItem([string]$WorkspaceId, [string]$Type, [string]$Endpoint, [string]$Name, [hashtable]$Extra = @{}) {
    $existing = Find-FabricItem $WorkspaceId $Type $Name
    if ($existing) { Write-Info "$Type '$Name' exists ($($existing.id))"; return $existing }
    $body = @{ displayName = $Name }
    foreach ($k in $Extra.Keys) { $body[$k] = $Extra[$k] }
    $created = Invoke-Fabric -Method POST -Path "/v1/workspaces/$WorkspaceId/$Endpoint" -Body $body
    if (-not $created -or -not $created.PSObject.Properties['id']) {
        Start-Sleep -Seconds 5
        $created = Find-FabricItem $WorkspaceId $Type $Name
    }
    if (-not $created) { throw "$Type '$Name' was not found after creation." }
    Write-Ok "created $Type '$Name' ($($created.id))"
    return $created
}

function ConvertTo-InlinePart([string]$PartPath, [string]$Text) {
    return @{ path = $PartPath; payload = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($Text)); payloadType = 'InlineBase64' }
}

function Set-ItemWithDefinition([string]$WorkspaceId, [string]$Type, [string]$Endpoint, [string]$Name, [string]$Description, [hashtable]$Definition) {
    # Create with definition, or update the definition of an existing item (idempotent).
    $existing = Find-FabricItem $WorkspaceId $Type $Name
    if ($existing) {
        Invoke-Fabric -Method POST -Path "/v1/workspaces/$WorkspaceId/$Endpoint/$($existing.id)/updateDefinition" -Body @{ definition = $Definition } | Out-Null
        Write-Ok "updated $Type '$Name' definition ($($existing.id))"
        return $existing
    }
    $created = Invoke-Fabric -Method POST -Path "/v1/workspaces/$WorkspaceId/$Endpoint" -Body @{ displayName = $Name; description = $Description; definition = $Definition }
    if (-not $created -or -not $created.PSObject.Properties['id']) { Start-Sleep -Seconds 5; $created = Find-FabricItem $WorkspaceId $Type $Name }
    if (-not $created) { throw "$Type '$Name' was not found after creation." }
    Write-Ok "created $Type '$Name' ($($created.id))"
    return $created
}

function Test-OneLakePath([string]$WorkspaceId, [string]$ItemId, [string]$RelativePath) {
    # ADLS Gen2 "Get Properties" (HEAD) against OneLake: 200 = exists.
    $uri = "https://onelake.dfs.fabric.microsoft.com/$WorkspaceId/$ItemId/$RelativePath"
    $h = Get-AuthHeader $script:StorageResource
    $h['x-ms-version'] = '2023-11-03'
    $r = Invoke-WebRequest -Method Head -Uri $uri -SkipHttpErrorCheck -Headers $h
    return ([int]$r.StatusCode -eq 200)
}

# ================================================================== lakehouse / SQL
function Get-LakehouseSqlEndpoint([string]$WorkspaceId, [string]$LakehouseId, [int]$MaxWaitMinutes = 10) {
    $deadline = (Get-Date).AddMinutes($MaxWaitMinutes)
    while ($true) {
        $lh = Invoke-Fabric -Path "/v1/workspaces/$WorkspaceId/lakehouses/$LakehouseId"
        $sep = $lh.properties.sqlEndpointProperties
        if ($sep -and $sep.id -and $sep.connectionString -and $sep.provisioningStatus -eq 'Success') {
            return [pscustomobject]@{ id = $sep.id; connectionString = $sep.connectionString }
        }
        if ((Get-Date) -gt $deadline) { throw 'SQL analytics endpoint not provisioned yet' }
        Write-Info 'waiting for SQL analytics endpoint provisioning ...'
        Start-Sleep -Seconds 10
    }
}

function Update-SqlEndpointMetadata([string]$WorkspaceId, [string]$SqlEndpointId) {
    # VERIFY: refreshMetadata endpoint (GA path first, then the older ?preview=true path).
    try {
        Invoke-Fabric -Method POST -Path "/v1/workspaces/$WorkspaceId/sqlEndpoints/$SqlEndpointId/refreshMetadata" -Body @{} | Out-Null
    }
    catch {
        Invoke-Fabric -Method POST -Path "/v1/workspaces/$WorkspaceId/sqlEndpoints/$SqlEndpointId/refreshMetadata?preview=true" -Body @{} | Out-Null
    }
    Write-Ok 'SQL analytics endpoint metadata refresh requested'
}

function Invoke-FabricSql {
    param([string]$Server, [string]$Database, [string]$InputFile, [string]$Query)
    $p = @{
        ServerInstance    = $Server
        Database          = $Database
        AccessToken       = (Get-Token $script:SqlResource)
        QueryTimeout      = 1800
        ConnectionTimeout = 60
        OutputSqlErrors   = $true
        OutputAs          = 'DataSet'
        ErrorAction       = 'Stop'
        Verbose           = $true      # shows PRINT messages
    }
    if ($InputFile) { $p.InputFile = $InputFile } else { $p.Query = $Query }
    $ds = Invoke-Sqlcmd @p 4>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.VerboseRecord]) { Write-Info $_.Message } else { $_ }
    }
    foreach ($set in @($ds)) {
        if ($set -is [System.Data.DataSet]) {
            foreach ($tbl in $set.Tables) { $tbl | Format-Table -AutoSize | Out-String -Width 200 | Write-Host }
        }
    }
}

# ================================================================== notebooks
function ConvertTo-PyLiteral($Value) {
    if ($Value -is [bool]) { return $(if ($Value) { 'True' } else { 'False' }) }
    if ($Value -is [int] -or $Value -is [long] -or $Value -is [double] -or $Value -is [decimal] -or $Value -is [single]) {
        $s = [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, '{0}', $Value)
        if ($Value -is [double] -and $s -notmatch '[.eE]') { $s += '.0' }
        return $s
    }
    return '"' + ([string]$Value).Replace('\', '\\').Replace('"', '\"') + '"'
}

function Get-NotebookDefinition {
    <#
      Reads an .ipynb, sets the default lakehouse (metadata.dependencies.lakehouse) and overwrites
      values in the cell tagged "parameters" (e.g. workspace_id, lakehouse_id, scale_factor).
    #>
    param([string]$File, [string]$LakehouseId, [string]$LakehouseName, [string]$LakehouseWorkspaceId, [hashtable]$Parameters = @{})
    $nb = Get-Content $File -Raw | ConvertFrom-Json -AsHashtable
    if ($LakehouseId) {
        if (-not $nb.metadata.ContainsKey('dependencies') -or $null -eq $nb.metadata.dependencies) { $nb.metadata.dependencies = @{} }
        $nb.metadata.dependencies.lakehouse = [ordered]@{
            default_lakehouse              = $LakehouseId
            default_lakehouse_name         = $LakehouseName
            default_lakehouse_workspace_id = $LakehouseWorkspaceId
        }
    }
    foreach ($cell in $nb.cells) {
        $tags = if ($cell.metadata -and $cell.metadata.ContainsKey('tags')) { @($cell.metadata.tags) } else { @() }
        if ($tags -notcontains 'parameters') { continue }
        $lines = [System.Collections.Generic.List[string]]::new()
        foreach ($line in @($cell.source)) {
            $newLine = $line
            foreach ($k in $Parameters.Keys) {
                $m = [regex]::Match($line, "^(?<name>$([regex]::Escape($k)))\s*=\s*[^#\n]*?(?<comment>\s+#[^\n]*)?(?<nl>\n?)$")
                if ($m.Success) { $newLine = "$k = $(ConvertTo-PyLiteral $Parameters[$k])$($m.Groups['comment'].Value)$($m.Groups['nl'].Value)" }
            }
            $lines.Add($newLine)
        }
        $cell.source = $lines.ToArray()
    }
    $json = $nb | ConvertTo-Json -Depth 100
    return @{ format = 'ipynb'; parts = @(ConvertTo-InlinePart 'notebook-content.ipynb' $json) }
}

function Start-NotebookRun {
    <#
      Runs a notebook through the job scheduler and waits. Parameters are passed as run-time
      parameters (VERIFY: executionData body shape and type names string/int/float/bool).
    #>
    param([string]$WorkspaceId, [string]$NotebookId, [hashtable]$Parameters = @{}, $Lakehouse, [int]$TimeoutMinutes = 40)
    $exec = [ordered]@{}
    if ($Parameters.Count -gt 0) {
        $p = [ordered]@{}
        foreach ($k in $Parameters.Keys) {
            $v = $Parameters[$k]
            $type = if ($v -is [bool]) { 'bool' } elseif ($v -is [int] -or $v -is [long]) { 'int' } elseif ($v -is [double] -or $v -is [decimal]) { 'float' } else { 'string' }
            $val = if ($v -is [bool]) { $(if ($v) { 'true' } else { 'false' }) } else { [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, '{0}', $v) }
            $p[$k] = @{ value = $val; type = $type }
        }
        $exec.parameters = $p
    }
    if ($Lakehouse) {
        $exec.configuration = @{ defaultLakehouse = @{ name = $Lakehouse.displayName; id = $Lakehouse.id; workspaceId = $WorkspaceId } }
    }
    $body = if ($exec.Count -gt 0) { @{ executionData = $exec } } else { $null }
    $resp = Invoke-Fabric -Method POST -Path "/v1/workspaces/$WorkspaceId/items/$NotebookId/jobs/instances?jobType=RunNotebook" -Body $body -Raw
    if ([int]$resp.StatusCode -ne 202) { throw "run request failed: HTTP $([int]$resp.StatusCode) $($resp.Content)" }
    $jobUrl = Get-HeaderValue $resp 'Location'
    Write-Ok "notebook job started: $jobUrl"
    $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
    while ($true) {
        Start-Sleep -Seconds 20
        $job = Invoke-Fabric -Path $jobUrl
        Write-Info "notebook status: $($job.status)"
        if ($job.status -eq 'Completed') { return $job }
        if ($job.status -in 'Failed', 'Cancelled', 'Deduped') {
            throw "notebook $($job.status): $($job.failureReason | ConvertTo-Json -Depth 5 -Compress)"
        }
        if ((Get-Date) -gt $deadline) { throw 'notebook still running - check the Monitor hub' }
    }
}

# ================================================================== Power BI REST
function Invoke-PowerBI([string]$Method = 'GET', [string]$Path, $Body) {
    $p = @{ Method = $Method; Uri = "$script:PbiApi$Path"; Headers = (Get-AuthHeader $script:PbiResource); ErrorAction = 'Stop' }
    if ($null -ne $Body) { $p.Body = ($Body | ConvertTo-Json -Depth 20 -Compress); $p.ContentType = 'application/json' }
    return Invoke-RestMethod @p
}

function Start-DatasetRefresh([string]$WorkspaceId, [string]$DatasetId, [switch]$Wait, [int]$TimeoutMinutes = 20) {
    Invoke-PowerBI -Method POST -Path "/groups/$WorkspaceId/datasets/$DatasetId/refreshes" -Body @{ notifyOption = 'NoNotification' } | Out-Null
    Write-Ok 'refresh requested'
    if (-not $Wait) { return }
    $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
    while ($true) {
        Start-Sleep -Seconds 10
        $last = (Invoke-PowerBI -Path "/groups/$WorkspaceId/datasets/$DatasetId/refreshes?`$top=1").value | Select-Object -First 1
        $status = if ($last) { $last.status } else { 'Unknown' }
        Write-Info "refresh status: $status"
        if ($status -eq 'Completed') { return }
        if ($status -eq 'Failed') { throw "refresh failed: $($last.serviceExceptionJson)" }
        if ((Get-Date) -gt $deadline) { throw 'refresh still running' }
    }
}

# ================================================================== step runner
$script:Failures = [System.Collections.Generic.List[string]]::new()
function Invoke-Step([string]$Name, [string]$Fallback, [scriptblock]$Action) {
    Write-Step $Name
    $t0 = Get-Date
    try {
        $null = & $Action
        Write-Info ("{0:n0}s" -f ((Get-Date) - $t0).TotalSeconds)
        return $true
    }
    catch {
        Write-Host "  [fail] $Name : $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "  [fallback] $Fallback" -ForegroundColor Yellow
        $script:Failures.Add($Name)
        return $false
    }
}

function Get-Id($o) { if ($o -and $o.PSObject.Properties['id']) { return $o.id } else { return $null } }
