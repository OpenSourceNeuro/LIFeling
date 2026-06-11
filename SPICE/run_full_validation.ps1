<#
.SYNOPSIS
    Run the Spiky-Lu.i SPICE validation suite.

.DESCRIPTION
    Runs a practical validation battery for the current Spice.py model:
      - Python syntax check
      - threshold-reset/AP/Spike_Out path
      - Vm peak injection and Vm_Ext output path
      - reset/adaptation baseline
      - cold-start stress
      - synapse-present/no-pulse check
      - simultaneous synapse stress checks
      - stimulus path check
      - RV1/RV2/RV3 behavioural sweeps, unless -SkipRV123Sweep is used
      - RV5 synaptic decay sweep, unless -SkipRV5Sweep is used
      - staggered RV6-RV9 synaptic range sweep, unless -SkipLongSynapseSweep is used

    Deliberately removed from this validation suite:
      - buffered V_Leak_Ref_Max validation
      - legacy direct-reference comparison

    Spice.py itself generates compact CSV/PNG outputs and one *_results.txt file
    per run. This PowerShell script additionally saves one console log per run
    and one suite-level summary log.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\run_spiky_full_validation.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\run_spiky_full_validation.ps1 `
      -PythonExe ".\.venv\Scripts\python.exe" `
      -SpicePy ".\Spice.py" `
      -NgspiceBinary "C:\Users\mzimm\Documents\Spice64\bin\ngspice.EXE"

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\run_spiky_full_validation.ps1 `
      -SkipRV123Sweep `
      -SkipRV5Sweep `
      -SkipLongSynapseSweep
#>

param(
    [string]$PythonExe = ".\.venv\Scripts\python.exe",
    [string]$SpicePy = ".\Spice.py",
    [string]$NgspiceBinary = "auto",
    [string]$LogDir = ".\spiky_validation_logs",
    [switch]$ContinueOnError,
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
    $stdoutTmp = Join-Path $script:ResolvedLogDir ("{0}.stdout.tmp" -f $Name)
    $stderrTmp = Join-Path $script:ResolvedLogDir ("{0}.stderr.tmp" -f $Name)
    Remove-Item -LiteralPath $runLog, $stdoutTmp, $stderrTmp -ErrorAction SilentlyContinue

    $argString = Join-Args $Arguments
    $commandLine = "$(Quote-Arg $FilePath) $argString"
    $start = Get-Date

    Write-Host ""
    Write-Host ("=" * 90)
    Write-Host "RUN: $Name"
    Write-Host "CMD: $commandLine"
    Write-Host ("=" * 90)

    Append-Line $runLog ("RUN: {0}" -f $Name)
    Append-Line $runLog ("START: {0:o}" -f $start)
    Append-Line $runLog ("WORKDIR: {0}" -f $WorkingDirectory)
    Append-Line $runLog ("COMMAND: {0}" -f $commandLine)
    Append-Line $runLog ""

    # Use System.Diagnostics.Process instead of direct native invocation.
    # This avoids PowerShell converting native stderr into NativeCommandError
    # records when $ErrorActionPreference = Stop, and it keeps the full Python
    # traceback in the per-run console log.
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

    Remove-Item -LiteralPath $stdoutTmp, $stderrTmp -ErrorAction SilentlyContinue

    if ($exitCode -eq 0) { $status = "PASS" } else { $status = "FAIL" }
    Append-Line $SuiteLog ("{0}`t{1}`tExit={2}`tElapsed={3:n1}s`tLog={4}" -f $status, $Name, $exitCode, $elapsed.TotalSeconds, $runLog)

    Write-Host ""
    Write-Host ("{0}: {1}  exit={2}  elapsed={3:n1}s" -f $status, $Name, $exitCode, $elapsed.TotalSeconds)
    Write-Host "Log: $runLog"

    if (($exitCode -ne 0) -and (-not $ContinueOnError)) {
        Write-Host ""
        Write-Host "Last lines from failed run log:"
        Get-Content -LiteralPath $runLog -Tail 80 -ErrorAction SilentlyContinue | Write-Host
        throw "Validation run failed: $Name. See $runLog"
    }

    return $exitCode
}

$PythonExe = Resolve-ToolPath $PythonExe
$SpicePy = Resolve-ToolPath $SpicePy
if (-not (Test-Path -LiteralPath $SpicePy)) { throw "Cannot find Spice.py at: $SpicePy" }

$WorkDir = Split-Path -Parent $SpicePy
if ([string]::IsNullOrWhiteSpace($WorkDir)) { $WorkDir = (Get-Location).Path }

if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$script:ResolvedLogDir = (Resolve-Path -LiteralPath $LogDir).Path

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$SuiteLog = Join-Path $script:ResolvedLogDir ("validation_suite_{0}.txt" -f $stamp)

Append-Line $SuiteLog "Spiky-Lu.i SPICE validation suite"
Append-Line $SuiteLog ("START: {0:o}" -f (Get-Date))
Append-Line $SuiteLog ("PythonExe: {0}" -f $PythonExe)
Append-Line $SuiteLog ("SpicePy: {0}" -f $SpicePy)
Append-Line $SuiteLog ("WorkDir: {0}" -f $WorkDir)
Append-Line $SuiteLog ("NgspiceBinary: {0}" -f $NgspiceBinary)
Append-Line $SuiteLog ("ContinueOnError: {0}" -f $ContinueOnError.IsPresent)
Append-Line $SuiteLog ("SkipRV123Sweep: {0}" -f $SkipRV123Sweep.IsPresent)
Append-Line $SuiteLog ("SkipRV5Sweep: {0}" -f $SkipRV5Sweep.IsPresent)
Append-Line $SuiteLog ("SkipLongSynapseSweep: {0}" -f $SkipLongSynapseSweep.IsPresent)
Append-Line $SuiteLog ""
Append-Line $SuiteLog "Removed runs: buffered V_Leak_Ref_Max validation; legacy direct-reference comparison"
Append-Line $SuiteLog ""
Append-Line $SuiteLog "STATUS`tRUN`tEXIT/ELAPSED/LOG"

$NgArg = @()
if (-not [string]::IsNullOrWhiteSpace($NgspiceBinary)) {
    $NgArg = @("--ngspice-binary", $NgspiceBinary)
}

$CommonCircuit = @(
    "--backend", "ngspice-cli"
) + $NgArg + @(
    "--supply-mode", "coin",
    "--vbat", "3",
    "--rbat", "50",
    "--startup-mode", "operating",
    "--ignore-start-ms", "20",
    "--rv1", "0.7",
    "--rv2", "0.5",
    "--rv3", "0.8",
    "--cmem-mode", "rv4",
    "--rv4", "0.3",
    "--tstep", "1u",
    "--maxstep", "1u"
)

$SynStaggeredTiming = @(
    "--syn1-delay", "150m", "--syn2-delay", "180m", "--syn3-delay", "210m", "--syn4-delay", "240m",
    "--syn1-width", "5m", "--syn2-width", "5m", "--syn3-width", "5m", "--syn4-width", "5m"
)

$SynSimultaneousTiming = @(
    "--syn1-delay", "150m", "--syn2-delay", "150m", "--syn3-delay", "150m", "--syn4-delay", "150m",
    "--syn1-width", "5m", "--syn2-width", "5m", "--syn3-width", "5m", "--syn4-width", "5m"
)

$Runs = New-Object System.Collections.ArrayList

function Add-PythonRun {
    param([string]$Name, [string[]]$RunArgs)
    [void]$script:Runs.Add(@{ Name = $Name; Args = @($RunArgs) })
}

function Add-SpiceRun {
    param([string]$Name, [string[]]$RunArgs)
    [void]$script:Runs.Add(@{ Name = $Name; Args = @($SpicePy) + @($RunArgs) })
}

Add-PythonRun -Name "00_python_compile" -RunArgs @("-m", "py_compile", $SpicePy)

# Threshold-reset/AP/Spike_Out path. Spike_Out is generated by the peak/reset block, so this uses threshold_reset rather than threshold.
Add-SpiceRun "01_threshold_reset_ap_spikeout" (@(
    "--stage", "threshold_reset", "--trace-set", "core"
) + $CommonCircuit + @(
    "--tstop", "300m"
))

# Full LIF baseline: Vm peak injection, Vm_Ext, reset, adaptation.
Add-SpiceRun "02_full_lif_no_synapse_vmext_peak" (@(
    "--stage", "threshold_reset_adapt", "--trace-set", "core"
) + $CommonCircuit + @(
    "--tstop", "1.5"
))

# Debug no-synapse run for V_Peak_Ref/U14/U1B/U19/U8 validation traces.
Add-SpiceRun "03_full_lif_no_synapse_debug" (@(
    "--stage", "threshold_reset_adapt", "--trace-set", "debug"
) + $CommonCircuit + @(
    "--tstop", "500m"
))

# Cold start stress.
Add-SpiceRun "04_cold_start_no_synapse" (@(
    "--stage", "threshold_reset_adapt", "--trace-set", "core", "--backend", "ngspice-cli"
) + $NgArg + @(
    "--supply-mode", "coin", "--vbat", "3", "--rbat", "50", "--startup-mode", "cold", "--ignore-start-ms", "20",
    "--rv1", "0.7", "--rv2", "0.5", "--rv3", "0.8", "--cmem-mode", "rv4", "--rv4", "0.3",
    "--tstop", "1.5", "--tstep", "1u", "--maxstep", "1u"
))

# Synapse blocks present, no pulses inside the analysis window.
Add-SpiceRun "05_synapses_present_no_pulses" (@(
    "--stage", "threshold_reset_adapt", "--trace-set", "core"
) + $CommonCircuit + @(
    "--syn-all-enable", "--rv5", "0.5", "--rv6", "0.5", "--rv7", "0.5", "--rv8", "0.5", "--rv9", "0.5",
    "--syn1-delay", "2", "--syn2-delay", "2", "--syn3-delay", "2", "--syn4-delay", "2",
    "--syn1-width", "5m", "--syn2-width", "5m", "--syn3-width", "5m", "--syn4-width", "5m",
    "--tstop", "1.5"
))

# Simultaneous synaptic stress tests.
Add-SpiceRun "06_synapses_simultaneous_low_stress" (@(
    "--stage", "threshold_reset_adapt", "--trace-set", "core"
) + $CommonCircuit + @(
    "--syn-all-enable", "--rv5", "0.5", "--rv6", "0.1", "--rv7", "0.1", "--rv8", "0.1", "--rv9", "0.1"
) + $SynSimultaneousTiming + @(
    "--tstop", "1.5"
))

Add-SpiceRun "07_synapses_simultaneous_high_stress" (@(
    "--stage", "threshold_reset_adapt", "--trace-set", "core"
) + $CommonCircuit + @(
    "--syn-all-enable", "--rv5", "0.5", "--rv6", "1.0", "--rv7", "1.0", "--rv8", "1.0", "--rv9", "1.0"
) + $SynSimultaneousTiming + @(
    "--tstop", "1.5"
))

# Stimulus path check using the U19 stimulus path.
Add-SpiceRun "08_stimulus_dc_positive" (@(
    "--stage", "threshold_reset_adapt", "--trace-set", "debug"
) + $CommonCircuit + @(
    "--stim-dc", "0.2", "--tstop", "500m"
))

# Independent RV1/RV2/RV3 behavioural sweeps.
# These are not full combinatorial sweeps; each knob is swept while the others stay at the baseline operating point.
if (-not $SkipRV123Sweep) {
    foreach ($rv1 in @("0.3", "0.5", "0.7", "0.9")) {
        $tag = $rv1.Replace(".", "p")
        Add-SpiceRun ("rv1_behaviour_{0}" -f $tag) (@(
            "--stage", "threshold_reset_adapt", "--trace-set", "core"
        ) + $CommonCircuit + @(
            "--rv1", $rv1,
            "--rv2", "0.5",
            "--rv3", "0.8",
            "--tstop", "1.5"
        ))
    }

    foreach ($rv2 in @("0.2", "0.5", "0.8")) {
        $tag = $rv2.Replace(".", "p")
        Add-SpiceRun ("rv2_behaviour_{0}" -f $tag) (@(
            "--stage", "threshold_reset_adapt", "--trace-set", "core"
        ) + $CommonCircuit + @(
            "--rv1", "0.7",
            "--rv2", $rv2,
            "--rv3", "0.8",
            "--tstop", "1.5"
        ))
    }

    foreach ($rv3 in @("0.2", "0.5", "0.8", "1.0")) {
        $tag = $rv3.Replace(".", "p")
        Add-SpiceRun ("rv3_behaviour_{0}" -f $tag) (@(
            "--stage", "threshold_reset_adapt", "--trace-set", "core"
        ) + $CommonCircuit + @(
            "--rv1", "0.7",
            "--rv2", "0.5",
            "--rv3", $rv3,
            "--tstop", "1.5"
        ))
    }
}

# RV5 synaptic-state decay sweep.
# RV6-RV9 are held at a representative 0.5 level while RV5 is swept.
if (-not $SkipRV5Sweep) {
    foreach ($rv5 in @("0.1", "0.3", "0.5", "0.8", "1.0")) {
        $tag = $rv5.Replace(".", "p")
        Add-SpiceRun ("rv5_syn_decay_{0}" -f $tag) (@(
            "--stage", "threshold_reset_adapt", "--trace-set", "core"
        ) + $CommonCircuit + @(
            "--syn-all-enable", "--rv5", $rv5, "--rv6", "0.5", "--rv7", "0.5", "--rv8", "0.5", "--rv9", "0.5"
        ) + $SynStaggeredTiming + @(
            "--tstop", "1.5"
        ))
    }
}

# Staggered RV6-RV9 synaptic control range sweep.
if (-not $SkipLongSynapseSweep) {
    foreach ($level in @("0.1", "0.3", "0.5", "0.8", "1.0")) {
        $tag = $level.Replace(".", "p")
        Add-SpiceRun ("synapse_staggered_rv{0}" -f $tag) (@(
            "--stage", "threshold_reset_adapt", "--trace-set", "core"
        ) + $CommonCircuit + @(
            "--syn-all-enable", "--rv5", "0.5", "--rv6", $level, "--rv7", $level, "--rv8", $level, "--rv9", $level
        ) + $SynStaggeredTiming + @(
            "--tstop", "1.5"
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
            throw
        }
    }
}

Append-Line $SuiteLog ""
Append-Line $SuiteLog ("END: {0:o}" -f (Get-Date))
Append-Line $SuiteLog ("TOTAL RUNS: {0}" -f $total)
Append-Line $SuiteLog ("FAILED RUNS: {0}" -f $failed)

Write-Host ""
Write-Host ("=" * 90)
Write-Host "Validation suite complete"
Write-Host "Total runs:  $total"
Write-Host "Failures:    $failed"
Write-Host "Suite log:   $SuiteLog"
Write-Host "Run logs:    $script:ResolvedLogDir"
Write-Host ("=" * 90)

if ($failed -ne 0) { exit 1 }
exit 0
