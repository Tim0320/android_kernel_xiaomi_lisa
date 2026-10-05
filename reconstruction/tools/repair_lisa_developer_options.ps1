param(
    [string]$Adb = "adb",
    [switch]$Apply,
    [string]$OutDir = ("lisa-devoptions-repair-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Run-AdbText {
    param([string]$Name, [string[]]$Args)
    $path = Join-Path $OutDir $Name
    & $Adb @Args 2>&1 | Out-File -FilePath $path -Encoding utf8
}

$state = (& $Adb get-state 2>&1 | Out-String).Trim()
if ($state -ne "device") {
    throw "ADB device not ready: $state"
}

Run-AdbText "adb_devices.txt" @("devices","-l")

$propCmd = @'
for p in ro.debuggable ro.force.debuggable ro.secure ro.adb.secure ro.build.type ro.build.tags ro.system.build.type ro.vendor.build.type; do
  echo "$p=$(getprop "$p")"
done
'@
Run-AdbText "debug_props_before.txt" @("shell","sh","-c",$propCmd)

$props = @{}
foreach ($line in Get-Content (Join-Path $OutDir "debug_props_before.txt")) {
    if ($line -match "^([^=]+)=(.*)$") {
        $props[$matches[1]] = $matches[2]
    }
}

$badTuple = (
    $props["ro.debuggable"] -eq "1" -and
    $props["ro.force.debuggable"] -eq "1" -and
    $props["ro.secure"] -eq "0" -and
    $props["ro.adb.secure"] -eq "0"
)

$rootCheck = (& $Adb shell su 0 id 2>&1 | Out-String).Trim()
$hasRoot = $rootCheck -match "uid=0"

$scan = @'
set -eu
PATTERN='(^|[[:space:]])(resetprop[[:space:]]+(-n[[:space:]]+)?|setprop[[:space:]]+)?(ro.debuggable[[:space:]]+1|ro.force.debuggable[[:space:]]+1|ro.secure[[:space:]]+0|ro.adb.secure[[:space:]]+0)|^(ro.debuggable=1|ro.force.debuggable=1|ro.secure=0|ro.adb.secure=0)$'
for f in   /data/adb/modules/*/system.prop   /data/adb/modules/*/post-fs-data.sh   /data/adb/modules/*/service.sh   /data/adb/post-fs-data.d/*   /data/adb/service.d/*   /data/local.prop
do
  [ -f "$f" ] || continue
  if grep -nEi "$PATTERN" "$f" >/dev/null 2>&1; then
    echo "FILE=$f"
    grep -nEi "$PATTERN" "$f" 2>/dev/null || true
  fi
done
'@

$offenderText = ""
if ($hasRoot) {
    $offenderText = (& $Adb shell su 0 sh -c $scan 2>&1 | Out-String)
} else {
    $offenderText = "ROOT_UNAVAILABLE"
}
$offenderText | Out-File (Join-Path $OutDir "property_override_scan.txt") -Encoding utf8

$offenders = @()
foreach ($line in ($offenderText -split "\r?\n")) {
    if ($line -match "^FILE=(/[^\r\n]+)$") {
        $candidate = $matches[1]
        if ($candidate -match "^/data/(adb/(modules/[^/]+/(system\.prop|post-fs-data\.sh|service\.sh)|post-fs-data\.d/[^/]+|service\.d/[^/]+)|local\.prop)$") {
            $offenders += $candidate
        }
    }
}
$offenders = $offenders | Sort-Object -Unique

$summary = [ordered]@{
    collected_at = (Get-Date).ToString("o")
    bad_debug_tuple_1_1_0_0 = $badTuple
    root_available = $hasRoot
    offender_count = $offenders.Count
    offenders = $offenders
    apply_requested = [bool]$Apply
    changes = @()
    reboot_required = $false
}

if ($Apply) {
    if (-not $hasRoot) {
        throw "Apply requested, but root shell is unavailable. No files changed."
    }

    if ($offenders.Count -eq 0) {
        Write-Host "No explicit external debug-property override found. Nothing changed."
    } else {
        $moduleDirs = @()
        $standalone = @()

        foreach ($item in $offenders) {
            if ($item -match "^/data/adb/modules/([^/]+)/") {
                $moduleDirs += "/data/adb/modules/$($matches[1])"
            } else {
                $standalone += $item
            }
        }

        foreach ($moduleDir in ($moduleDirs | Sort-Object -Unique)) {
            $safeModuleDir = $moduleDir.Replace("'","")
            $cmd = "touch '$safeModuleDir/disable' && chmod 0644 '$safeModuleDir/disable'"
            & $Adb shell su 0 sh -c $cmd | Out-Null
            $summary.changes += "disabled module: $safeModuleDir"
        }

        foreach ($item in ($standalone | Sort-Object -Unique)) {
            $safePath = $item.Replace("'","")
            $backup = "$safePath.disabled-lisa-devoptions"
            $cmd = "if [ -e '$backup' ]; then rm -f '$backup'; fi; mv '$safePath' '$backup'"
            & $Adb shell su 0 sh -c $cmd | Out-Null
            $summary.changes += "renamed override: $safePath -> $backup"
        }

        $summary.reboot_required = $true
    }
}

$summary | ConvertTo-Json -Depth 6 | Out-File (Join-Path $OutDir "summary.json") -Encoding utf8

Write-Host "Report: $OutDir"
Write-Host "bad tuple 1/1/0/0: $badTuple"
Write-Host "root available: $hasRoot"
Write-Host "explicit override files: $($offenders.Count)"

if ($Apply -and $summary.reboot_required) {
    Write-Host "Targeted override sources were disabled/backed aside."
    Write-Host "Reboot manually, then rerun WITHOUT -Apply and confirm 0/0/1/1."
    Write-Host "This tool does not weaken SELinux and does not use live resetprop."
} elseif (-not $Apply) {
    Write-Host "Read-only mode. Use -Apply only after reviewing property_override_scan.txt."
}
