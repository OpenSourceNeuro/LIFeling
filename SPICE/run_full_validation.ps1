[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$NgspiceBinary = "auto",
    [ValidateSet("hybrid", "portable", "vendor")]
    [string]$Profile = "hybrid",
    [switch]$FetchVendorModels,
    [switch]$GenerateOnly,
    [switch]$SkipTests,
    [ValidateRange(1, 86400)]
    [int]$SimulationTimeoutSeconds = 180,
    [string]$RepositoryCommit = "272b9b74c9f78c5c64ee9d9609b1ea035339ad1e"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Spice = Join-Path $Root "Spice.py"
$Netlist = Join-Path $Root "sources\LIFeling.net"
$Reports = Join-Path $Root "reports"
$Generated = Join-Path $Root "generated"

function Invoke-Checked {
    param([string[]]$Arguments)
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $Python $($Arguments -join ' ')"
    }
}

Write-Host "LIFeling physical-netlist SPICE validation" -ForegroundColor Cyan
Write-Host "Root: $Root"
Write-Host "Profile: $Profile"

Invoke-Checked @("-m", "py_compile", $Spice)
if (-not $SkipTests) {
    Invoke-Checked @("-m", "unittest", "discover", "-s", (Join-Path $Root "tests"), "-v")
}

if ($FetchVendorModels) {
    Invoke-Checked @($Spice, "fetch-models", "--profile", $Profile)
}

$Common = @(
    $Spice,
    $(if ($GenerateOnly) { "generate" } else { "run" }),
    "--suite",
    "--profile", $Profile,
    "--netlist", $Netlist,
    "--report-dir", $Reports,
    "--output-dir", $Generated,
    "--ngspice-binary", $NgspiceBinary,
    "--timeout-seconds", $SimulationTimeoutSeconds,
    "--repository-commit", $RepositoryCommit,
    "--skip-static-tests"
)
Invoke-Checked $Common

$Summary = Join-Path $Reports "validation_summary.json"
if (-not (Test-Path $Summary)) {
    throw "Validation summary was not created: $Summary"
}
$Status = Get-Content $Summary -Raw | ConvertFrom-Json
Write-Host "Components: $($Status.component_count); nets: $($Status.net_count)"
Write-Host "Decks: $($Status.decks_generated); passed: $($Status.runs_passed); failed: $($Status.runs_failed); not executed: $($Status.runs_not_executed)"
if (-not $GenerateOnly -and $Status.runs_not_executed -gt 0) {
    throw "One or more runs were not executed. Set -NgspiceBinary explicitly if ngspice is not on PATH."
}
if ($Status.runs_failed -gt 0 -or $Status.blocking_topology_failures -gt 0) {
    throw "LIFeling validation failed. Inspect reports\validation_report.md and generated ngspice logs."
}
Write-Host "Validation artifacts: $Reports" -ForegroundColor Green
