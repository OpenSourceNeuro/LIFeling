<#
.SYNOPSIS
    Run the LIFeling full-schematic SPICE validation suite.

.DESCRIPTION
    Runs a practical validation battery for the current LIFeling Spice.py model.
    All generated decks, raw ngspice CSV files, parsed CSV files, diagnostics,
    plots, companion Vm_Int/Vm_Ext-only plots, coverage reports, and console logs
    are written under .\LIFeling_pyspice_output by default.

    The suite assumes the new full-schematic Spice.py interface:
      - no reduced --stage selection is needed;
      - RV4 always drives the real capacitor-selector model;
      - ngspice is used when --run is passed;
      - each simulation writes a full plot and a companion *_vmint_vmext.png plot.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\run_full_validation.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\run_full_validation.ps1 `
      -PythonExe ".\.venv\Scripts\python.exe" `
      -SpicePy ".\Spice.py" `
      -NgspiceBinary "C:\Spice64\bin\ngspice.exe"

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\run_full_validation.ps1 -Quick

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\run_full_validation.ps1 -ContinueOnError -SkipKnobSweeps
#>

param(
    [string]$PythonExe = ".\.venv\Scripts\python.exe",
    [string]$SpicePy = ".\Spice.py",
    [string]$NgspiceBinary = "auto",
    [string]$OutputDir = ".\LIFeling_pyspice_output",
    [string]$LogDir = "",
    [string]$ReadmePath = ".\README.md",
    [switch]$NoReadmeUpdate,
    [switch]$ContinueOnError,
    [switch]$Quick,
    [switch]$SkipKnobSweeps,
    [switch]$SkipSynapseSweeps,
    [switch]$SkipStressRuns,

    # Backward-compatible switches from the previous validation script.
    [switch]$SkipRV123Sweep,
    [switch]$SkipRV5Sweep,
    [switch]$SkipLongSynapseSweep
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

function Resolve-ToolPath {
    param([string]$PathOrCommand)
    if ([string]::IsNullOrWhiteSpace($PathOrCommand)) { throw "Empty path/command." }
    if (Test-Path -LiteralPath $PathOrCommand) { return (Resolve-Path -LiteralPath $PathOrCommand).Path }
    return $PathOrCommand
}

function Quote-Arg {
    param([string]$Arg)
    if ($null -eq $Arg) { return '""' }
    $s = [string]$Arg
    if ($s.Length -eq 0) { return '""' }
    if ($s -match '[\s"]') { return '"' + ($s -replace '"', '\"') + '"' }
    return $s
}

function Join-Args {
    param([string[]]$Items)
    return (($Items | ForEach-Object { Quote-Arg $_ }) -join " ")
}

function Append-Line {
    param([string]$Path, [string]$Text = "")
    Add-Content -LiteralPath $Path -Value $Text -Encoding UTF8
}

function Invoke-LoggedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [string]$SuiteLog
    )

    $runLog = Join-Path $script:ResolvedLogDir ("{0}.console.txt" -f $Name)
    Remove-Item -LiteralPath $runLog -ErrorAction SilentlyContinue

    $argString = Join-Args $Arguments
    $commandLine = "$(Quote-Arg $FilePath) $argString"
    $start = Get-Date

    Write-Host ""
    Write-Host ("=" * 100)
    Write-Host "RUN: $Name"
    Write-Host "CMD: $commandLine"
    Write-Host ("=" * 100)

    Append-Line $runLog ("RUN: {0}" -f $Name)
    Append-Line $runLog ("START: {0:o}" -f $start)
    Append-Line $runLog ("WORKDIR: {0}" -f $WorkingDirectory)
    Append-Line $runLog ("COMMAND: {0}" -f $commandLine)
    Append-Line $runLog ""

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = $argString
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    [void]$proc.Start()
    $stdoutText = $proc.StandardOutput.ReadToEnd()
    $stderrText = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()
    $exitCode = $proc.ExitCode

    $end = Get-Date
    $elapsed = New-TimeSpan -Start $start -End $end

    if (-not [string]::IsNullOrEmpty($stdoutText)) {
        $stdoutText | Tee-Object -FilePath $runLog -Append | Write-Host
    }
    if (-not [string]::IsNullOrEmpty($stderrText)) {
        Append-Line $runLog ""
        Append-Line $runLog "--- STDERR ---"
        $stderrText | Tee-Object -FilePath $runLog -Append | Write-Host
    }

    Append-Line $runLog ""
    Append-Line $runLog ("END: {0:o}" -f $end)
    Append-Line $runLog ("ELAPSED: {0:n1} s" -f $elapsed.TotalSeconds)
    Append-Line $runLog ("EXIT_CODE: {0}" -f $exitCode)

    if ($exitCode -eq 0) { $status = "PASS" } else { $status = "FAIL" }
    Append-Line $SuiteLog ("{0}`t{1}`tExit={2}`tElapsed={3:n1}s`tLog={4}" -f $status, $Name, $exitCode, $elapsed.TotalSeconds, $runLog)

    Write-Host ""
    Write-Host ("{0}: {1}  exit={2}  elapsed={3:n1}s" -f $status, $Name, $exitCode, $elapsed.TotalSeconds)
    Write-Host "Log: $runLog"

    if (($exitCode -ne 0) -and (-not $ContinueOnError)) {
        Write-Host ""
        Write-Host "Last lines from failed run log:"
        Get-Content -LiteralPath $runLog -Tail 100 -ErrorAction SilentlyContinue | Write-Host
        throw "Validation run failed: $Name. See $runLog"
    }

    return $exitCode
}

function Test-SuiteLogReady {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $content = Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue
    if ($null -eq $content) { return $false }
    return (($content -match '(?m)^END:') -and ($content -match '(?m)^TOTAL RUNS:') -and ($content -match '(?m)^FAILED RUNS:'))
}

function Copy-LatestSuiteLogs {
    param(
        [string]$SourcePath,
        [string[]]$Destinations
    )
    foreach ($dest in $Destinations) {
        if ([string]::IsNullOrWhiteSpace($dest)) { continue }
        $parent = Split-Path -Parent $dest
        if (-not [string]::IsNullOrWhiteSpace($parent) -and -not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Path $parent | Out-Null
        }
        Copy-Item -LiteralPath $SourcePath -Destination $dest -Force -ErrorAction SilentlyContinue
    }
}

function Add-PythonRun {
    param([string]$Name, [string[]]$RunArgs)
    [void]$script:Runs.Add(@{ Name = $Name; Args = @($RunArgs) })
}

function Add-SpiceWriteOnlyRun {
    param([string]$Name, [string[]]$RunArgs)
    [void]$script:Runs.Add(@{ Name = $Name; Args = @($SpicePy, "--write-only", "--run-label", $Name) + @($RunArgs) })
}

function Add-SpiceRun {
    param([string]$Name, [string[]]$RunArgs)
    [void]$script:Runs.Add(@{ Name = $Name; Args = @($SpicePy, "--run", "--run-label", $Name) + @($RunArgs) })
}

# Backward-compatible skip mapping.
if ($SkipRV123Sweep) { $SkipKnobSweeps = $true }
if ($SkipRV5Sweep) { $SkipSynapseSweeps = $true }
if ($SkipLongSynapseSweep) { $SkipStressRuns = $true }
if ($Quick) {
    $SkipKnobSweeps = $true
    $SkipSynapseSweeps = $true
    $SkipStressRuns = $true
}

$PythonExe = Resolve-ToolPath $PythonExe
$SpicePy = Resolve-ToolPath $SpicePy
if (-not (Test-Path -LiteralPath $SpicePy)) { throw "Cannot find Spice.py at: $SpicePy" }

$WorkDir = Split-Path -Parent $SpicePy
if ([string]::IsNullOrWhiteSpace($WorkDir)) { $WorkDir = (Get-Location).Path }

if (-not (Test-Path -LiteralPath $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir | Out-Null }
$ResolvedOutputDir = (Resolve-Path -LiteralPath $OutputDir).Path
if ([System.IO.Path]::IsPathRooted($ReadmePath)) {
    $ResolvedReadmePath = $ReadmePath
}
else {
    $ResolvedReadmePath = Join-Path $WorkDir $ReadmePath
}

$ReadmeParent = Split-Path -Parent $ResolvedReadmePath
if (-not [string]::IsNullOrWhiteSpace($ReadmeParent) -and -not (Test-Path -LiteralPath $ReadmeParent)) {
    New-Item -ItemType Directory -Path $ReadmeParent | Out-Null
}

if (Test-Path -LiteralPath $ResolvedReadmePath) {
    $ResolvedReadmePath = (Resolve-Path -LiteralPath $ResolvedReadmePath).Path
}

if ([string]::IsNullOrWhiteSpace($LogDir)) { $LogDir = Join-Path $ResolvedOutputDir "validation_logs" }
if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$script:ResolvedLogDir = (Resolve-Path -LiteralPath $LogDir).Path

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$SuiteLog = Join-Path $script:ResolvedLogDir ("validation_suite_{0}.txt" -f $stamp)
$LatestSuiteLog = Join-Path $script:ResolvedLogDir "validation_suite_latest.txt"
$LatestSuiteLogRoot = Join-Path $ResolvedOutputDir "validation_suite_latest.txt"

Append-Line $SuiteLog "LIFeling SPICE validation suite"
Append-Line $SuiteLog ("START: {0:o}" -f (Get-Date))
Append-Line $SuiteLog ("PythonExe: {0}" -f $PythonExe)
Append-Line $SuiteLog ("SpicePy: {0}" -f $SpicePy)
Append-Line $SuiteLog ("WorkDir: {0}" -f $WorkDir)
Append-Line $SuiteLog ("OutputDir: {0}" -f $ResolvedOutputDir)
Append-Line $SuiteLog ("ReadmePath: {0}" -f $ResolvedReadmePath)
Append-Line $SuiteLog ("NoReadmeUpdate: {0}" -f $NoReadmeUpdate.IsPresent)
Append-Line $SuiteLog ("NgspiceBinary: {0}" -f $NgspiceBinary)
Append-Line $SuiteLog ("ContinueOnError: {0}" -f $ContinueOnError.IsPresent)
Append-Line $SuiteLog ("Quick: {0}" -f $Quick.IsPresent)
Append-Line $SuiteLog ("SkipKnobSweeps: {0}" -f $SkipKnobSweeps.IsPresent)
Append-Line $SuiteLog ("SkipSynapseSweeps: {0}" -f $SkipSynapseSweeps.IsPresent)
Append-Line $SuiteLog ("SkipStressRuns: {0}" -f $SkipStressRuns.IsPresent)
Append-Line $SuiteLog ""
Append-Line $SuiteLog "Every ngspice run should generate both a full plot and a companion *_vmint_vmext.png plot."
Append-Line $SuiteLog ""
Append-Line $SuiteLog "STATUS`tRUN`tEXIT/ELAPSED/LOG"

$NgArg = @()
if (-not [string]::IsNullOrWhiteSpace($NgspiceBinary)) {
    $NgArg = @("--ngspice-binary", $NgspiceBinary)
}

$BaseCoin = @(
    "--output-dir", $ResolvedOutputDir
) + $NgArg + @(
    "--supply-mode", "coin",
    "--vbat", "3",
    "--rbat", "50",
    "--startup-mode", "operating",
    "--ignore-start-ms", "20",
    "--rv2", "0.5",
    "--rv3", "0.8",
    "--rv4", "0.3",
    "--tstep", "10u",
    "--maxstep", "10u"
)

$Subthreshold = @("--rv1", "0.35")
$SelfSpiking = @("--rv1", "0.70")

$SingleSynTiming = @(
    "--syn1-delay", "150m", "--syn2-delay", "180m", "--syn3-delay", "210m", "--syn4-delay", "240m",
    "--syn1-width", "5m", "--syn2-width", "5m", "--syn3-width", "5m", "--syn4-width", "5m",
    "--syn1-period", "10", "--syn2-period", "10", "--syn3-period", "10", "--syn4-period", "10"
)

$RepeatingSynTiming = @(
    "--syn1-delay", "150m", "--syn2-delay", "180m", "--syn3-delay", "210m", "--syn4-delay", "240m",
    "--syn1-width", "5m", "--syn2-width", "5m", "--syn3-width", "5m", "--syn4-width", "5m",
    "--syn1-period", "100m", "--syn2-period", "100m", "--syn3-period", "100m", "--syn4-period", "100m"
)

$SimultaneousSynTiming = @(
    "--syn1-delay", "150m", "--syn2-delay", "150m", "--syn3-delay", "150m", "--syn4-delay", "150m",
    "--syn1-width", "5m", "--syn2-width", "5m", "--syn3-width", "5m", "--syn4-width", "5m",
    "--syn1-period", "100m", "--syn2-period", "100m", "--syn3-period", "100m", "--syn4-period", "100m"
)

$Runs = New-Object System.Collections.ArrayList

Add-PythonRun -Name "00_python_compile" -RunArgs @("-m", "py_compile", $SpicePy)

Add-SpiceWriteOnlyRun "01_write_only_full_schematic_debug" (@(
    "--output-dir", $ResolvedOutputDir
) + $NgArg + @(
    "--trace-debug",
    "--tstop", "100m"
))

Add-SpiceRun "02_baseline_self_spiking_coin" ($BaseCoin + $SelfSpiking + @(
    "--tstop", "1.5"
))

Add-SpiceRun "03_debug_self_spiking_short" ($BaseCoin + $SelfSpiking + @(
    "--trace-debug",
    "--tstop", "400m"
))

Add-SpiceRun "04_cold_start_self_spiking_coin" (@(
    "--output-dir", $ResolvedOutputDir
) + $NgArg + @(
    "--supply-mode", "coin", "--vbat", "3", "--rbat", "50",
    "--startup-mode", "cold", "--ignore-start-ms", "20",
    "--rv1", "0.70", "--rv2", "0.5", "--rv3", "0.8", "--rv4", "0.3",
    "--tstop", "800m", "--tstep", "10u", "--maxstep", "10u"
))

Add-SpiceRun "05_quiet_subthreshold_no_synapse" ($BaseCoin + $Subthreshold + @(
    "--tstop", "400m"
))

Add-SpiceRun "06_synapse_midpoint_zero_effect_single" ($BaseCoin + $Subthreshold + @(
    "--syn-all-enable", "--rv5", "0.5", "--rv6", "0.5", "--rv7", "0.5", "--rv8", "0.5", "--rv9", "0.5"
) + $SingleSynTiming + @(
    "--tstop", "400m"
))

Add-SpiceRun "07_synapse_excitatory_single_high" ($BaseCoin + $Subthreshold + @(
    "--syn-all-enable", "--rv5", "0.5", "--rv6", "1.0", "--rv7", "1.0", "--rv8", "1.0", "--rv9", "1.0"
) + $SingleSynTiming + @(
    "--tstop", "400m"
))

Add-SpiceRun "08_synapse_inhibitory_single_low" ($BaseCoin + $SelfSpiking + @(
    "--syn-all-enable", "--rv5", "0.5", "--rv6", "0.0", "--rv7", "0.0", "--rv8", "0.0", "--rv9", "0.0"
) + $SingleSynTiming + @(
    "--tstop", "500m"
))

Add-SpiceRun "09_external_stimulus_positive_subthreshold" ($BaseCoin + $Subthreshold + @(
    "--stimulus-ext", "0.2",
    "--tstop", "400m"
))

Add-SpiceRun "10_external_stimulus_negative_subthreshold" ($BaseCoin + $Subthreshold + @(
    "--stimulus-ext", "-0.2",
    "--tstop", "400m"
))

Add-SpiceRun "11_ideal_supply_reference_run" (@(
    "--output-dir", $ResolvedOutputDir
) + $NgArg + @(
    "--supply-mode", "ideal", "--vdd-ideal", "3",
    "--startup-mode", "operating", "--ignore-start-ms", "20",
    "--rv1", "0.70", "--rv2", "0.5", "--rv3", "0.8", "--rv4", "0.3",
    "--tstop", "500m", "--tstep", "10u", "--maxstep", "10u"
))

Add-SpiceRun "12_low_battery_high_impedance_stress" (@(
    "--output-dir", $ResolvedOutputDir
) + $NgArg + @(
    "--supply-mode", "coin", "--vbat", "2.7", "--rbat", "120",
    "--startup-mode", "operating", "--ignore-start-ms", "20",
    "--rv1", "0.70", "--rv2", "0.5", "--rv3", "0.8", "--rv4", "0.3",
    "--tstop", "500m", "--tstep", "10u", "--maxstep", "10u"
))

if (-not $SkipStressRuns) {
    Add-SpiceRun "13_synapse_repeating_staggered_high_stress" ($BaseCoin + $SelfSpiking + @(
        "--syn-all-enable", "--rv5", "0.5", "--rv6", "1.0", "--rv7", "1.0", "--rv8", "1.0", "--rv9", "1.0"
    ) + $RepeatingSynTiming + @(
        "--tstop", "1.5"
    ))

    Add-SpiceRun "14_synapse_repeating_simultaneous_high_stress" ($BaseCoin + $SelfSpiking + @(
        "--syn-all-enable", "--rv5", "0.5", "--rv6", "1.0", "--rv7", "1.0", "--rv8", "1.0", "--rv9", "1.0"
    ) + $SimultaneousSynTiming + @(
        "--tstop", "1.5"
    ))

    Add-SpiceRun "15_synapse_repeating_simultaneous_low_stress" ($BaseCoin + $SelfSpiking + @(
        "--syn-all-enable", "--rv5", "0.5", "--rv6", "0.0", "--rv7", "0.0", "--rv8", "0.0", "--rv9", "0.0"
    ) + $SimultaneousSynTiming + @(
        "--tstop", "1.5"
    ))
}

if (-not $SkipKnobSweeps) {
    foreach ($rv1 in @("0.25", "0.35", "0.50", "0.70", "0.90")) {
        $tag = $rv1.Replace(".", "p")
        Add-SpiceRun ("rv1_leak_threshold_sweep_{0}" -f $tag) ($BaseCoin + @(
            "--rv1", $rv1,
            "--tstop", "600m"
        ))
    }

    foreach ($rv2 in @("0.20", "0.50", "0.80")) {
        $tag = $rv2.Replace(".", "p")
        Add-SpiceRun ("rv2_leak_rate_sweep_{0}" -f $tag) ($BaseCoin + $SelfSpiking + @(
            "--rv2", $rv2,
            "--tstop", "800m"
        ))
    }

    foreach ($rv3 in @("0.20", "0.50", "0.80", "1.00")) {
        $tag = $rv3.Replace(".", "p")
        Add-SpiceRun ("rv3_adaptation_sweep_{0}" -f $tag) ($BaseCoin + $SelfSpiking + @(
            "--rv3", $rv3,
            "--tstop", "800m"
        ))
    }

    foreach ($rv4 in @("0.10", "0.30", "0.50", "0.70", "0.90")) {
        $tag = $rv4.Replace(".", "p")
        Add-SpiceRun ("rv4_capacitance_bank_sweep_{0}" -f $tag) ($BaseCoin + $SelfSpiking + @(
            "--rv4", $rv4,
            "--tstop", "800m"
        ))
    }
}

if (-not $SkipSynapseSweeps) {
    foreach ($rv5 in @("0.10", "0.30", "0.50", "0.80", "1.00")) {
        $tag = $rv5.Replace(".", "p")
        Add-SpiceRun ("rv5_synaptic_decay_sweep_{0}" -f $tag) ($BaseCoin + $Subthreshold + @(
            "--syn-all-enable", "--rv5", $rv5, "--rv6", "1.0", "--rv7", "1.0", "--rv8", "1.0", "--rv9", "1.0"
        ) + $SingleSynTiming + @(
            "--tstop", "500m"
        ))
    }

    foreach ($level in @("0.00", "0.25", "0.50", "0.75", "1.00")) {
        $tag = $level.Replace(".", "p")
        Add-SpiceRun ("synaptic_sign_weight_sweep_{0}" -f $tag) ($BaseCoin + $Subthreshold + @(
            "--syn-all-enable", "--rv5", "0.5", "--rv6", $level, "--rv7", $level, "--rv8", $level, "--rv9", $level
        ) + $SingleSynTiming + @(
            "--tstop", "500m"
        ))
    }
}

$failed = 0
$total = $Runs.Count
$index = 0

foreach ($run in $Runs) {
    $index += 1
    $name = "{0:D2}_{1}" -f $index, $run.Name
    try {
        $exit = Invoke-LoggedProcess -Name $name -FilePath $PythonExe -Arguments ([string[]]$run.Args) -WorkingDirectory $WorkDir -SuiteLog $SuiteLog
        if ($exit -ne 0) { $failed += 1 }
    }
    catch {
        $failed += 1
        Append-Line $SuiteLog ("FAIL`t{0}`tException={1}" -f $name, $_.Exception.Message)
        Write-Host ""
        Write-Host "FAILED: $name"
        Write-Host $_.Exception.Message
        if (-not $ContinueOnError) {
            Append-Line $SuiteLog ""
            Append-Line $SuiteLog ("ABORTED: {0:o}" -f (Get-Date))
            Copy-LatestSuiteLogs -SourcePath $SuiteLog -Destinations @($LatestSuiteLog, $LatestSuiteLogRoot)
            throw
        }
    }
}

$SummaryCsv = Join-Path $ResolvedOutputDir "validation_diagnostics_summary.csv"

try {
    $diagFiles = Get-ChildItem -LiteralPath $ResolvedOutputDir -Filter "*_diagnostics.csv" -File -ErrorAction SilentlyContinue | Sort-Object Name
    if ($diagFiles.Count -gt 0) {
        $allRows = foreach ($file in $diagFiles) { Import-Csv -LiteralPath $file.FullName }
        $allRows | Export-Csv -LiteralPath $SummaryCsv -NoTypeInformation -Encoding UTF8
        Append-Line $SuiteLog ("Diagnostics summary: {0}" -f $SummaryCsv)
    }
    else {
        Append-Line $SuiteLog "WARNING: No *_diagnostics.csv files found; validation_diagnostics_summary.csv was not created."
    }
}
catch {
    Append-Line $SuiteLog ("WARNING: Could not build diagnostics summary: {0}" -f $_.Exception.Message)
}

# Write the suite result before generating the README, so Spice.py can read the current run status.
Append-Line $SuiteLog ""
Append-Line $SuiteLog ("END: {0:o}" -f (Get-Date))
Append-Line $SuiteLog ("TOTAL RUNS: {0}" -f $total)
Append-Line $SuiteLog ("FAILED RUNS: {0}" -f $failed)
Copy-LatestSuiteLogs -SourcePath $SuiteLog -Destinations @($LatestSuiteLog, $LatestSuiteLogRoot)

if (-not $NoReadmeUpdate) {
    try {
        if ((-not (Test-SuiteLogReady -Path $LatestSuiteLog)) -or (-not (Test-SuiteLogReady -Path $LatestSuiteLogRoot))) {
            throw "README update skipped because validation_suite_latest.txt is not finalised with END, TOTAL RUNS, and FAILED RUNS."
        }
        Append-Line $SuiteLog "README update starting from finalised validation_suite_latest.txt."
        Write-Host "README update starting from finalised validation suite log."

        $ReadmeArgs = @(
            $SpicePy,
            "--update-readme-only",
            "--output-dir", $ResolvedOutputDir,
            "--readme-path", $ResolvedReadmePath
        )

        [void](Invoke-LoggedProcess `
            -Name "update_readme_validation_snapshot" `
            -FilePath $PythonExe `
            -Arguments $ReadmeArgs `
            -WorkingDirectory $WorkDir `
            -SuiteLog $SuiteLog)

        Append-Line $SuiteLog ("README updated: {0}" -f $ResolvedReadmePath)
        Copy-LatestSuiteLogs -SourcePath $SuiteLog -Destinations @($LatestSuiteLog, $LatestSuiteLogRoot)
        Write-Host "README updated: $ResolvedReadmePath"
    }
    catch {
        Append-Line $SuiteLog ("WARNING: Could not update README: {0}" -f $_.Exception.Message)
        Copy-LatestSuiteLogs -SourcePath $SuiteLog -Destinations @($LatestSuiteLog, $LatestSuiteLogRoot)
        Write-Host "WARNING: Could not update README: $($_.Exception.Message)"
        if (-not $ContinueOnError) { throw }
    }
}
else {
    Append-Line $SuiteLog "README update skipped because -NoReadmeUpdate was provided."
    Copy-LatestSuiteLogs -SourcePath $SuiteLog -Destinations @($LatestSuiteLog, $LatestSuiteLogRoot)
}

Write-Host ""
Write-Host ("=" * 100)
Write-Host "Validation suite complete"
Write-Host "Total runs:       $total"
Write-Host "Failures:         $failed"
Write-Host "Output folder:    $ResolvedOutputDir"
Write-Host "README:           $ResolvedReadmePath"
Write-Host "Suite log:        $SuiteLog"
Write-Host "Latest suite log: $LatestSuiteLog"
Write-Host "Latest suite log in output: $LatestSuiteLogRoot"
Write-Host "Run logs:         $script:ResolvedLogDir"
if (Test-Path -LiteralPath $SummaryCsv) { Write-Host "Diagnostics CSV:  $SummaryCsv" }
Write-Host ("=" * 100)

if ($failed -ne 0) { exit 1 }
exit 0
