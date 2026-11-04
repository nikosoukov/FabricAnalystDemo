#Requires -Version 7.2
<#
    SYNTHETIC DATA · for training only · no OSFI data
    ------------------------------------------------------------------
    02-Reset-FdaDemo.ps1
    Puts FDA-Analyst-Dev back in the "before the session" state after a rehearsal:

      1. nb_fda_02_land_late_filings mode=reset  -> late filers' 2026 Q3 rows removed (30 of 40 reporting)
      2. nb_fda_00_generate_data only_reset_thresholds=True -> supervisory_watch_thresholds = v1,
         Files/reference holds only the v1 Excel file again (v2 upload from D5 removed)
      3. sql/30_wh_sandbox_setup.sql on wh_analyst_sandbox -> drops watchlist_2026q3, 5 analyst_notes rows
      4. SQL analytics endpoint metadata refresh, Direct Lake framing, Import model refresh (back to 30)
      5. Prints the manual checklist (Git, Copilot pages, Test stage content)

    Expected afterwards: Institutions Reporting 2026 Q3 = 30 on both models, Institutions Below CET1 Watch = 1.

    Examples:
      ./02-Reset-FdaDemo.ps1
      ./02-Reset-FdaDemo.ps1 -SkipModelRefresh
#>
[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'config.json'),
    [string]$EnvironmentPath = (Join-Path $PSScriptRoot 'out/fda-environment.json'),
    [switch]$SkipModelRefresh,
    [switch]$UseDeviceAuthentication
)

. (Join-Path $PSScriptRoot 'FdaCommon.ps1')
$Started = Get-Date

Write-Step 'Reading configuration'
$cfg = Read-FdaConfig $ConfigPath
Assert-Modules 'Az.Accounts', 'SqlServer'
$null = Connect-Fda -TenantId $cfg.tenantId -UseDeviceAuthentication:$UseDeviceAuthentication

$ws = Find-Workspace $cfg.devWorkspaceName
if (-not $ws) { throw "Workspace $($cfg.devWorkspaceName) not found. Run 01-Deploy-FdaEnvironment.ps1 first." }
$devId = $ws.id
$lh = Find-FabricItem $devId 'Lakehouse' 'lh_supervisory'
$nb00 = Find-FabricItem $devId 'Notebook' 'nb_fda_00_generate_data'
$nb02 = Find-FabricItem $devId 'Notebook' 'nb_fda_02_land_late_filings'
$wh = Find-FabricItem $devId 'Warehouse' 'wh_analyst_sandbox'
$smDirect = Find-FabricItem $devId 'SemanticModel' 'sm_fda_supervisory'
$smImport = Find-FabricItem $devId 'SemanticModel' 'sm_fda_supervisory_import'
Write-Info "dev=$devId lakehouse=$(Get-Id $lh)"

Invoke-Step 'Remove landed late filings (nb_fda_02 mode=reset)' 'README > Reset: open nb_fda_02_land_late_filings > set mode = "reset" in the parameters cell > Run all > set it back to "land".' {
    if (-not $nb02) { throw 'nb_fda_02_land_late_filings not found' }
    Start-NotebookRun -WorkspaceId $devId -NotebookId $nb02.id -Lakehouse $lh -Parameters @{
        mode = 'reset'; workspace_id = $devId; lakehouse_id = $lh.id; scale_factor = [double]$cfg.scaleFactor
    } | Out-Null
} | Out-Null

Invoke-Step 'Thresholds back to v1 + v1 Excel file (nb_fda_00 only_reset_thresholds=True)' 'README > Reset: open nb_fda_00_generate_data > set only_reset_thresholds = True > Run all > set it back to False. Delete Files/reference/supervisory_watch_thresholds_v2.xlsx by hand if it is still there.' {
    if (-not $nb00) { throw 'nb_fda_00_generate_data not found' }
    Start-NotebookRun -WorkspaceId $devId -NotebookId $nb00.id -Lakehouse $lh -Parameters @{
        workspace_id = $devId; lakehouse_id = $lh.id; scale_factor = [double]$cfg.scaleFactor; only_reset_thresholds = $true
    } | Out-Null
} | Out-Null

Invoke-Step 'Warehouse sandbox reset (sql/30_wh_sandbox_setup.sql)' 'README > Reset: wh_analyst_sandbox > New SQL query > paste sql/30_wh_sandbox_setup.sql > Run.' {
    $w = Invoke-Fabric -Path "/v1/workspaces/$devId/warehouses/$($wh.id)"
    Invoke-FabricSql -Server $w.properties.connectionString -Database 'wh_analyst_sandbox' -InputFile (Join-Path $script:KitRoot 'sql/30_wh_sandbox_setup.sql')
} | Out-Null

Invoke-Step 'SQL analytics endpoint metadata refresh' 'lh_supervisory > SQL analytics endpoint > Refresh.' {
    $sep = Get-LakehouseSqlEndpoint $devId $lh.id
    Update-SqlEndpointMetadata $devId $sep.id
    Start-Sleep -Seconds 15
} | Out-Null

if (-not $SkipModelRefresh) {
    Invoke-Step 'Refresh sm_fda_supervisory (Direct Lake framing) and sm_fda_supervisory_import (Import)' 'Open each semantic model > Refresh now. Import needs OAuth2 credentials (README S10).' {
        if ($smDirect) { Start-DatasetRefresh $devId $smDirect.id -Wait -TimeoutMinutes 10 }
        if ($smImport) { Start-DatasetRefresh $devId $smImport.id -Wait -TimeoutMinutes 20 }
    } | Out-Null
}

Write-Host ''
Write-Host '================ Manual reset checklist ================' -ForegroundColor Cyan
Write-Host '[ ] DAX query view, both models: Institutions Reporting 2026 Q3 = 30; Institutions Below CET1 Watch 2026 Q3 = 1'
Write-Host '[ ] Git (D9): FDA-Analyst-Dev > Source control shows 0 changes. If the rehearsal committed a description change,'
Write-Host '    revert it (edit the description back, commit) so D9 shows exactly 1 change live.'
Write-Host '[ ] Copilot (D7): delete report pages Copilot created in rpt_fda_supervisory_overview; start a new Copilot chat.'
Write-Host '[ ] Dataflow (D5): df_fda_watch_thresholds destination - keep it (fallback) or remove it if you set it live.'
Write-Host '[ ] Test stage (D9): if you deployed in rehearsal, either leave FDA-Analyst-Test as is (deploy shows "no changes")'
Write-Host '    or delete sm_fda_supervisory and rpt_fda_supervisory_overview from FDA-Analyst-Test so Compare shows "new" items.'
Write-Host '[ ] nb_fda_01: table analyst_outliers can stay (it is overwritten live). Stop Spark sessions in the Monitor hub.'
Write-Host '[ ] Excel (D8): close the Analyze in Excel workbook; delete downloaded exports from the desktop.'
$elapsed = (Get-Date) - $Started
if ($script:Failures.Count -gt 0) {
    Write-Host ("[step] Reset finished in {0:n0} min with failures: {1}" -f $elapsed.TotalMinutes, ($script:Failures -join '; ')) -ForegroundColor Yellow
}
else { Write-Host ("[step] Reset finished in {0:n0} min." -f $elapsed.TotalMinutes) -ForegroundColor Green }
