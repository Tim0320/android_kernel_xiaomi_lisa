# Candidate0061: acquire only missing OEM vendor module-selector evidence.
# Requires TWRP recovery ADB. Mounts mapped vendor_a EROFS read-only in recovery tmpfs.
# NO partition write, flash, remount rw, vbmeta, SELinux or device property changes.
[CmdletBinding()]
param(
    [string]$OutputRoot = '',
    [switch]$SelfTest
)
$ErrorActionPreference = 'Stop'
$FixedFiles = @(
    'bin/modprobe',
    'bin/vendor_modprobe.sh',
    'lib/modules/modules.dep',
    'lib/modules/modules.load',
    'lib/modules/modules.alias',
    'lib/modules/modules.softdep',
    'lib/modules/modules.blocklist',
    'lib/modules/5.4-gki/modules.dep',
    'lib/modules/5.4-gki/modules.load',
    'lib/modules/5.4-gki/modules.alias',
    'lib/modules/5.4-gki/modules.softdep',
    'lib/modules/5.4-gki/modules.blocklist'
)
if ($SelfTest) {
    if ($FixedFiles.Count -ne 12 -or ($FixedFiles | Select-Object -Unique).Count -ne 12) {
        throw 'C0061_VENDOR_PROVENANCE_ALLOWLIST_BAD'
    }
    foreach ($f in $FixedFiles) {
        if ($f -notmatch '^(bin/(modprobe|vendor_modprobe\.sh)|lib/modules/(5\.4-gki/)?modules\.(dep|load|alias|softdep|blocklist))$') {
            throw "Unexpected read-only path: $f"
        }
    }
    Write-Output 'C0061_VENDOR_LOADER_READONLY_SELF_TEST=PASS'
    return
}

$adbCommand = Get-Command adb -CommandType Application -ErrorAction Stop
$adbPath = $adbCommand.Source
function Invoke-DeviceAdb {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)
    $out = & $script:adbPath @Arguments 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw ("ADB_FAIL exit={0} command={1} output={2}" -f $code, ($Arguments -join ' '), ($out -join ' ')) }
    return @($out)
}
$state = ((Invoke-DeviceAdb -Arguments @('get-state')) -join "`n").Trim()
if ($state -ne 'recovery') { throw "ADB_STATE_NOT_RECOVERY: $state. No Android-System adb or flash will be attempted." }
$now = Get-Date -Format 'yyyyMMdd-HHmmss'
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path (Get-Location).Path "C0061-Vendor-Loader-RO-$now"
}
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Refusing overwrite: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$MountPoint = "/tmp/c0061_vendor_ro_$now"
$source = '/dev/block/mapper/vendor_a'
$mounted = $false
$manifest = New-Object System.Collections.Generic.List[Object]
try {
    $id = (Invoke-DeviceAdb -Arguments @('shell','id')) -join "`n"
    if ($id -notmatch 'uid=0\(') { throw 'TWRP ADB shell is not root; refusing mount attempt' }
    Invoke-DeviceAdb -Arguments @('shell',"mkdir -p '$MountPoint' && mount -t erofs -o ro '$source' '$MountPoint'") | Out-Null
    $mounted = $true
    $mountText = (Invoke-DeviceAdb -Arguments @('shell','cat /proc/mounts')) -join "`n"
    $mountRow = @($mountText -split "`n" | Where-Object { $_ -like "* $MountPoint *" })
    if ($mountRow.Count -ne 1 -or $mountRow[0] -notmatch ' erofs ro[, ]') {
        throw "EROFS_READ_ONLY_MOUNT_NOT_CONFIRMED: $($mountRow -join ' ')"
    }
    foreach ($item in $FixedFiles) {
        $remote = "$MountPoint/$item"
        $local = Join-Path $OutputRoot ($item -replace '/',[IO.Path]::DirectorySeparatorChar)
        $localDir = Split-Path -Parent $local
        if (-not (Test-Path -LiteralPath $localDir)) { New-Item -ItemType Directory -Path $localDir -Force | Out-Null }
        # Only a probe for file presence; a MISSING row is not a runtime loader decision.
        $testOut = & $adbPath shell "test -f '$remote'" 2>&1
        if ($LASTEXITCODE -ne 0) {
            $manifest.Add([ordered]@{ path=$item; captured=$false; reason='file_absent_or_inaccessible' })
            continue
        }
        Invoke-DeviceAdb -Arguments @('pull',$remote,$local) | Out-Null
        if (-not (Test-Path -LiteralPath $local -PathType Leaf)) { throw "ADB_PULL_MISSING_LOCAL: $item" }
        $hash = (Get-FileHash -LiteralPath $local -Algorithm SHA256).Hash.ToLowerInvariant()
        $size = (Get-Item -LiteralPath $local).Length
        $manifest.Add([ordered]@{path=$item;captured=$true;bytes=$size;sha256=$hash})
    }
    $evidence = [ordered]@{
        case='C0061 OEM vendor module selector files'
        device_adb_state='recovery'
        device_mount_source=$source
        mount_fs='erofs'
        mount_mode='ro'
        collection_time_local=(Get-Date).ToString('o')
        device_runtime_first_probe='UNKNOWN_NOT_EXECUTED'
        vendor_loader_executed=$false
        android_system_logs_collected=$false
        fresh_kernel_panic_collected=$false
        flash_authorized=$false
        files=@($manifest.ToArray())
        interpretation='No modules.load first-line inference. Files are static; actual Android vendor modprobe -l and process exit remain unobserved.'
        privacy='OEM binary and script are private; do not commit them to public GitHub.'
    }
    $json = Join-Path $OutputRoot 'c0061_vendor_loader_readonly_manifest.json'
    $evidence | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $json -Encoding UTF8
    Write-Output "C0061_VENDOR_LOADER_READONLY_CAPTURE=COMPLETE"
    Write-Output "C0061_VENDOR_LOADER_OUTPUT=$OutputRoot"
    Write-Output "C0061_VENDOR_LOADER_FIRST_PROBE=UNKNOWN"
    Write-Output "C0061_FLASH_AUTHORIZED=false"
}
finally {
    if ($mounted) {
        $null = & $adbPath shell "umount '$MountPoint'" 2>&1
        if ($LASTEXITCODE -ne 0) { Write-Warning "Recovery tmpfs mount remains: $MountPoint; no partition write attempted." }
    }
}