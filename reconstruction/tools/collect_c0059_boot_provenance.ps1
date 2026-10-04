param(
    [string]$Adb = "adb",
    [string]$OutDir = ("c0059-boot-provenance-" + (Get-Date -Format "yyyyMMdd-HHmmss")),
    [string]$ExpectedBootSha256 = ""
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Run-AdbText {
    param([string]$Name, [string[]]$Args)
    $path = Join-Path $OutDir $Name
    try {
        & $Adb @Args 2>&1 | Out-File -FilePath $path -Encoding utf8
    } catch {
        $_ | Out-File -FilePath $path -Encoding utf8
    }
}

$state = (& $Adb get-state 2>&1 | Out-String).Trim()
if ($state -ne "device") {
    throw "ADB device not ready: $state"
}

Run-AdbText "adb_devices.txt" @("devices","-l")
Run-AdbText "proc_version.txt" @("shell","cat","/proc/version")
Run-AdbText "proc_cmdline.txt" @("shell","cat","/proc/cmdline")
Run-AdbText "proc_bootconfig.txt" @("shell","sh","-c","cat /proc/bootconfig 2>&1 || true")
Run-AdbText "getprop.txt" @("shell","getprop")
Run-AdbText "pid1_exe.txt" @("shell","sh","-c","readlink -f /proc/1/exe; ls -laZ /proc/1/exe 2>&1")
Run-AdbText "mountinfo_pid1.txt" @("shell","cat","/proc/1/mountinfo")
Run-AdbText "mounts.txt" @("shell","cat","/proc/mounts")
Run-AdbText "ps_contexts.txt" @("shell","ps","-AZ")
Run-AdbText "debug_files_shell.txt" @("shell","sh","-c","for p in /force_debuggable /adb_debug.prop /userdebug_plat_sepolicy.cil /debug_ramdisk /first_stage_ramdisk /init /system/bin/init; do echo ====\\$p====; ls -ladZ \\$p 2>&1; [ -f \\$p ] && sha256sum \\$p 2>&1; done")
Run-AdbText "root_indicators_shell.txt" @("shell","sh","-c","command -v magisk 2>&1; command -v resetprop 2>&1; command -v su 2>&1; ls -ladZ /data/adb /data/adb/modules 2>&1; getprop | grep -Ei 'magisk|zygisk|kernelsu|apatch|debuggable|force.debuggable|ro.secure|adb.secure'")

$slotRaw = (& $Adb shell getprop ro.boot.slot_suffix 2>$null | Out-String).Trim()
$slot = $slotRaw.TrimStart("_")
if (-not $slot) { $slot = "a" }
$bootBlock = "/dev/block/by-name/boot_$slot"
$vendorBootBlock = "/dev/block/by-name/vendor_boot_$slot"

$rootProbe = "id; echo ====DEBUG_FILES====; for p in /force_debuggable /adb_debug.prop /userdebug_plat_sepolicy.cil /debug_ramdisk /first_stage_ramdisk /init /system/bin/init; do echo ====\\$p====; ls -ladZ \\$p 2>&1; [ -f \\$p ] && sha256sum \\$p 2>&1; done; echo ====ROOT_OVERLAY====; command -v magisk 2>&1; command -v resetprop 2>&1; ls -ladZ /data/adb /data/adb/modules 2>&1; ps -AZ | grep -Ei 'magisk|zygisk|kernelsu|ksud|apatch' || true; echo ====BOOT_HASH====; blockdev --getsize64 $bootBlock 2>&1; sha256sum $bootBlock 2>&1; echo ====VENDOR_BOOT_HASH====; blockdev --getsize64 $vendorBootBlock 2>&1; sha256sum $vendorBootBlock 2>&1"
Run-AdbText "root_provenance.txt" @("shell","su","0","sh","-c",$rootProbe)

$bootHash = ""
$rootFile = Join-Path $OutDir "root_provenance.txt"
if (Test-Path $rootFile) {
    $content = Get-Content $rootFile -Raw
    $escaped = [regex]::Escape($bootBlock)
    $m = [regex]::Match($content, "(?im)^([0-9a-f]{64})\\s+" + $escaped + "$")
    if ($m.Success) { $bootHash = $m.Groups[1].Value.ToLowerInvariant() }
}

$summary = [ordered]@{
    collected_at = (Get-Date).ToString("o")
    slot_suffix = $slotRaw
    boot_block = $bootBlock
    vendor_boot_block = $vendorBootBlock
    expected_boot_sha256 = $ExpectedBootSha256.ToLowerInvariant()
    live_boot_sha256 = $bootHash
    live_boot_matches_expected = $null
}
if ($ExpectedBootSha256 -and $bootHash) {
    $summary.live_boot_matches_expected = ($bootHash -eq $ExpectedBootSha256.ToLowerInvariant())
}
$summary | ConvertTo-Json -Depth 4 | Out-File (Join-Path $OutDir "summary.json") -Encoding utf8

$zip = "$OutDir.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $OutDir "*") -DestinationPath $zip -CompressionLevel Optimal
Write-Host "Created: $zip"
Write-Host "Expected boot SHA256: $ExpectedBootSha256"
Write-Host "Live boot SHA256:     $bootHash"
if ($ExpectedBootSha256 -and $bootHash) {
    Write-Host ("Match: " + ($bootHash -eq $ExpectedBootSha256.ToLowerInvariant()))
}
