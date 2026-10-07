param(
    [string]$Adb = "adb",
    [int]$WindowSeconds = 15,
    [string]$ExpectedKernelRelease = "5.4.302-qgki-lisa-c0061-r803b05f-by-Tim0320",
    [string]$OutDir = ("lisa-touch-runtime-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Save-Adb {
    param(
        [string]$Name,
        [string[]]$Args
    )
    $path = Join-Path $OutDir $Name
    & $Adb @Args 2>&1 | Out-File -FilePath $path -Encoding utf8
}

function Read-AdbText {
    param([string[]]$Args)
    return ((& $Adb @Args 2>&1 | Out-String).Trim())
}

$state = Read-AdbText @("get-state")
if ($state -ne "device") {
    throw "ADB device not ready: $state"
}

$kernelRelease = Read-AdbText @("shell","uname","-r")
$selinux = Read-AdbText @("shell","getenforce")
$bootCompleted = Read-AdbText @("shell","getprop","sys.boot_completed")

Save-Adb "00_adb_devices.txt" @("devices","-l")
Save-Adb "01_kernel_identity.txt" @(
    "shell","sh","-c",
    "uname -a; echo kernel_release=$(uname -r); cat /proc/version; echo boot_completed=$(getprop sys.boot_completed)"
)
Save-Adb "02_system_identity.txt" @(
    "shell","sh","-c",
    "for p in ro.product.device ro.product.model ro.build.fingerprint ro.build.version.release ro.build.version.sdk ro.mi.os.version.name ro.miui.ui.version.name ro.vendor.build.security_patch; do echo \"$p=$(getprop $p)\"; done"
)
Save-Adb "03_security_state.txt" @(
    "shell","sh","-c",
    "echo getenforce=$(getenforce 2>/dev/null || true); for p in ro.debuggable ro.force.debuggable ro.secure ro.adb.secure; do echo \"$p=$(getprop $p)\"; done"
)
Save-Adb "04_uptime.txt" @("shell","cat","/proc/uptime")
Save-Adb "05_battery_dumpsys.txt" @("shell","dumpsys","battery")
Save-Adb "06_battery_sysfs.txt" @(
    "shell","sh","-c",
    "for d in /sys/class/power_supply/battery /sys/class/power_supply/usb /sys/class/power_supply/pc_port; do [ -d $d ] || continue; echo ===$d===; for f in status health capacity voltage_now current_now temp charge_full charge_full_design cycle_count online type; do [ -r $d/$f ] && echo $f=$(cat $d/$f); done; done"
)
Save-Adb "07_wifi_state.txt" @(
    "shell","sh","-c",
    "ip link show wlan0 2>&1 || true; ip addr show wlan0 2>&1 || true; echo '--- dumpsys wifi ---'; dumpsys wifi 2>/dev/null | head -n 260 || true"
)
Save-Adb "08_ufs_storage.txt" @(
    "shell","sh","-c",
    "echo '--- block devices ---'; ls -l /dev/block/by-name 2>/dev/null | head -n 120 || true; echo '--- UFS/SCSI ---'; cat /proc/scsi/scsi 2>/dev/null || true; for b in /sys/block/sd*; do [ -e $b ] || continue; echo ===$b===; for f in device/model device/rev device/state size; do [ -r $b/$f ] && echo $f=$(cat $b/$f); done; done; echo '--- data mount ---'; mount | grep -E ' /data | /metadata ' || true"
)
Save-Adb "09_touch_props.txt" @(
    "shell","sh","-c",
    "for p in ro.vendor.touchfeature.type persist.sys.touch_up_boost.enable ro.surface_flinger.set_touch_timer_ms; do echo \"$p=$(getprop $p)\"; done"
)
Save-Adb "10_services_touch.txt" @(
    "shell","sh","-c",
    "service list 2>/dev/null | grep -i touch || true; echo '--- lshal ---'; lshal 2>/dev/null | grep -i -E 'touch|ITouchFeature' || true"
)
Save-Adb "11_getevent_devices.txt" @("shell","getevent","-pl")
Save-Adb "12_dumpsys_input.txt" @("shell","dumpsys","input")
Save-Adb "13_dumpsys_display.txt" @("shell","dumpsys","display")
Save-Adb "14_interrupts_before.txt" @("shell","cat","/proc/interrupts")

$goodixIrq = Read-AdbText @(
    "shell","sh","-c",
    "grep -i -m1 goodix /proc/interrupts 2>/dev/null | cut -d: -f1 | tr -d ' '"
)
if ($goodixIrq -notmatch '^\d+$') {
    $goodixIrq = ""
}
$goodixIrq | Out-File (Join-Path $OutDir "15_goodix_irq_number.txt") -Encoding utf8

if ($goodixIrq) {
    Save-Adb "16_goodix_irq_before.txt" @(
        "shell","sh","-c",
        "for f in /proc/irq/$goodixIrq/smp_affinity_list /proc/irq/$goodixIrq/smp_affinity /proc/irq/$goodixIrq/spurious; do echo ===$f===; cat $f 2>&1 || true; done"
    )
} else {
    "Goodix IRQ not found" | Out-File (Join-Path $OutDir "16_goodix_irq_before.txt") -Encoding utf8
}

Save-Adb "17_cpufreq_before.txt" @(
    "shell","sh","-c",
    "for d in /sys/devices/system/cpu/cpufreq/policy*; do echo ===$d===; for f in scaling_cur_freq scaling_min_freq scaling_max_freq cpuinfo_min_freq cpuinfo_max_freq scaling_governor; do [ -r $d/$f ] && echo $f=$(cat $d/$f); done; done"
)
Save-Adb "18_migt_package_runtime.txt" @(
    "shell","sh","-c",
    "echo '=== /sys/module/migt/parameters ==='; for f in /sys/module/migt/parameters/*; do [ -e $f ] || continue; echo ===$f===; cat $f 2>&1 || true; done; echo '=== /proc/package ==='; for f in $(find /proc/package -maxdepth 3 -type f -print 2>/dev/null | sort); do echo ===$f===; cat $f 2>&1 || true; done"
)
Save-Adb "19_top_threads_before.txt" @(
    "shell","sh","-c",
    "top -H -b -n 1 2>/dev/null | head -n 180 || top -H -n 1 2>/dev/null | head -n 180 || true"
)
Save-Adb "20_logcat_before.txt" @("logcat","-d","-v","threadtime")

Write-Host ""
Write-Host "Phase10 Candidate0061 touch/jank validation window: $WindowSeconds seconds"
Write-Host "- swipe repeatedly"
Write-Host "- test gesture edges"
Write-Host "- test multi-touch"
Write-Host "- reproduce the workload where Candidate0059 felt delayed"
Write-Host ""

Start-Sleep -Seconds $WindowSeconds

Save-Adb "21_interrupts_after.txt" @("shell","cat","/proc/interrupts")
if ($goodixIrq) {
    Save-Adb "22_goodix_irq_after.txt" @(
        "shell","sh","-c",
        "for f in /proc/irq/$goodixIrq/smp_affinity_list /proc/irq/$goodixIrq/smp_affinity /proc/irq/$goodixIrq/spurious; do echo ===$f===; cat $f 2>&1 || true; done"
    )
} else {
    "Goodix IRQ not found" | Out-File (Join-Path $OutDir "22_goodix_irq_after.txt") -Encoding utf8
}
Save-Adb "23_cpufreq_after.txt" @(
    "shell","sh","-c",
    "for d in /sys/devices/system/cpu/cpufreq/policy*; do echo ===$d===; for f in scaling_cur_freq scaling_min_freq scaling_max_freq cpuinfo_min_freq cpuinfo_max_freq scaling_governor; do [ -r $d/$f ] && echo $f=$(cat $d/$f); done; done"
)
Save-Adb "24_top_threads_after.txt" @(
    "shell","sh","-c",
    "top -H -b -n 1 2>/dev/null | head -n 180 || top -H -n 1 2>/dev/null | head -n 180 || true"
)
Save-Adb "25_logcat_after.txt" @("logcat","-d","-v","threadtime")
Save-Adb "26_dmesg.txt" @(
    "shell","sh","-c",
    "dmesg 2>&1 || su 0 dmesg 2>&1 || true"
)
Save-Adb "27_kernel_error_summary.txt" @(
    "shell","sh","-c",
    "(dmesg 2>/dev/null || su 0 dmesg 2>/dev/null || true) | grep -i -E 'panic|oops|BUG:|watchdog|rcu.*stall|goodix|touch|ufs|wifi|wlan|battery|power_supply|migt|freq_qos' | tail -n 500 || true"
)

$before = Get-Content (Join-Path $OutDir "14_interrupts_before.txt")
$after = Get-Content (Join-Path $OutDir "21_interrupts_after.txt")
$beforeGoodix = $before | Select-String -Pattern "goodix|touch" -CaseSensitive:$false
$afterGoodix = $after | Select-String -Pattern "goodix|touch" -CaseSensitive:$false

@(
    "window_seconds=$WindowSeconds"
    "goodix_irq=$goodixIrq"
    "=== interrupts before ==="
    ($beforeGoodix | ForEach-Object { $_.Line })
    "=== interrupts after ==="
    ($afterGoodix | ForEach-Object { $_.Line })
) | Out-File (Join-Path $OutDir "28_goodix_irq_window.txt") -Encoding utf8

$patterns = @(
    "TouchFeature",
    "ITouchFeature",
    "HwBinder Error",
    "boost for qcom touch up failed",
    "RefreshRateSelector: Touch Boost",
    "InputDispatcher",
    "InputReader",
    "goodix",
    "jank",
    "frame duration",
    "FREQ_QOS",
    "migt"
)
$logAfter = Get-Content (Join-Path $OutDir "25_logcat_after.txt")
$selected = foreach ($line in $logAfter) {
    foreach ($p in $patterns) {
        if ($line -match [regex]::Escape($p)) {
            $line
            break
        }
    }
}
$selected | Out-File (Join-Path $OutDir "29_touch_log_summary.txt") -Encoding utf8

$identityPass = ($kernelRelease -eq $ExpectedKernelRelease)
$selinuxPass = ($selinux -eq "Enforcing")
$bootPass = ($bootCompleted -eq "1")

@(
    "candidate=0061"
    "baseline=HyperOS 3.0.9 / Android 16"
    "expected_kernel_release=$ExpectedKernelRelease"
    "actual_kernel_release=$kernelRelease"
    "kernel_identity_pass=$identityPass"
    "boot_completed=$bootCompleted"
    "boot_completed_pass=$bootPass"
    "selinux=$selinux"
    "selinux_enforcing_pass=$selinuxPass"
    "goodix_irq=$goodixIrq"
    "window_seconds=$WindowSeconds"
    "manual_required_touch_result=PASS/FAIL"
    "manual_required_jank_result=IMPROVED/SAME/REGRESSED"
    "manual_required_wifi_result=PASS/FAIL"
    "manual_required_battery_charging_result=PASS/FAIL"
    "manual_required_ufs_result=PASS/FAIL"
) | Out-File (Join-Path $OutDir "30_phase10_summary.txt") -Encoding utf8

Compress-Archive -Path (Join-Path $OutDir "*") -DestinationPath ($OutDir + ".zip") -Force
Write-Host "Created: $OutDir.zip"
Write-Host "Kernel identity pass: $identityPass"
Write-Host "SELinux enforcing pass: $selinuxPass"
Write-Host "Boot completed pass: $bootPass"
