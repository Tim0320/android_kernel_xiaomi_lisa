[CmdletBinding()]
param(
    [string]$BootImagePath = "",
    [string]$BuildLabel = "",
    [string]$KernelCommit = "",
    [string]$Outcome = "unknown",
    [string]$Note = "",
    [string]$OutputRoot = "",
    [switch]$IncludeRawDump,
    [switch]$NoZip
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptVersion = "1.3.7"
$SchemaVersion = 1

function Write-Step {
    param([string]$Message)
    Write-Host ("[Lisa-TWRP] " + $Message)
}

function Get-SafeName {
    param([string]$Value, [int]$MaxLength = 40)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return "unlabeled"
    }

    $safe = $Value -replace '[^A-Za-z0-9._-]+', '-'
    $safe = $safe.Trim('-', '.', '_')
    if ([string]::IsNullOrWhiteSpace($safe)) {
        $safe = "unlabeled"
    }
    if ($safe.Length -gt $MaxLength) {
        $safe = $safe.Substring(0, $MaxLength)
    }
    return $safe
}

function Invoke-AdbShellCapture {
    param(
        [string]$AdbPath,
        [string]$Command,
        [string]$OutFile
    )

    $header = @(
        ("command=adb shell " + $Command),
        ("captured_utc=" + (Get-Date).ToUniversalTime().ToString("o")),
        ""
    )

    try {
        $body = & $AdbPath shell $Command 2>&1
        $exitCode = $LASTEXITCODE
        @($header + @("exit_code=" + $exitCode, "") + $body) |
            Out-File -FilePath $OutFile -Encoding utf8
        return $exitCode
    }
    catch {
        @($header + @("capture_exception=" + $_.Exception.Message)) |
            Out-File -FilePath $OutFile -Encoding utf8
        return 255
    }
}

function Get-AdbShellText {
    param(
        [string]$AdbPath,
        [string]$Command
    )

    try {
        $result = & $AdbPath shell $Command 2>$null
        if ($null -eq $result) {
            return ""
        }
        return (($result | Out-String).Trim())
    }
    catch {
        return ""
    }
}

function Pull-AdbPathIfPresent {
    param(
        [string]$AdbPath,
        [string]$RemotePath,
        [string]$LocalPath,
        [string]$StatusFile
    )

    $probeCommand = "if [ -e '$RemotePath' ]; then echo PRESENT; else echo MISSING; fi"
    $probe = Get-AdbShellText -AdbPath $AdbPath -Command $probeCommand

    if ($probe -notmatch "PRESENT") {
        Add-Content -Path $StatusFile -Value ("MISSING " + $RemotePath)
        return $false
    }

    $parent = Split-Path -Parent $LocalPath
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }

    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $pullOutput = & $AdbPath pull $RemotePath $LocalPath 2>&1
        $exitCode = $LASTEXITCODE
    }
    catch {
        $exitCode = 255
        $pullOutput = @($_.Exception.Message)
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }

    Add-Content -Path $StatusFile -Value ("PULL exit=" + $exitCode + " remote=" + $RemotePath + " local=" + $LocalPath)
    if ($null -ne $pullOutput) {
        $pullOutput | ForEach-Object { ([string]$_) | Add-Content -Path $StatusFile }
    }
    if ($exitCode -ne 0) {
        Add-Content -Path $StatusFile -Value ("PULL_FAILED remote=" + $RemotePath)
    }
    return ($exitCode -eq 0)
}

function Pull-AdbGlobFiles {
    param(
        [string]$AdbPath,
        [string]$RemoteGlob,
        [string]$LocalDirectory,
        [string]$StatusFile
    )

    New-Item -ItemType Directory -Force -Path $LocalDirectory | Out-Null
    $listCommand = 'for f in ' + $RemoteGlob + '; do [ -f "$f" ] && echo "$f"; done'
    $listed = Get-AdbShellText -AdbPath $AdbPath -Command $listCommand
    $remoteFiles = @($listed -split "\r?\n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })

    foreach ($remoteFileRaw in $remoteFiles) {
        $remoteFile = ([string]$remoteFileRaw).Trim()
        if (-not $remoteFile.StartsWith("/")) { continue }
        $leaf = Split-Path -Leaf $remoteFile
        $localFile = Join-Path $LocalDirectory $leaf
        Pull-AdbPathIfPresent -AdbPath $AdbPath -RemotePath $remoteFile -LocalPath $localFile -StatusFile $StatusFile | Out-Null
    }
    return $remoteFiles.Count
}



function Pull-RecentAdbFiles {
    param(
        [string]$AdbPath,
        [string]$RemoteDirectory,
        [string]$LocalDirectory,
        [string]$StatusFile,
        [int]$MaxFiles = 8,
        [int64]$MaxBytes = 2097152
    )

    New-Item -ItemType Directory -Force -Path $LocalDirectory | Out-Null
    $listCommand = 'if [ -d "' + $RemoteDirectory + '" ]; then ls -1t "' + $RemoteDirectory + '" 2>/dev/null | head -n ' + $MaxFiles + '; fi'
    $listed = Get-AdbShellText -AdbPath $AdbPath -Command $listCommand
    $names = @($listed -split "\r?\n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $pulled = 0

    foreach ($nameRaw in $names) {
        $name = ([string]$nameRaw).Trim()
        if ([string]::IsNullOrWhiteSpace($name) -or $name.Contains("'") -or $name.Contains("/")) {
            Add-Content -Path $StatusFile -Value ("SKIP_UNSAFE_NAME dir=" + $RemoteDirectory + " name=" + $name)
            continue
        }

        $remoteFile = $RemoteDirectory.TrimEnd("/") + "/" + $name
        $sizeText = Get-AdbShellText -AdbPath $AdbPath -Command ("if [ -f '" + $remoteFile + "' ]; then stat -c %s '" + $remoteFile + "' 2>/dev/null || wc -c < '" + $remoteFile + "'; fi")
        [int64]$size = -1
        if (-not [int64]::TryParse(($sizeText -split "\r?\n")[0].Trim(), [ref]$size)) {
            Add-Content -Path $StatusFile -Value ("SKIP_SIZE_UNKNOWN remote=" + $remoteFile)
            continue
        }
        if ($size -gt $MaxBytes) {
            Add-Content -Path $StatusFile -Value ("SKIP_TOO_LARGE bytes=" + $size + " max=" + $MaxBytes + " remote=" + $remoteFile)
            continue
        }

        $localFile = Join-Path $LocalDirectory $name
        if (Pull-AdbPathIfPresent -AdbPath $AdbPath -RemotePath $remoteFile -LocalPath $localFile -StatusFile $StatusFile) {
            $pulled++
        }
    }

    Add-Content -Path $StatusFile -Value ("RECENT_PULL_SUMMARY dir=" + $RemoteDirectory + " pulled=" + $pulled + " max_files=" + $MaxFiles + " max_bytes_each=" + $MaxBytes)
    return $pulled
}


function Get-BinaryContentStats {
    param(
        [string]$Path
    )

    $stream = [System.IO.File]::OpenRead($Path)
    $buffer = New-Object byte[] (4MB)

    [int64]$absoluteOffset = 0
    [int64]$nonZeroBytes = 0
    [int64]$firstNonZeroOffset = -1
    [int64]$lastNonZeroOffset = -1

    try {
        while (($read = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            for ($i = 0; $i -lt $read; $i++) {
                if ($buffer[$i] -ne 0) {
                    $nonZeroBytes++
                    $currentOffset = $absoluteOffset + $i

                    if ($firstNonZeroOffset -lt 0) {
                        $firstNonZeroOffset = $currentOffset
                    }

                    $lastNonZeroOffset = $currentOffset
                }
            }

            $absoluteOffset += $read
        }
    }
    finally {
        $stream.Dispose()
    }

    return [pscustomobject][ordered]@{
        all_zero = ($nonZeroBytes -eq 0)
        nonzero_bytes = $nonZeroBytes
        first_nonzero_offset = $firstNonZeroOffset
        last_nonzero_offset = $lastNonZeroOffset
    }
}

function Capture-AdbBlockPartition {
    param(
        [string]$AdbPath,
        [string]$PartitionName,
        [string]$LocalDirectory,
        [string]$Iteration,
        [string]$StatusFile,
        [int64]$MaxBytes = 268435456
    )

    $remoteBlock = "/dev/block/by-name/" + $PartitionName
    $probe = Get-AdbShellText -AdbPath $AdbPath -Command ("if [ -e '" + $remoteBlock + "' ]; then echo PRESENT; else echo MISSING; fi")
    if ($probe -notmatch "PRESENT") {
        Add-Content -Path $StatusFile -Value ("BLOCK_MISSING " + $remoteBlock)
        return $null
    }

    $sizeText = Get-AdbShellText -AdbPath $AdbPath -Command ("blockdev --getsize64 '" + $remoteBlock + "' 2>/dev/null")
    [int64]$sizeBytes = 0
    if (-not [int64]::TryParse(($sizeText.Trim()), [ref]$sizeBytes)) {
        Add-Content -Path $StatusFile -Value ("BLOCK_SIZE_UNKNOWN partition=" + $PartitionName + " value=" + $sizeText)
        return $null
    }

    Add-Content -Path $StatusFile -Value ("BLOCK partition=" + $PartitionName + " size_bytes=" + $sizeBytes)
    if ($sizeBytes -le 0 -or $sizeBytes -gt $MaxBytes) {
        Add-Content -Path $StatusFile -Value ("BLOCK_SKIP partition=" + $PartitionName + " size_bytes=" + $sizeBytes + " max_bytes=" + $MaxBytes)
        return $null
    }

    New-Item -ItemType Directory -Force -Path $LocalDirectory | Out-Null
    $remoteTemp = "/tmp/lisa_" + $PartitionName + "_iter" + $Iteration + ".bin"
    $localFile = Join-Path $LocalDirectory ("lisa_" + $PartitionName + "_iter" + $Iteration + ".bin")

    Write-Step ("Capturing " + $PartitionName + " partition (" + $sizeBytes + " bytes)...")
    $ddCommand = "rm -f '" + $remoteTemp + "'; dd if='" + $remoteBlock + "' of='" + $remoteTemp + "' bs=1048576 2>&1; sync"
    $ddOutput = Get-AdbShellText -AdbPath $AdbPath -Command $ddCommand
    Add-Content -Path $StatusFile -Value ("DD partition=" + $PartitionName)
    Add-Content -Path $StatusFile -Value $ddOutput

    $pullOk = Pull-AdbPathIfPresent -AdbPath $AdbPath -RemotePath $remoteTemp -LocalPath $localFile -StatusFile $StatusFile
    Get-AdbShellText -AdbPath $AdbPath -Command ("rm -f '" + $remoteTemp + "'") | Out-Null
    if (-not $pullOk) { return $null }

    $localInfo = Get-Item -LiteralPath $localFile
    $localHash = (Get-FileHash -LiteralPath $localFile -Algorithm SHA256).Hash.ToLowerInvariant()
    Add-Content -Path $StatusFile -Value ("BLOCK_CAPTURED partition=" + $PartitionName + " local_bytes=" + $localInfo.Length + " sha256=" + $localHash)

    return [pscustomobject][ordered]@{
        partition = $PartitionName
        remote_path = $remoteBlock
        size_bytes = [int64]$localInfo.Length
        sha256 = $localHash
        local_file = ("pulled/block_partitions/" + $localInfo.Name)
    }
}

function Write-HistoryFiles {
    param(
        [string]$Root,
        [pscustomobject]$Record
    )

    $csvPath = Join-Path $Root "ITERATIONS.csv"
    $mdPath = Join-Path $Root "ITERATIONS.md"

    $rows = @()
    if (Test-Path -LiteralPath $csvPath) {
        try {
            $rows = @(Import-Csv -LiteralPath $csvPath)
        }
        catch {
            $backup = $csvPath + ".corrupt-" + (Get-Date -Format "yyyyMMdd-HHmmss")
            Copy-Item -LiteralPath $csvPath -Destination $backup -Force
            $rows = @()
        }
    }

    $rows = @($rows + $Record)
    $rows | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding UTF8

    $md = New-Object System.Collections.Generic.List[string]
    $md.Add("# Lisa TWRP log iterations")
    $md.Add("")
    $md.Add("Generated by scripts/collect_lisa_twrp_logs.ps1. Existing iterations are never intentionally overwritten.")
    $md.Add("")
    $md.Add("| Iteration | Local time | Build label | Boot SHA256 | Kernel commit | Outcome | Folder |")
    $md.Add("| --- | --- | --- | --- | --- | --- | --- |")

    foreach ($row in $rows) {
        $label = ([string]$row.BuildLabel).Replace("|", "/")
        $outcome = ([string]$row.Outcome).Replace("|", "/")
        $folder = ([string]$row.Folder).Replace("|", "/")
        $sha = [string]$row.BootSha256
        if ($sha.Length -gt 16) {
            $sha = $sha.Substring(0, 16) + "..."
        }
        $commit = [string]$row.KernelCommit
        if ($commit.Length -gt 12) {
            $commit = $commit.Substring(0, 12)
        }
        $md.Add("| " + $row.Iteration + " | " + $row.TimestampLocal + " | " + $label + " | " + $sha + " | " + $commit + " | " + $outcome + " | " + $folder + " |")
    }

    $md | Set-Content -LiteralPath $mdPath -Encoding UTF8
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptDir ".."))

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $repoRoot "twrp_logs"
}
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

if ([string]::IsNullOrWhiteSpace($BootImagePath)) {
    $cwdBoot = Join-Path (Get-Location).Path "boot.img"
    $repoBoot = Join-Path $repoRoot "boot.img"

    if (Test-Path -LiteralPath $cwdBoot) {
        $BootImagePath = $cwdBoot
    }
    elseif (Test-Path -LiteralPath $repoBoot) {
        $BootImagePath = $repoBoot
    }
}

$bootFile = "UNKNOWN"
$bootSha256 = "UNKNOWN"
$bootBytes = 0
$bootLastWriteUtc = "UNKNOWN"

if (-not [string]::IsNullOrWhiteSpace($BootImagePath)) {
    $BootImagePath = [System.IO.Path]::GetFullPath($BootImagePath)
    if (-not (Test-Path -LiteralPath $BootImagePath -PathType Leaf)) {
        throw "Boot image not found: $BootImagePath"
    }

    $bootInfo = Get-Item -LiteralPath $BootImagePath
    $bootFile = $bootInfo.Name
    $bootBytes = $bootInfo.Length
    $bootLastWriteUtc = $bootInfo.LastWriteTimeUtc.ToString("o")
    $bootSha256 = (Get-FileHash -LiteralPath $BootImagePath -Algorithm SHA256).Hash.ToLowerInvariant()
}
else {
    Write-Warning "No boot.img path was supplied or auto-detected. The package will still be created, but boot SHA256 will be UNKNOWN."
}

if ([string]::IsNullOrWhiteSpace($BuildLabel)) {
    if ($bootFile -ne "UNKNOWN") {
        $BuildLabel = [System.IO.Path]::GetFileNameWithoutExtension($bootFile)
    }
    else {
        $BuildLabel = "unlabeled"
    }
}

if ([string]::IsNullOrWhiteSpace($KernelCommit)) {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($null -ne $git -and (Test-Path -LiteralPath (Join-Path $repoRoot ".git"))) {
        try {
            $candidate = (& $git.Source -C $repoRoot rev-parse HEAD 2>$null | Out-String).Trim()
            if ($candidate -match '^[0-9a-fA-F]{40}$') {
                $KernelCommit = $candidate.ToLowerInvariant()
            }
        }
        catch {
        }
    }
}
if ([string]::IsNullOrWhiteSpace($KernelCommit)) {
    $KernelCommit = "UNKNOWN"
}

$existingNumbers = @()
Get-ChildItem -LiteralPath $OutputRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.Name -match '^iter-(\d{4,})_') {
        $existingNumbers += [int]$Matches[1]
    }
}
[int]$nextNumber = 1
if ($existingNumbers.Count -gt 0) {
    [int]$maxExisting = [int](($existingNumbers | Measure-Object -Maximum).Maximum)
    $nextNumber = $maxExisting + 1
}

$iteration = ([int]$nextNumber).ToString("D4", [System.Globalization.CultureInfo]::InvariantCulture)
$timestampName = Get-Date -Format "yyyyMMdd-HHmmss"
$timestampLocal = (Get-Date).ToString("o")
$timestampUtc = (Get-Date).ToUniversalTime().ToString("o")
$shortHash = "nohash"
if ($bootSha256 -ne "UNKNOWN") {
    $shortHash = $bootSha256.Substring(0, 12)
}
$safeLabel = Get-SafeName -Value $BuildLabel
$folderName = "iter-" + $iteration + "_" + $timestampName + "_" + $safeLabel + "_" + $shortHash
$iterationDir = Join-Path $OutputRoot $folderName
$rawDir = Join-Path $iterationDir "raw"
$pulledDir = Join-Path $iterationDir "pulled"

New-Item -ItemType Directory -Force -Path $rawDir | Out-Null
New-Item -ItemType Directory -Force -Path $pulledDir | Out-Null

$adb = Get-Command adb -ErrorAction Stop
$adbPath = $adb.Source

Write-Step "Starting ADB and checking for a usable TWRP/recovery transport..."
& $adbPath start-server | Out-Null

$acceptedAdbStates = @("device", "recovery")
$state = (& $adbPath get-state 2>$null | Out-String).Trim()

if ($acceptedAdbStates -notcontains $state) {
    Write-Step ("Current ADB state is '" + $state + "'. Waiting for device/recovery transport...")
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Seconds 1
        $state = (& $adbPath get-state 2>$null | Out-String).Trim()
        if ($acceptedAdbStates -contains $state) {
            break
        }
    } while ((Get-Date) -lt $deadline)
}

if ($acceptedAdbStates -notcontains $state) {
    throw "ADB state is '$state'; expected 'device' or 'recovery'."
}

Write-Step ("ADB transport ready: " + $state)

$device = Get-AdbShellText -AdbPath $adbPath -Command "getprop ro.product.device"
$model = Get-AdbShellText -AdbPath $adbPath -Command "getprop ro.product.model"
$slot = Get-AdbShellText -AdbPath $adbPath -Command "getprop ro.boot.slot_suffix"
$bootMode = Get-AdbShellText -AdbPath $adbPath -Command "getprop ro.bootmode"
$bootReason = Get-AdbShellText -AdbPath $adbPath -Command "getprop ro.boot.bootreason"
$twrpVersion = Get-AdbShellText -AdbPath $adbPath -Command "getprop ro.twrp.version"

$cmdlineText = Get-AdbShellText -AdbPath $adbPath -Command "cat /proc/cmdline 2>/dev/null"
$pureason = "UNKNOWN"
$pdreason = "UNKNOWN"

if ($cmdlineText -match '(?:^|\s)bootinfo\.pureason=([^\s]+)') {
    $pureason = $Matches[1]
}

if ($cmdlineText -match '(?:^|\s)bootinfo\.pdreason=([^\s]+)') {
    $pdreason = $Matches[1]
}

if ([string]::IsNullOrWhiteSpace($device)) { $device = "UNKNOWN" }
if ([string]::IsNullOrWhiteSpace($model)) { $model = "UNKNOWN" }
if ([string]::IsNullOrWhiteSpace($slot)) { $slot = "UNKNOWN" }
if ([string]::IsNullOrWhiteSpace($bootMode)) { $bootMode = "UNKNOWN" }
if ([string]::IsNullOrWhiteSpace($bootReason)) { $bootReason = "UNKNOWN" }
if ([string]::IsNullOrWhiteSpace($twrpVersion)) { $twrpVersion = "UNKNOWN" }

Write-Step ("Collecting iteration " + $iteration + " into " + $iterationDir)

$commands = @(
    @{ File = "01_identity.txt"; Command = "id; echo; uname -a; echo; cat /proc/version 2>/dev/null || true" },
    @{ File = "02_boot_properties.txt"; Command = 'for p in ro.product.device ro.product.model ro.bootmode ro.boot.slot_suffix ro.boot.bootreason sys.boot.reason ro.boot.vbmeta.device_state ro.boot.verifiedbootstate ro.boot.flash.locked ro.twrp.version; do printf "%s=" "$p"; getprop "$p"; done' },
    @{ File = "03_proc_cmdline.txt"; Command = "cat /proc/cmdline 2>/dev/null || true" },
    @{ File = "04_proc_bootconfig.txt"; Command = "cat /proc/bootconfig 2>/dev/null || true" },
    @{ File = "05_mounts.txt"; Command = "cat /proc/mounts 2>/dev/null || mount" },
    @{ File = "06_df.txt"; Command = "df -h 2>/dev/null || df" },
    @{ File = "07_block_by_name.txt"; Command = "ls -la /dev/block/by-name 2>/dev/null || true; echo; ls -la /dev/block/bootdevice/by-name 2>/dev/null || true" },
    @{ File = "08_pstore_listing.txt"; Command = "ls -la /sys/fs/pstore 2>/dev/null || true" },
    @{ File = "09_pstore_contents.txt"; Command = 'if [ -d /sys/fs/pstore ]; then for f in /sys/fs/pstore/*; do [ -f "$f" ] || continue; echo "===== $f ====="; cat "$f"; echo; done; fi' },
    @{ File = "10_last_kmsg.txt"; Command = "if [ -r /proc/last_kmsg ]; then cat /proc/last_kmsg; else echo NO_PROC_LAST_KMSG; fi" },
    @{ File = "11_dmesg_recovery.txt"; Command = "dmesg 2>&1" },
    @{ File = "12_logcat_recovery.txt"; Command = "logcat -b all -d 2>&1 || true" },
    @{ File = "13_twrp_recovery_log.txt"; Command = "if [ -r /tmp/recovery.log ]; then cat /tmp/recovery.log; else echo NO_TMP_RECOVERY_LOG; fi" },
    @{ File = "14_cache_recovery_log.txt"; Command = "if [ -r /cache/recovery/log ]; then cat /cache/recovery/log; else echo NO_CACHE_RECOVERY_LOG; fi" },
    @{ File = "15_cache_recovery_last_log.txt"; Command = "if [ -r /cache/recovery/last_log ]; then cat /cache/recovery/last_log; else echo NO_CACHE_RECOVERY_LAST_LOG; fi" },
    @{ File = "16_boot_reason_sources.txt"; Command = 'echo ro.boot.bootreason=$(getprop ro.boot.bootreason); echo sys.boot.reason=$(getprop sys.boot.reason); echo ro.bootmode=$(getprop ro.bootmode); echo ro.boot.slot_suffix=$(getprop ro.boot.slot_suffix); echo ro.boot.verifiedbootstate=$(getprop ro.boot.verifiedbootstate); echo ro.boot.vbmeta.device_state=$(getprop ro.boot.vbmeta.device_state)' },
    @{ File = "17_kernel_message_sources.txt"; Command = 'for p in /sys/fs/pstore /data/vendor/ramoops /cache/recovery /tmp; do echo "===== $p ====="; ls -la "$p" 2>&1 || true; done' },
    @{ File = "21_userspace_failure_sources.txt"; Command = 'echo "===== data mount ====="; grep " /data " /proc/mounts 2>/dev/null || echo NO_DATA_MOUNT_LINE; echo; for p in /data/system/dropbox /data/tombstones /data/anr; do echo "===== $p ====="; if [ -d "$p" ]; then ls -lat "$p" 2>&1 | head -n 80; else echo MISSING_OR_LOCKED; fi; echo; done' },
    @{ File = "22_adbd_debug_provenance.txt"; Command = 'echo "===== static property sources ====="; for f in /system/etc/prop.default /system/system/etc/prop.default /system/build.prop /system/system/build.prop /system_ext/build.prop /system_ext/etc/build.prop /product/build.prop /product/etc/build.prop /vendor/default.prop /vendor/build.prop /odm/build.prop /odm/etc/build.prop; do if [ -f "$f" ]; then echo "---- $f ----"; grep -nE "^(ro\\.debuggable|ro\\.force\\.debuggable|ro\\.secure|ro\\.adb\\.secure)=" "$f" 2>/dev/null || true; fi; done; echo; echo "===== debug/root marker files ====="; for p in /force_debuggable /adb_debug.prop /userdebug_plat_sepolicy.cil /debug_ramdisk /first_stage_ramdisk; do ls -ladZ "$p" 2>&1 || true; done; echo; echo "===== init adbd/root references ====="; for d in /system/etc/init /system/system/etc/init /system_ext/etc/init /product/etc/init /vendor/etc/init /odm/etc/init; do if [ -d "$d" ]; then echo "---- $d ----"; grep -RnsE "service[[:space:]]+adbd|root_seclabel|service\\.adb\\.root|u:r:su:s0" "$d" 2>/dev/null | head -n 160; fi; done; echo; echo "===== data adb/root indicators ====="; ls -ladZ /data/adb /data/adb/modules /data/property 2>&1 || true; if [ -d /data/adb ]; then find /data/adb -maxdepth 2 -type f \( -name "*.prop" -o -name "module.prop" -o -name "*.rc" \) -print 2>/dev/null | head -n 120; fi; echo; echo "===== persistent property strings ====="; if [ -f /data/property/persistent_properties ]; then strings /data/property/persistent_properties 2>/dev/null | grep -Ei "debuggable|force.debuggable|ro.secure|adb.secure|service.adb.root|root_access|magisk|kernelsu|apatch" | head -n 160 || true; else echo NO_PERSISTENT_PROPERTIES_FILE; fi' }
    @{ File = "23_nfc_runtime_module_provenance.txt"; Command = 'echo "===== vendor/odm module mounts ====="; grep -E " /(vendor_dlkm|odm_dlkm|vendor|odm)(/| )" /proc/mounts 2>/dev/null || true; echo; echo "===== canonical module paths ====="; for root in /vendor/lib/modules /odm/lib/modules /vendor_dlkm/lib/modules /odm_dlkm/lib/modules; do echo "---- $root ----"; if [ -d "$root" ]; then find -H "$root" -maxdepth 4 \( -type f -o -type l \) \( -name "nfc_i2c.ko" -o -name "nfc_i2c.ko.*" \) -print 2>/dev/null | while read f; do echo "FILE=$f"; resolved=$(readlink -f "$f" 2>/dev/null || echo "$f"); echo "RESOLVED=$resolved"; sha256sum "$resolved" 2>/dev/null || sha256sum "$f" 2>/dev/null || true; strings "$resolved" 2>/dev/null | grep -E "^(vermagic=|depends=)|NFC cdev unavailable" | head -n 20 || true; done; find -H "$root" -maxdepth 4 -type f \( -name "modules.load*" -o -name "modules.dep*" -o -name "modules.order" \) -print 2>/dev/null | while read mf; do echo "MANIFEST=$mf"; grep -nE "(^|/|[[:space:]])nfc_i2c(\\.ko)?([[:space:]]|$)" "$mf" 2>/dev/null | head -n 40 || true; done; else echo MISSING; fi; done; echo; scan_dlkm() { label="$1"; shift; tmp="/tmp/lisa_$label-ro"; mkdir -p "$tmp"; mounted=0; for dev in "$@"; do [ -b "$dev" ] || continue; echo "TRY_$label-DEV=$dev"; if mount -t ext4 -o ro,noload "$dev" "$tmp" 2>/dev/null; then mounted=1; mode="ext4:ro,noload"; elif mount -t erofs -o ro "$dev" "$tmp" 2>/dev/null; then mounted=1; mode="erofs:ro"; else continue; fi; echo "$label-READONLY_MOUNTED=$dev"; echo "$label-MOUNT_MODE=$mode"; root="$tmp/lib/modules"; if [ -d "$root" ]; then find -H "$root" -maxdepth 4 \( -type f -o -type l \) \( -name "nfc_i2c.ko" -o -name "nfc_i2c.ko.*" \) -print 2>/dev/null | while read f; do echo "FILE=$f"; resolved=$(readlink -f "$f" 2>/dev/null || echo "$f"); echo "RESOLVED=$resolved"; sha256sum "$resolved" 2>/dev/null || sha256sum "$f" 2>/dev/null || true; strings "$resolved" 2>/dev/null | grep -E "^(vermagic=|depends=)|NFC cdev unavailable" | head -n 20 || true; done; find -H "$root" -maxdepth 4 -type f \( -name "modules.load*" -o -name "modules.dep*" -o -name "modules.order" \) -print 2>/dev/null | while read mf; do echo "MANIFEST=$mf"; grep -nE "(^|/|[[:space:]])nfc_i2c(\\.ko)?([[:space:]]|$)" "$mf" 2>/dev/null | head -n 40 || true; done; else echo "$label-NO_LIB_MODULES"; fi; umount "$tmp" 2>/dev/null || true; break; done; [ "$mounted" = 1 ] || echo "$label-READONLY_MOUNT_FAILED"; rmdir "$tmp" 2>/dev/null || true; }; slot=$(getprop ro.boot.slot_suffix 2>/dev/null); echo; echo "===== strict RO vendor_dlkm partition provenance ====="; scan_dlkm VENDOR "/dev/block/mapper/vendor_dlkm$slot" "/dev/block/by-name/vendor_dlkm$slot" /dev/block/mapper/vendor_dlkm /dev/block/by-name/vendor_dlkm; echo; echo "===== strict RO odm_dlkm partition provenance ====="; scan_dlkm ODM "/dev/block/mapper/odm_dlkm$slot" "/dev/block/by-name/odm_dlkm$slot" /dev/block/mapper/odm_dlkm /dev/block/by-name/odm_dlkm' },
)

foreach ($entry in $commands) {
    $out = Join-Path $rawDir $entry.File
    Invoke-AdbShellCapture -AdbPath $adbPath -Command $entry.Command -OutFile $out | Out-Null
}

$getpropPath = Join-Path $rawDir "18_getprop_redacted.txt"
$getpropLines = & $adbPath shell getprop 2>&1
$redactedProps = foreach ($line in $getpropLines) {
    if ($line -match '^\[([^\]]*(serial|imei|meid|mac_address|bluetooth\.address)[^\]]*)\]:') {
        $key = $Matches[1]
        "[" + $key + "]: [[REDACTED]]"
    }
    else {
        $line
    }
}
$redactedProps | Out-File -LiteralPath $getpropPath -Encoding utf8

$pullStatus = Join-Path $rawDir "19_pull_status.txt"
"Lisa TWRP pull status" | Set-Content -LiteralPath $pullStatus -Encoding utf8

Pull-AdbPathIfPresent -AdbPath $adbPath -RemotePath "/sys/fs/pstore" -LocalPath (Join-Path $pulledDir "pstore") -StatusFile $pullStatus | Out-Null
Pull-AdbPathIfPresent -AdbPath $adbPath -RemotePath "/data/vendor/ramoops" -LocalPath (Join-Path $pulledDir "data_vendor_ramoops") -StatusFile $pullStatus | Out-Null
Pull-AdbPathIfPresent -AdbPath $adbPath -RemotePath "/tmp/recovery.log" -LocalPath (Join-Path $pulledDir "twrp_recovery.log") -StatusFile $pullStatus | Out-Null

$cacheHistoryDir = Join-Path $pulledDir "cache_recovery_history"
$cacheLastKmsgCount = Pull-AdbGlobFiles -AdbPath $adbPath -RemoteGlob "/cache/recovery/last_kmsg*" -LocalDirectory $cacheHistoryDir -StatusFile $pullStatus
$cacheLastLogCount = Pull-AdbGlobFiles -AdbPath $adbPath -RemoteGlob "/cache/recovery/last_log*" -LocalDirectory $cacheHistoryDir -StatusFile $pullStatus

foreach ($cacheFile in @("/cache/recovery/last_status", "/cache/recovery/last_install", "/cache/recovery/last_extension_parameters", "/cache/recovery/last_virtualpartition_log", "/cache/recovery/recovery.fstab")) {
    $leaf = Split-Path -Leaf $cacheFile
    Pull-AdbPathIfPresent -AdbPath $adbPath -RemotePath $cacheFile -LocalPath (Join-Path $cacheHistoryDir $leaf) -StatusFile $pullStatus | Out-Null
}


$userspaceEvidenceDir = Join-Path $pulledDir "userspace_failure"
$dataAccessProbe = Get-AdbShellText -AdbPath $adbPath -Command 'if [ -d /data/system ] && [ -r /data/system ]; then echo DATA_ACCESSIBLE; else echo DATA_UNAVAILABLE_OR_LOCKED; fi'
$dataAccessible = ($dataAccessProbe -match "DATA_ACCESSIBLE")
$dropboxFileCount = 0
$tombstoneFileCount = 0
$anrFileCount = 0

Add-Content -Path $pullStatus -Value ("DATA_ACCESS_PROBE " + $dataAccessProbe)
if ($dataAccessible) {
    $dropboxFileCount = Pull-RecentAdbFiles -AdbPath $adbPath -RemoteDirectory "/data/system/dropbox" -LocalDirectory (Join-Path $userspaceEvidenceDir "dropbox") -StatusFile $pullStatus -MaxFiles 8 -MaxBytes 2097152
    $tombstoneFileCount = Pull-RecentAdbFiles -AdbPath $adbPath -RemoteDirectory "/data/tombstones" -LocalDirectory (Join-Path $userspaceEvidenceDir "tombstones") -StatusFile $pullStatus -MaxFiles 8 -MaxBytes 2097152
    $anrFileCount = Pull-RecentAdbFiles -AdbPath $adbPath -RemoteDirectory "/data/anr" -LocalDirectory (Join-Path $userspaceEvidenceDir "anr") -StatusFile $pullStatus -MaxFiles 8 -MaxBytes 2097152
}
else {
    Add-Content -Path $pullStatus -Value "USERSPACE_EVIDENCE_SKIPPED data unavailable or encrypted in recovery"
}


$blockDumpDir = Join-Path $pulledDir "block_partitions"
$blockCaptures = @()
foreach ($partitionName in @("oops", "logdump")) {
    $capture = Capture-AdbBlockPartition -AdbPath $adbPath -PartitionName $partitionName -LocalDirectory $blockDumpDir -Iteration $iteration -StatusFile $pullStatus
    if ($null -ne $capture) { $blockCaptures += $capture }
}

$dumpInventoryPath = Join-Path $rawDir "20_dump_partition_inventory.txt"
$dumpInventory = New-Object System.Collections.Generic.List[string]
foreach ($partitionName in @("oops", "logdump", "minidump", "rawdump", "logfs", "mdcompress")) {
    $remoteBlock = "/dev/block/by-name/" + $partitionName
    $line = Get-AdbShellText -AdbPath $adbPath -Command ("if [ -e '" + $remoteBlock + "' ]; then printf '" + $partitionName + " '; blockdev --getsize64 '" + $remoteBlock + "' 2>/dev/null || echo SIZE_UNKNOWN; else echo '" + $partitionName + " MISSING'; fi")
    $dumpInventory.Add($line)
}
$dumpInventory | Set-Content -LiteralPath $dumpInventoryPath -Encoding utf8

$manifest = [ordered]@{
    schema_version = $SchemaVersion
    collector = [ordered]@{
        name = "Lisa TWRP failure log collector"
        script_version = $ScriptVersion
        script_name = "collect_lisa_twrp_logs.ps1"
    }
    iteration = [ordered]@{
        number = $iteration
        folder = $folderName
        timestamp_local = $timestampLocal
        timestamp_utc = $timestampUtc
        outcome = $Outcome
        note = $Note
    }
    build = [ordered]@{
        label = $BuildLabel
        kernel_commit = $KernelCommit
        boot_image_file = $bootFile
        boot_image_sha256 = $bootSha256
        boot_image_bytes = $bootBytes
        boot_image_last_write_utc = $bootLastWriteUtc
    }
    device = [ordered]@{
        product_device = $device
        model = $model
        slot_suffix = $slot
        boot_mode = $bootMode
        boot_reason = $bootReason
        cmdline_pureason = $pureason
        cmdline_pdreason = $pdreason
        twrp_version = $twrpVersion
    }
    collection = [ordered]@{
        adb_state = $state
        pstore_path_present = (Test-Path -LiteralPath (Join-Path $pulledDir "pstore"))
        pstore_file_count = @(Get-ChildItem -LiteralPath (Join-Path $pulledDir "pstore") -File -Recurse -ErrorAction SilentlyContinue).Count
        data_vendor_ramoops_present = (Test-Path -LiteralPath (Join-Path $pulledDir "data_vendor_ramoops"))
        cache_recovery_last_kmsg_count = $cacheLastKmsgCount
        cache_recovery_last_log_count = $cacheLastLogCount
        data_accessible_in_recovery = $dataAccessible
        dropbox_recent_file_count = $dropboxFileCount
        tombstone_recent_file_count = $tombstoneFileCount
        anr_recent_file_count = $anrFileCount
        userspace_failure_inventory_file = "raw/21_userspace_failure_sources.txt"
        userspace_failure_pull_root = "pulled/userspace_failure"
        block_partition_captures = @($blockCaptures)
        dump_partition_inventory_file = "raw/20_dump_partition_inventory.txt"
        proc_last_kmsg_marker_file = "raw/10_last_kmsg.txt"
        recovery_dmesg_file = "raw/11_dmesg_recovery.txt"
        twrp_log_file = "raw/13_twrp_recovery_log.txt"
    }
}

$manifestPath = Join-Path $iterationDir "manifest.json"
$manifest | ConvertTo-Json -Depth 8 | Out-File -LiteralPath $manifestPath -Encoding utf8

$summary = @(
    "Lisa TWRP failure-log package",
    "collector_version=$ScriptVersion",
    "iteration=$iteration",
    "timestamp_local=$timestampLocal",
    "timestamp_utc=$timestampUtc",
    "build_label=$BuildLabel",
    "kernel_commit=$KernelCommit",
    "boot_image_file=$bootFile",
    "boot_image_sha256=$bootSha256",
    "boot_image_bytes=$bootBytes",
    "device=$device",
    "model=$model",
    "slot_suffix=$slot",
    "boot_mode=$bootMode",
    "boot_reason=$bootReason",
    "cmdline_pureason=$pureason",
    "cmdline_pdreason=$pdreason",
    "twrp_version=$twrpVersion",
    "outcome=$Outcome",
    "note=$Note",
    "",
    "Primary failure evidence:",
    "1. pulled/block_partitions/lisa_oops_iter$iteration.bin",
    "2. pulled/block_partitions/lisa_logdump_iter$iteration.bin",
    "3. pulled/block_partitions/lisa_minidump_iter$iteration.bin",
    "4. pulled/block_partitions/lisa_mdcompress_iter$iteration.bin",
    "5. pulled/block_partitions/lisa_logfs_iter$iteration.bin",
    "6. pulled/pstore and raw/09_pstore_contents.txt",
    "7. raw/10_last_kmsg.txt",
    "8. pulled/data_vendor_ramoops",
    "9. raw/11_dmesg_recovery.txt",
    "10. raw/21_userspace_failure_sources.txt",
    "11. pulled/userspace_failure/dropbox (up to 8 newest files, <=2 MiB each)",
    "12. pulled/userspace_failure/tombstones (up to 8 newest files, <=2 MiB each)",
    "13. pulled/userspace_failure/anr (up to 8 newest files, <=2 MiB each)",
    "14. raw/22_adbd_debug_provenance.txt (read-only property/init/root provenance)",
    "15. raw/23_nfc_runtime_module_provenance.txt (runtime nfc_i2c symlink-aware canonical/resolved path, hash/vermagic/guard, text manifests; strict RO vendor_dlkm+odm_dlkm provenance)",
    "",
    "Recovery history (context only):",
    "15. pulled/cache_recovery_history/last_kmsg*",
    "16. pulled/cache_recovery_history/last_log*",
    "",
    "Additional dump inventory:",
    "17. raw/20_dump_partition_inventory.txt",
    "18. rawdump is captured only when -IncludeRawDump is explicitly supplied"
)
$summary | Set-Content -LiteralPath (Join-Path $iterationDir "SUMMARY.txt") -Encoding utf8

$zipName = "lisa-twrp-" + $folderName + ".zip"
$historyRecord = [pscustomobject][ordered]@{
    Iteration = $iteration
    TimestampLocal = $timestampLocal
    TimestampUtc = $timestampUtc
    BuildLabel = $BuildLabel
    BootFile = $bootFile
    BootSha256 = $bootSha256
    BootBytes = $bootBytes
    KernelCommit = $KernelCommit
    Outcome = $Outcome
    Device = $device
    Slot = $slot
    TwrpVersion = $twrpVersion
    Folder = $folderName
    Zip = $zipName
    Note = $Note
}
Write-HistoryFiles -Root $OutputRoot -Record $historyRecord

Copy-Item -LiteralPath (Join-Path $OutputRoot "ITERATIONS.csv") -Destination (Join-Path $iterationDir "ITERATIONS.csv") -Force
Copy-Item -LiteralPath (Join-Path $OutputRoot "ITERATIONS.md") -Destination (Join-Path $iterationDir "ITERATIONS.md") -Force

$hashLines = New-Object System.Collections.Generic.List[string]
Get-ChildItem -LiteralPath $iterationDir -File -Recurse | Sort-Object FullName | ForEach-Object {
    $relative = $_.FullName.Substring($iterationDir.Length).TrimStart('\', '/')
    $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $hashLines.Add($hash + "  " + ($relative -replace '\\', '/'))
}
$hashLines | Set-Content -LiteralPath (Join-Path $iterationDir "SHA256SUMS.txt") -Encoding ascii

$zipPath = Join-Path $OutputRoot $zipName
$zipHash = "NOT_CREATED"

if (-not $NoZip) {
    if (Test-Path -LiteralPath $zipPath) {
        throw "Refusing to overwrite existing ZIP: $zipPath"
    }

    Write-Step "Creating upload ZIP..."
    Compress-Archive -Path (Join-Path $iterationDir "*") -DestinationPath $zipPath -CompressionLevel Optimal
    $zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    ($zipHash + "  " + $zipName) | Set-Content -LiteralPath ($zipPath + ".sha256") -Encoding ascii
}

$latest = @(
    "iteration=$iteration",
    "folder=$folderName",
    "zip=$zipName",
    "zip_sha256=$zipHash",
    "boot_sha256=$bootSha256",
    "kernel_commit=$KernelCommit",
    "timestamp_local=$timestampLocal",
    "outcome=$Outcome"
)
$latest | Set-Content -LiteralPath (Join-Path $OutputRoot "LATEST.txt") -Encoding utf8

Write-Host ""
Write-Host "=== Lisa TWRP collection complete ==="
Write-Host ("ITERATION      : " + $iteration)
Write-Host ("OUTPUT_DIR     : " + $iterationDir)
if (-not $NoZip) {
    Write-Host ("UPLOAD_THIS_ZIP: " + $zipPath)
    Write-Host ("ZIP_SHA256     : " + $zipHash)
}
Write-Host ("BOOT_SHA256    : " + $bootSha256)
Write-Host ("KERNEL_COMMIT  : " + $KernelCommit)
Write-Host ""
Write-Host "Upload the generated ZIP to ChatGPT. Keep the whole twrp_logs directory locally so older iterations remain retrievable."
