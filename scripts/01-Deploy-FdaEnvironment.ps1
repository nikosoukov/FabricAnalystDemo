#Requires -Version 7.2
<#
    SYNTHETIC DATA · for training only · no OSFI data
    ------------------------------------------------------------------
    01-Deploy-FdaEnvironment.ps1
    Builds the whole "Microsoft Fabric for Data Analysts" demo environment from scratch with the
    Fabric and Power BI REST APIs. Nothing from earlier sessions is reused.

      FDA-Analyst-Dev   (main demo workspace, on your F-SKU capacity)
        lh_supervisory (lakehouse, schemas off)  <- nb_fda_00_generate_data (scale 1.0)
        wh_analyst_sandbox (warehouse)           <- sql/30_wh_sandbox_setup.sql
        nb_fda_00_generate_data, nb_fda_01_analyst_explore, nb_fda_02_land_late_filings
        SQL analytics endpoint views             <- sql/20_lh_views.sql
        sm_fda_supervisory        (Direct Lake TMDL, model/sm_fda_supervisory)
        sm_fda_supervisory_import (Import TMDL,      model/sm_fda_supervisory_import)
        df_fda_watch_thresholds   (Dataflow Gen2: queryMetadata.json + mashup.pq)
        rpt_fda_institution_return (paginated report, Power BI Imports API)
      FDA-Analyst-Test  (deployment target)
        lh_supervisory <- nb_fda_00_generate_data (scale 0.25, late filers still missing)
      dp_fda_analyst    (deployment pipeline: Development = Dev, Test = Test)

    Idempotent: existing items are reused, definitions updated. Data is generated only when
    lh_supervisory has no tables yet (use -RegenerateData to force; that also undoes D2/D5).
    Every step prints its README click fallback on failure and the script continues where possible.
    Writes ./out/fda-environment.json.

    Requires: PowerShell 7.2+, Az.Accounts, SqlServer (v22+), Fabric admin / capacity contributor.

    Examples:
      ./01-Deploy-FdaEnvironment.ps1
      ./01-Deploy-FdaEnvironment.ps1 -SkipTest -SkipPipeline
      ./01-Deploy-FdaEnvironment.ps1 -RegenerateData -ScaleFactor 0.5
#>
[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'config.json'),
    [string]$TenantId,
    [string]$CapacityId,
    [double]$ScaleFactor = -1,
    [switch]$SkipTest,
    [switch]$SkipImportModel,
    [switch]$SkipPaginated,
    [switch]$SkipDataflow,
    [switch]$SkipPipeline,
    [switch]$RegenerateData,
    [switch]$UseDeviceAuthentication,
    [string]$OutDir = (Join-Path $PSScriptRoot 'out')
)

. (Join-Path $PSScriptRoot 'FdaCommon.ps1')
$Started = Get-Date

# ================================================================== configuration
Write-Step 'Reading configuration'
$cfg = Read-FdaConfig $ConfigPath
if ($TenantId)   { $cfg.tenantId = $TenantId }
if ($CapacityId) { $cfg.capacityId = $CapacityId }
if ($ScaleFactor -gt 0) { $cfg.scaleFactor = $ScaleFactor }
if (-not $cfg.capacityId) { throw 'capacityId is required (Admin portal > Capacity settings > Fabric capacity > your F-SKU).' }
$DevName  = $cfg.devWorkspaceName
$TestName = $cfg.testWorkspaceName
Write-Info "dev=$DevName test=$TestName capacity=$($cfg.capacityId) scale=$($cfg.scaleFactor) testScale=$($cfg.testScaleFactor)"
Assert-Modules 'Az.Accounts', 'SqlServer'

Write-Step 'Signing in (Az.Accounts) and getting tokens for Fabric, Power BI and SQL'
$azCtx = Connect-Fda -TenantId $cfg.tenantId -UseDeviceAuthentication:$UseDeviceAuthentication
if (-not $cfg.tenantId) { $cfg.tenantId = $azCtx.Tenant.Id }
foreach ($r in $script:FabricResource, $script:PbiResource, $script:SqlResource) { $null = Get-Token $r }
Write-Ok 'tokens acquired'

$S = @{}   # shared state (hashtable so step script blocks can write into it)
$Desc = 'FDA - Microsoft Fabric for Data Analysts demo (OSFI training). SYNTHETIC DATA - for training only - no OSFI data.'

# ================================================================== S4 Dev workspace
$ok = Invoke-Step "Workspace '$DevName' on capacity" 'README > Setup > S4: Workspaces > New workspace > FDA-Analyst-Dev > Advanced > License mode: Fabric capacity > your capacity.' {
    $S.dev = Get-OrNewWorkspace $DevName $cfg.capacityId $Desc
}
if (-not $ok -or -not $S.dev) { throw 'Cannot continue without the Dev workspace.' }
$devId = $S.dev.id

# ================================================================== S5 lakehouse + warehouse
Invoke-Step 'Lakehouse lh_supervisory (schemas off)' 'README > Setup > S5: New item > Lakehouse > lh_supervisory (leave "Lakehouse schemas" unticked).' {
    # VERIFY: lakehouses are created without schemas unless creationPayload.enableSchemas = true.
    $S.lh = New-OrGetItem $devId 'Lakehouse' 'lakehouses' 'lh_supervisory' @{ description = 'Supervisory returns, dbo Delta tables (SYNTHETIC DATA)' }
} | Out-Null

Invoke-Step 'Warehouse wh_analyst_sandbox' 'README > Setup > S5: New item > Warehouse > wh_analyst_sandbox.' {
    $S.wh = New-OrGetItem $devId 'Warehouse' 'warehouses' 'wh_analyst_sandbox' @{ description = 'Analyst sandbox: writable T-SQL, cross-database queries (SYNTHETIC DATA)' }
} | Out-Null
if (-not $S.lh) { throw 'Cannot continue without lh_supervisory.' }

# ================================================================== S6 notebooks
$NotebookNames = 'nb_fda_00_generate_data', 'nb_fda_01_analyst_explore', 'nb_fda_02_land_late_filings'
$S.notebooks = [ordered]@{}
Invoke-Step 'Notebooks nb_fda_00 / nb_fda_01 / nb_fda_02 (default lakehouse lh_supervisory)' 'README > Setup > S6: workspace > Import > Notebook > From this computer > notebooks/*.ipynb; open each > Explorer > Add lakehouse > lh_supervisory; in nb_fda_00 and nb_fda_02 leave workspace_id/lakehouse_id empty.' {
    foreach ($name in $NotebookNames) {
        $params = @{}
        if ($name -ne 'nb_fda_01_analyst_explore') {
            $params = @{ workspace_id = $devId; lakehouse_id = $S.lh.id; scale_factor = [double]$cfg.scaleFactor }
        }
        $def = Get-NotebookDefinition -File (Join-Path $script:KitRoot "notebooks/$name.ipynb") -LakehouseId $S.lh.id -LakehouseName 'lh_supervisory' -LakehouseWorkspaceId $devId -Parameters $params
        $S.notebooks[$name] = Set-ItemWithDefinition $devId 'Notebook' 'notebooks' $name 'FDA demo notebook (SYNTHETIC DATA)' $def
    }
} | Out-Null

# ================================================================== S7 generate data
Invoke-Step 'Generate data: run nb_fda_00_generate_data (3-10 min incl. Spark start)' 'README > Setup > S7: open nb_fda_00_generate_data > Run all. Expected last cell: 2026 Q3 institutions reporting: 30.' {
    $nb = $S.notebooks['nb_fda_00_generate_data']
    if (-not $nb) { throw 'nb_fda_00_generate_data missing' }
    $exists = Test-OneLakePath $devId $S.lh.id 'Tables/fact_mortgage_exposure/_delta_log'
    if ($exists -and -not $RegenerateData) { Write-Info 'tables already exist - skipped (use -RegenerateData to rebuild; that resets D2/D5 state)'; return }
    Start-NotebookRun -WorkspaceId $devId -NotebookId $nb.id -Lakehouse $S.lh -Parameters @{
        workspace_id = $devId; lakehouse_id = $S.lh.id; scale_factor = [double]$cfg.scaleFactor; only_reset_thresholds = $false
    } | Out-Null
    Write-Ok 'data generated'
} | Out-Null

# ================================================================== S8 SQL endpoint + views + warehouse
Invoke-Step 'Refresh lh_supervisory SQL analytics endpoint metadata' 'README > Setup > S8: lh_supervisory > SQL analytics endpoint > Refresh (the tables appear under dbo).' {
    $S.sqlEp = Get-LakehouseSqlEndpoint $devId $S.lh.id
    Update-SqlEndpointMetadata $devId $S.sqlEp.id
    Start-Sleep -Seconds 20
} | Out-Null

Invoke-Step 'Views on the SQL analytics endpoint (sql/20_lh_views.sql)' 'README > Setup > S8: lh_supervisory SQL analytics endpoint > New SQL query > paste sql/20_lh_views.sql > Run.' {
    if (-not $S.sqlEp) { $S.sqlEp = Get-LakehouseSqlEndpoint $devId $S.lh.id }
    Invoke-FabricSql -Server $S.sqlEp.connectionString -Database 'lh_supervisory' -InputFile (Join-Path $script:KitRoot 'sql/20_lh_views.sql')
} | Out-Null

Invoke-Step 'Warehouse sandbox table (sql/30_wh_sandbox_setup.sql)' 'README > Setup > S8: wh_analyst_sandbox > New SQL query > paste sql/30_wh_sandbox_setup.sql > Run.' {
    $w = Invoke-Fabric -Path "/v1/workspaces/$devId/warehouses/$($S.wh.id)"
    $S.whConnection = $w.properties.connectionString
    if (-not $S.whConnection) { throw 'warehouse connectionString not available' }
    Invoke-FabricSql -Server $S.whConnection -Database 'wh_analyst_sandbox' -InputFile (Join-Path $script:KitRoot 'sql/30_wh_sandbox_setup.sql')
} | Out-Null

# ================================================================== S9 semantic models
function Get-ModelParts([string]$Folder, [hashtable]$Replace) {
    $root = Join-Path $script:KitRoot "model/$Folder"
    foreach ($f in Get-ChildItem $root -Recurse -File) {
        $rel = [System.IO.Path]::GetRelativePath($root, $f.FullName).Replace('\', '/')
        $text = Get-Content $f.FullName -Raw
        foreach ($k in $Replace.Keys) { $text = $text.Replace($k, $Replace[$k]) }
        ConvertTo-InlinePart $rel $text
    }
}

Invoke-Step 'Semantic model sm_fda_supervisory (Direct Lake, TMDL)' 'README > Setup > S9: lh_supervisory > New semantic model > sm_fda_supervisory > tick all 8 tables; then build relationships/measures from model/sm_fda_supervisory/definition/*.tmdl (or open in Power BI Desktop with TMDL view).' {
    if (-not $S.sqlEp) { $S.sqlEp = Get-LakehouseSqlEndpoint $devId $S.lh.id }
    $parts = @(Get-ModelParts 'sm_fda_supervisory' @{ '__SQL_ENDPOINT__' = $S.sqlEp.connectionString; '__SQL_ENDPOINT_ID__' = $S.sqlEp.id })
    $S.smDirect = Set-ItemWithDefinition $devId 'SemanticModel' 'semanticModels' 'sm_fda_supervisory' 'Supervisory analytics, Direct Lake on lh_supervisory (SYNTHETIC DATA)' @{ parts = $parts }
    try { Start-DatasetRefresh $devId $S.smDirect.id -Wait -TimeoutMinutes 10 }
    catch { Write-Warn "framing refresh not completed ($($_.Exception.Message)). Open the model > Settings > data source credentials (OAuth2, SSO), then Refresh." }
} | Out-Null

if (-not $SkipImportModel) {
    Invoke-Step 'Semantic model sm_fda_supervisory_import (Import, TMDL)' 'README > Setup > S9: Power BI Desktop > Get data > SQL Server (endpoint, database lh_supervisory, Import) > 8 tables > paste measures > Publish as sm_fda_supervisory_import.' {
        if (-not $S.sqlEp) { $S.sqlEp = Get-LakehouseSqlEndpoint $devId $S.lh.id }
        $parts = @(Get-ModelParts 'sm_fda_supervisory_import' @{ '__SQL_ENDPOINT__' = $S.sqlEp.connectionString })
        $S.smImport = Set-ItemWithDefinition $devId 'SemanticModel' 'semanticModels' 'sm_fda_supervisory_import' 'Supervisory analytics, Import copy for the storage-mode demo (SYNTHETIC DATA)' @{ parts = $parts }
        try { Start-DatasetRefresh $devId $S.smImport.id -Wait -TimeoutMinutes 20; $S.importRefreshed = $true }
        catch {
            Write-Warn "import refresh not done yet ($($_.Exception.Message))."
            Write-Warn 'CLICK: sm_fda_supervisory_import > Settings > Data source credentials > Edit credentials > OAuth2, privacy Organizational > Sign in; then Refresh now (README S10).'
        }
    } | Out-Null
}
else { Write-Warn 'SkipImportModel: D2 needs sm_fda_supervisory_import - build it by hand (README S9 fallback).' }

# ================================================================== S11 dataflow
if (-not $SkipDataflow) {
    Invoke-Step 'Dataflow Gen2 df_fda_watch_thresholds (definition upload)' 'README > Setup > S11 and dataflow/click-build.md: New item > Dataflow Gen2 > df_fda_watch_thresholds > Get data > Lakehouse > lh_supervisory > Files/reference > supervisory_watch_thresholds.xlsx > steps.' {
        $root = Join-Path $script:KitRoot 'dataflow/df_fda_watch_thresholds'
        $mashup = (Get-Content (Join-Path $root 'mashup.pq') -Raw).Replace('__WORKSPACE_ID__', $devId).Replace('__LAKEHOUSE_ID__', $S.lh.id)
        $meta = Get-Content (Join-Path $root 'queryMetadata.json') -Raw
        # VERIFY: Dataflow Gen2 (CI/CD) definition parts queryMetadata.json + mashup.pq, endpoint /dataflows.
        $def = @{ parts = @((ConvertTo-InlinePart 'queryMetadata.json' $meta), (ConvertTo-InlinePart 'mashup.pq' $mashup)) }
        $S.dataflow = Set-ItemWithDefinition $devId 'Dataflow' 'dataflows' 'df_fda_watch_thresholds' 'Watch thresholds Excel -> supervisory_watch_thresholds (SYNTHETIC DATA)' $def
        Write-Warn 'CLICK (S11): open df_fda_watch_thresholds > configure the Lakehouse connection (OAuth2) > check the preview (14 rows) > Save. Destination is set in D5 (or now, see README).'
    } | Out-Null
}

# ================================================================== S12 paginated report
if (-not $SkipPaginated) {
    Invoke-Step 'Paginated report rpt_fda_institution_return (Power BI Imports API)' 'README > Setup > S12 and paginated/README-paginated.md: Power BI Report Builder > open the .rdl > Data source > sm_fda_supervisory > Publish to FDA-Analyst-Dev.' {
        if (-not $S.smDirect) { $S.smDirect = Find-FabricItem $devId 'SemanticModel' 'sm_fda_supervisory' }
        if (-not $S.smDirect) { throw 'sm_fda_supervisory not found' }
        New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
        $rdl = (Get-Content (Join-Path $script:KitRoot 'paginated/rpt_fda_institution_return.rdl') -Raw).Replace('__TENANT_ID__', $cfg.tenantId).Replace('__DATASET_ID__', $S.smDirect.id)
        $rdlPath = Join-Path $OutDir 'rpt_fda_institution_return.rdl'
        Set-Content -Path $rdlPath -Value $rdl -Encoding utf8NoBOM
        $existing = (Invoke-PowerBI -Path "/groups/$devId/reports").value | Where-Object { $_.name -eq 'rpt_fda_institution_return' } | Select-Object -First 1
        $conflict = if ($existing) { 'Overwrite' } else { 'Abort' }
        # VERIFY: Imports API for .rdl (datasetDisplayName must include the .rdl extension; nameConflict Abort/Overwrite).
        $uri = "$script:PbiApi/groups/$devId/imports?datasetDisplayName=rpt_fda_institution_return.rdl&nameConflict=$conflict"
        $imp = Invoke-RestMethod -Method Post -Uri $uri -Headers (Get-AuthHeader $script:PbiResource) -Form @{ file = Get-Item $rdlPath }
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Seconds 5
            $st = Invoke-PowerBI -Path "/groups/$devId/imports/$($imp.id)"
            Write-Info "import state: $($st.importState)"
            if ($st.importState -eq 'Succeeded') { $S.paginated = $st.reports | Select-Object -First 1; break }
            if ($st.importState -eq 'Failed') { throw "import failed: $($st | ConvertTo-Json -Depth 5 -Compress)" }
        }
        if (-not $S.paginated) { throw 'import did not finish in time' }
        Write-Ok "paginated report $($S.paginated.id)"
    } | Out-Null
}

# ================================================================== S13 Test workspace
if (-not $SkipTest) {
    Invoke-Step "Test workspace '$TestName' + lh_supervisory + nb_fda_00 (scale $($cfg.testScaleFactor))" 'README > Setup > S13: create FDA-Analyst-Test on the capacity > New lakehouse lh_supervisory > Import nb_fda_00 > attach lh_supervisory > set scale_factor = 0.25 > Run all.' {
        $S.test = Get-OrNewWorkspace $TestName $cfg.capacityId ($Desc + ' Deployment target (Test stage).')
        $S.testLh = New-OrGetItem $S.test.id 'Lakehouse' 'lakehouses' 'lh_supervisory' @{ description = 'Supervisory returns, Test stage (SYNTHETIC DATA)' }
        $def = Get-NotebookDefinition -File (Join-Path $script:KitRoot 'notebooks/nb_fda_00_generate_data.ipynb') -LakehouseId $S.testLh.id -LakehouseName 'lh_supervisory' -LakehouseWorkspaceId $S.test.id -Parameters @{
            workspace_id = $S.test.id; lakehouse_id = $S.testLh.id; scale_factor = [double]$cfg.testScaleFactor
        }
        $S.testNb = Set-ItemWithDefinition $S.test.id 'Notebook' 'notebooks' 'nb_fda_00_generate_data' 'FDA demo notebook (SYNTHETIC DATA)' $def
        $exists = Test-OneLakePath $S.test.id $S.testLh.id 'Tables/fact_mortgage_exposure/_delta_log'
        if ($exists -and -not $RegenerateData) { Write-Info 'Test tables already exist - skipped' }
        else {
            Start-NotebookRun -WorkspaceId $S.test.id -NotebookId $S.testNb.id -Lakehouse $S.testLh -Parameters @{
                workspace_id = $S.test.id; lakehouse_id = $S.testLh.id; scale_factor = [double]$cfg.testScaleFactor; only_reset_thresholds = $false
            } | Out-Null
        }
        $S.testSqlEp = Get-LakehouseSqlEndpoint $S.test.id $S.testLh.id
        Update-SqlEndpointMetadata $S.test.id $S.testSqlEp.id
    } | Out-Null
}

# ================================================================== S13 deployment pipeline
if (-not $SkipPipeline -and -not $SkipTest) {
    Invoke-Step 'Deployment pipeline dp_fda_analyst (Development -> Test)' 'README > Setup > S13: Workspaces > Deployment pipelines > Create pipeline > dp_fda_analyst > 2 stages Development, Test > assign FDA-Analyst-Dev and FDA-Analyst-Test.' {
        # VERIFY: deployment pipelines REST (create with stages, assignWorkspace).
        $dp = Get-FabricList '/v1/deploymentPipelines' | Where-Object { $_.displayName -eq 'dp_fda_analyst' } | Select-Object -First 1
        if (-not $dp) {
            $dp = Invoke-Fabric -Method POST -Path '/v1/deploymentPipelines' -Body @{
                displayName = 'dp_fda_analyst'
                description = 'FDA demo: Development (FDA-Analyst-Dev) -> Test (FDA-Analyst-Test). SYNTHETIC DATA.'
                stages      = @(
                    @{ displayName = 'Development'; description = 'FDA-Analyst-Dev'; isPublic = $false },
                    @{ displayName = 'Test'; description = 'FDA-Analyst-Test'; isPublic = $false }
                )
            }
            Write-Ok "created dp_fda_analyst ($($dp.id))"
        }
        else { Write-Info "dp_fda_analyst exists ($($dp.id))" }
        $S.pipeline = $dp
        $stages = @(Get-FabricList "/v1/deploymentPipelines/$($dp.id)/stages" | Sort-Object order)
        $targets = @($devId, $S.test.id)
        for ($i = 0; $i -lt [Math]::Min($stages.Count, 2); $i++) {
            $st = $stages[$i]
            $current = if ($st.PSObject.Properties['workspaceId']) { $st.workspaceId } else { $null }
            if ($current -eq $targets[$i]) { Write-Info "stage $($st.displayName) already assigned"; continue }
            if ($current) { Write-Warn "stage $($st.displayName) holds another workspace ($current) - unassign it in the UI"; continue }
            Invoke-Fabric -Method POST -Path "/v1/deploymentPipelines/$($dp.id)/stages/$($st.id)/assignWorkspace" -Body @{ workspaceId = $targets[$i] } | Out-Null
            Write-Ok "stage $($st.displayName) <- $($targets[$i])"
        }
    } | Out-Null
}

# ================================================================== outputs
Write-Step 'Writing ./out/fda-environment.json'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$out = [ordered]@{
    generatedAt = (Get-Date).ToString('s')
    tenantId    = $cfg.tenantId
    capacityId  = $cfg.capacityId
    dev         = [ordered]@{
        workspaceName = $DevName
        workspaceId   = $devId
        items         = [ordered]@{
            lh_supervisory              = Get-Id $S.lh
            wh_analyst_sandbox          = Get-Id $S.wh
            nb_fda_00_generate_data     = Get-Id $S.notebooks['nb_fda_00_generate_data']
            nb_fda_01_analyst_explore   = Get-Id $S.notebooks['nb_fda_01_analyst_explore']
            nb_fda_02_land_late_filings = Get-Id $S.notebooks['nb_fda_02_land_late_filings']
            sm_fda_supervisory          = Get-Id $S.smDirect
            sm_fda_supervisory_import   = Get-Id $S.smImport
            df_fda_watch_thresholds     = Get-Id $S.dataflow
            rpt_fda_institution_return  = Get-Id $S.paginated
        }
        sqlEndpoint   = if ($S.sqlEp) { [ordered]@{ id = $S.sqlEp.id; connectionString = $S.sqlEp.connectionString; database = 'lh_supervisory' } } else { $null }
        warehouse     = [ordered]@{ connectionString = $S.whConnection; database = 'wh_analyst_sandbox' }
        scaleFactor   = $cfg.scaleFactor
    }
    test        = if ($S.test) { [ordered]@{ workspaceName = $TestName; workspaceId = $S.test.id; lh_supervisory = (Get-Id $S.testLh); nb_fda_00_generate_data = (Get-Id $S.testNb); scaleFactor = $cfg.testScaleFactor } } else { $null }
    deploymentPipeline = if ($S.pipeline) { [ordered]@{ name = 'dp_fda_analyst'; id = $S.pipeline.id } } else { $null }
    failedSteps = @($script:Failures)
}
$outPath = Join-Path $OutDir 'fda-environment.json'
$out | ConvertTo-Json -Depth 6 | Set-Content -Path $outPath -Encoding utf8
Write-Ok "-> $outPath"

$elapsed = (Get-Date) - $Started
Write-Host ''
Write-Host '================ Summary ================' -ForegroundColor Cyan
Write-Host ("Dev  : {0} ({1})" -f $DevName, $devId)
if ($S.sqlEp) { Write-Host ("SQL analytics endpoint: {0}  database lh_supervisory" -f $S.sqlEp.connectionString) }
if ($S.test) { Write-Host ("Test : {0} ({1})" -f $TestName, $S.test.id) }
Write-Host ''
Write-Host 'Remaining CLICK steps (README section 4):' -ForegroundColor Cyan
if (-not $S.importRefreshed -and -not $SkipImportModel) { Write-Host '  S10  sm_fda_supervisory_import: Data source credentials (OAuth2) + Refresh now' }
Write-Host '  S10  sm_fda_supervisory: check credentials (OAuth2, SSO) + Q&A on (needed for Prep data for AI)'
Write-Host '  S11  df_fda_watch_thresholds: configure connection, check preview, Save (destination: D5)'
Write-Host '  S14  rpt_fda_supervisory_overview: build the report (README spec, ~12 min); Prep data for AI (service) + Approved for Copilot + verified answer'
Write-Host '  S15  Connect FDA-Analyst-Dev to Git (GitHub <you>/fabric-analyst-workshop, folder /analyst-dev, branch main) + initial commit;'
Write-Host '       rehearse, capture fallback screenshots, then ./02-Reset-FdaDemo.ps1'
if ($script:Failures.Count -gt 0) {
    Write-Host ("[step] Finished in {0:n0} min with {1} failed step(s): {2}" -f $elapsed.TotalMinutes, $script:Failures.Count, ($script:Failures -join '; ')) -ForegroundColor Yellow
    Write-Host '       Use the printed README fallbacks, then rerun this script (it is idempotent).' -ForegroundColor Yellow
}
else {
    Write-Host ("[step] Finished in {0:n0} min." -f $elapsed.TotalMinutes) -ForegroundColor Green
}
