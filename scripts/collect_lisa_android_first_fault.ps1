param(
    [ValidateRange(15, 600)][int]$WindowSeconds = 120,
    [string]$OutputRoot = 'D:\1.ROM_Prot\lisa\pull_log',
    [switch]$SelfTest
)

# v1.0.0: read-only host-side Android first-fault capture.
# Only adb state device is eligible; recovery/unauthorized/offline are not.
$ErrorActionPreference = 'Stop'
$ScriptVersion = '1.0.0'

function Normalize-AdbState([string]$Value) {
    $v = $Value.Trim()
    if ($v -eq 'device') { return 'android_device' }
    if ($v -eq 'recovery') { return 'twrp_recovery' }
    if ($v -eq 'unauthorized') { return 'unauthorized' }
    if ($v -eq 'offline') { return 'offline' }
    return 'unavailable'
}

if ($SelfTest) {
    if ((Normalize-AdbState 'device') -ne 'android_device') { throw 'DEVICE_STATE_TEST_FAILED' }
    foreach ($v in @('recovery', 'unauthorized', 'offline', '', 'error: no devices/emulators found')) {
        if ((Normalize-AdbState $v) -eq 'android_device') { throw 'RECOVERY_MISCLASSIFIED_AS_ANDROID' }
    }
    Write-Output 'LISA_ANDROID_FIRST_FAULT_SELF_TEST=PASS'
    exit 0
}

$root = [System.IO.Path]::GetFullPath($OutputRoot)
New-Item -ItemType Directory -Path $root -Force | Out-Null
Set-Location $root
$adb = (Get-Command 'adb.exe' -ErrorAction Stop).Source
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$folder = Join-Path $root ('lisa-android-firstfault-' + $stamp)
New-Item -ItemType Directory -Path $folder -Force | Out-Null
$timeline = Join-Path $folder 'state_timeline.txt'
$summary = Join-Path $folder 'SUMMARY.txt'
$androidSeen = $false
$lastState = ''
$stream = $null
$androidCount = 0

function Snapshot-ReadOnly([string]$Label, [string[]]$Arguments) {
    $out = Join-Path $folder ($Label + '.txt')
    try {
        & $adb @Arguments 2>&1 | Out-File -LiteralPath $out -Encoding utf8 -Width 4096
        ('{0} exit={1}' -f $Label, $LASTEXITCODE) | Add-Content -LiteralPath $timeline
    } catch {
        ('{0} exception={1}' -f $Label, $_.Exception.Message) | Add-Content -LiteralPath $timeline
    }
}

$deadline = [DateTime]::UtcNow.AddSeconds($WindowSeconds)
Write-Host "COLLECTOR_VERSION: $ScriptVersion"
Write-Host "OUTPUT_ROOT: $root"
Write-Host 'Start capture BEFORE selecting Reboot System in TWRP.'
Write-Host "Only state 'device' is Android. Recovery and unauthorized do not count."
Write-Host "Monitoring up to $WindowSeconds seconds; do not flash boot.img."

try {
    while ([DateTime]::UtcNow -lt $deadline) {
        $raw = ''
        try { $raw = (& $adb -d get-state 2>$null | Out-String).Trim() }
        catch { $raw = '' }
        $state = Normalize-AdbState $raw

        if ($state -ne $lastState) {
            ('{0} UTC state={1} raw={2}' -f [DateTime]::UtcNow.ToString('o'), $state, $raw) | Add-Content -LiteralPath $timeline
            Write-Host "ADB_STATE: $state"
            $lastState = $state
        }

        if ($state -eq 'android_device' -and -not $androidSeen) {
            $androidSeen = $true
            $androidCount++
            $prefix = 'android-session-' + $androidCount
            ('ANDROID_ADB_DETECTED_UTC=' + [DateTime]::UtcNow.ToString('o')) | Add-Content -LiteralPath $timeline

            try {
                $stream = Start-Process -FilePath $adb -ArgumentList @('-d', 'logcat', '-b', 'all', '-v', 'threadtime') -RedirectStandardOutput (Join-Path $folder ($prefix + '-logcat-live.txt')) -RedirectStandardError (Join-Path $folder ($prefix + '-logcat-live.err.txt')) -PassThru -NoNewWindow
                ('LOGCAT_STREAM_PID=' + $stream.Id) | Add-Content -LiteralPath $timeline
            } catch {
                ('LOGCAT_STREAM_START_FAILED=' + $_.Exception.Message) | Add-Content -LiteralPath $timeline
            }

            Snapshot-ReadOnly ($prefix + '-logcat-dump') @('-d', 'logcat', '-b', 'all', '-d', '-v', 'threadtime')
            Snapshot-ReadOnly ($prefix + '-proc-modules') @('-d', 'shell', 'cat /proc/modules')
            Snapshot-ReadOnly ($prefix + '-boot-properties') @('-d', 'shell', 'getprop ro.bootmode; getprop ro.build.version.release; getprop sys.boot_completed')
            Snapshot-ReadOnly ($prefix + '-dmesg-if-permitted') @('-d', 'shell', 'dmesg')
        }

        if ($androidSeen -and $state -ne 'android_device') {
            ('ANDROID_ADB_LOST_UTC=' + [DateTime]::UtcNow.ToString('o')) | Add-Content -LiteralPath $timeline
            break
        }
        Start-Sleep -Milliseconds 250
    }
} finally {
    if ($null -ne $stream) {
        try {
            if (-not $stream.HasExited) { Stop-Process -Id $stream.Id -Force -ErrorAction SilentlyContinue }
        } catch {}
        $stream.Dispose()
    }
}

$status = if ($androidSeen) { 'ANDROID_ADB_OBSERVED' } else { 'ANDROID_ADB_NOT_OBSERVED' }
@(
    "collector=$ScriptVersion"
    'device=lisa'
    'collection_scope=ANDROID_ADB_READONLY_NOT_TWRP_RUNTIME'
    "outcome=$status"
    "window_seconds=$WindowSeconds"
    'flash_performed_by_script=false'
    'module_load_or_boot_success_not_inferred=true'
    'security=logs_may_contain_private_user_data_UPLOAD_PRIVATELY'
) | Set-Content -LiteralPath $summary -Encoding UTF8

$logFiles = Get-ChildItem -LiteralPath $folder -File | Where-Object { $_.Name -like '*logcat*.txt' }
if ($logFiles) {
    $pattern = 'modprobe|nfc_i2c|nqnfcinfo|xhci|dwc3|Unknown symbol|disagrees about version|Invalid module format|watchdog|fatal|panic|avc: denied'
    $found = foreach ($file in $logFiles) { Select-String -LiteralPath $file.FullName -Pattern $pattern -ErrorAction SilentlyContinue }
    if ($found) { $found | ForEach-Object { $_.Line } | Set-Content -LiteralPath (Join-Path $folder 'firstfault-filtered-hints.txt') -Encoding UTF8 }
}

$zip = $folder + '.zip'
Compress-Archive -Path (Join-Path $folder '*') -DestinationPath $zip -Force
Write-Host "ANDROID_ADB_STATUS: $status"
Write-Host "UPLOAD_THIS_ZIP: $zip"
Write-Host 'If NOT_OBSERVED, this is not evidence of Android module loading.'
