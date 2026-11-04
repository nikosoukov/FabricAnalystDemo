#Requires -Version 7.2
<#
    SYNTHETIC DATA · for training only · no OSFI data
    ------------------------------------------------------------------
    99-Remove-FdaEnvironment.ps1
    Deletes the demo environment: first the deployment pipeline dp_fda_analyst (stages unassigned),
    then FDA-Analyst-Test and FDA-Analyst-Dev with everything in them.
    Asks you to type each workspace name unless -Force.
    Does NOT touch the Git repo, tenant settings or the capacity (pause it yourself).

    Examples:
      ./99-Remove-FdaEnvironment.ps1
      ./99-Remove-FdaEnvironment.ps1 -Force
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'config.json'),
    [switch]$Force,
    [switch]$UseDeviceAuthentication
)

. (Join-Path $PSScriptRoot 'FdaCommon.ps1')
$cfg = Read-FdaConfig $ConfigPath
Assert-Modules 'Az.Accounts'
$null = Connect-Fda -TenantId $cfg.tenantId -UseDeviceAuthentication:$UseDeviceAuthentication

# ---- deployment pipeline first (a workspace assigned to a stage can't be deleted cleanly)
Write-Step 'Deployment pipeline dp_fda_analyst'
$dp = Get-FabricList '/v1/deploymentPipelines' | Where-Object { $_.displayName -eq 'dp_fda_analyst' } | Select-Object -First 1
if (-not $dp) { Write-Ok 'not found - nothing to do' }
else {
    $answer = if ($Force -or $WhatIfPreference) { 'dp_fda_analyst' } else { Read-Host 'Type dp_fda_analyst to delete the pipeline' }
    if ($answer -ne 'dp_fda_analyst') { Write-Warn 'cancelled - pipeline kept' }
    elseif ($PSCmdlet.ShouldProcess('dp_fda_analyst', 'Unassign stages and delete deployment pipeline')) {
        try {
            foreach ($st in @(Get-FabricList "/v1/deploymentPipelines/$($dp.id)/stages")) {
                if ($st.PSObject.Properties['workspaceId'] -and $st.workspaceId) {
                    # VERIFY: unassignWorkspace endpoint
                    Invoke-Fabric -Method POST -Path "/v1/deploymentPipelines/$($dp.id)/stages/$($st.id)/unassignWorkspace" | Out-Null
                    Write-Ok "unassigned stage $($st.displayName)"
                }
            }
            Invoke-Fabric -Method DELETE -Path "/v1/deploymentPipelines/$($dp.id)" | Out-Null
            Write-Ok 'deleted dp_fda_analyst'
        }
        catch {
            Write-Warn "pipeline delete failed: $($_.Exception.Message)"
            Write-Warn 'Fallback: Workspaces > Deployment pipelines > dp_fda_analyst > ... > Delete pipeline.'
        }
    }
}

# ---- workspaces (Test first, then Dev)
foreach ($name in @($cfg.testWorkspaceName, $cfg.devWorkspaceName)) {
    Write-Step "Workspace $name"
    $ws = Find-Workspace $name
    if (-not $ws) { Write-Ok 'not found - nothing to do'; continue }
    $items = @(Get-FabricList "/v1/workspaces/$($ws.id)/items")
    Write-Host "  $($ws.id) contains $($items.Count) items:" -ForegroundColor Gray
    $items | Sort-Object type, displayName | ForEach-Object { Write-Host "    - $($_.type): $($_.displayName)" -ForegroundColor Gray }
    if (-not $Force -and -not $WhatIfPreference) {
        $answer = Read-Host "Type the workspace name ($name) to delete it"
        if ($answer -ne $name) { Write-Warn 'cancelled'; continue }
    }
    if ($PSCmdlet.ShouldProcess($name, 'Delete workspace and all items')) {
        try {
            Invoke-Fabric -Method DELETE -Path "/v1/workspaces/$($ws.id)" | Out-Null
            Write-Ok "deleted $name"
        }
        catch { Write-Warn "delete failed: $($_.Exception.Message). Fallback: workspace > Workspace settings > General > Remove this workspace." }
    }
}
Write-Step 'Done. Also: disconnect/delete the Git repo fabric-analyst-workshop if you no longer need it, revert tenant settings you changed, and pause the capacity.'
