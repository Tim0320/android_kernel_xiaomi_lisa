param(
    [string]$Adb = "adb",
    [int]$WindowSeconds = 15,
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

$state = (& $Adb get-state 2>&1 | Out-String).Trim()
if ($state -ne "device") {
    throw "ADB device not ready: $state"
}

Save-Adb "00_adb_devices.txt" @("devices","-l")
Save-Adb "01_proc_version.txt" @("shell","cat","/proc/version")
Save-Adb "02_uptime.txt" @("shell","cat","/proc/uptime")
Save-Adb "03_touch_props.txt" @(
    "shell","sh","-c",
    "for p in ro.debuggable ro.force.debuggable ro.secure ro.adb.secure ro.vendor.touchfeature.type persist.sys.touch_up_boost.enable ro.surface_flinger.set_touch_timer_ms; do echo \"$p=$(getprop $p)\"; done"
)
Save-Adb "04_services_touch.txt" @(
    "shell","sh","-c",
    "service list 2>/dev/null | grep -i touch || true; echo '--- lshal ---'; lshal 2>/dev/null | grep -i -E 'touch|ITouchFeature' || true"
)
Save-Adb "05_getevent_devices.txt" @("shell","getevent","-pl")
Save-Adb "06_dumpsys_input.txt" @("shell","dumpsys","input")
Save-Adb "07_dumpsys_display.txt" @("shell","dumpsys","display")
Save-Adb "08_interrupts_before.txt" @("shell","cat","/proc/interrupts")
Save-Adb "09_irq305_before.txt" @(
    "shell","sh","-c",
    "for f in /proc/irq/305/smp_affinity_list /proc/irq/305/smp_affinity /proc/irq/305/spurious; do echo ===$f===; cat $f 2>&1 || true; done"
)
Save-Adb "10_cpufreq_before.txt" @(
    "shell","sh","-c",
    "for d in /sys/devices/system/cpu/cpufreq/policy*; do echo ===$d===; for f in scaling_cur_freq scaling_min_freq scaling_max_freq cpuinfo_min_freq cpuinfo_max_freq scaling_governor; do [ -r $d/$f ] && echo $f=$(cat $d/$f); done; done"
)
Save-Adb "11_migt_params.txt" @(
    "shell","sh","-c",
    "echo '=== /sys/module/migt/parameters ==='; for f in /sys/module/migt/parameters/*; do [ -e $f ] || continue; echo ===$f===; cat $f 2>&1 || true; done; echo '=== /proc/package ==='; find /proc/package -maxdepth 3 -type f -print 2>/dev/null | sort || true"
)
Save-Adb "12_top_threads_before.txt" @(
    "shell","sh","-c",
    "top -H -b -n 1 2>/dev/null | head -n 160 || top -H -n 1 2>/dev/null | head -n 160 || true"
)
Save-Adb "13_logcat_before.txt" @("logcat","-d","-v","threadtime")

Write-Host ""
Write-Host "For the next $WindowSeconds seconds, reproduce the bad touch behavior:"
Write-Host "- swipe repeatedly"
Write-Host "- use the gesture edges"
Write-Host "- do multi-touch if that is where it is worse"
Write-Host ""

Start-Sleep -Seconds $WindowSeconds

Save-Adb "14_interrupts_after.txt" @("shell","cat","/proc/interrupts")
Save-Adb "15_irq305_after.txt" @(
    "shell","sh","-c",
    "for f in /proc/irq/305/smp_affinity_list /proc/irq/305/smp_affinity /proc/irq/305/spurious; do echo ===$f===; cat $f 2>&1 || true; done"
)
Save-Adb "16_cpufreq_after.txt" @(
    "shell","sh","-c",
    "for d in /sys/devices/system/cpu/cpufreq/policy*; do echo ===$d===; for f in scaling_cur_freq scaling_min_freq scaling_max_freq cpuinfo_min_freq cpuinfo_max_freq scaling_governor; do [ -r $d/$f ] && echo $f=$(cat $d/$f); done; done"
)
Save-Adb "17_top_threads_after.txt" @(
    "shell","sh","-c",
    "top -H -b -n 1 2>/dev/null | head -n 160 || top -H -n 1 2>/dev/null | head -n 160 || true"
)
Save-Adb "18_logcat_after.txt" @("logcat","-d","-v","threadtime")
Save-Adb "19_dmesg.txt" @(
    "shell","sh","-c",
    "dmesg 2>&1 || su 0 dmesg 2>&1 || true"
)

$before = Get-Content (Join-Path $OutDir "08_interrupts_before.txt")
$after = Get-Content (Join-Path $OutDir "14_interrupts_after.txt")
$beforeGoodix = $before | Select-String -Pattern "goodix|touch" -CaseSensitive:$false
$afterGoodix = $after | Select-String -Pattern "goodix|touch" -CaseSensitive:$false

@(
    "window_seconds=$WindowSeconds"
    "=== interrupts before ==="
    ($beforeGoodix | ForEach-Object { $_.Line })
    "=== interrupts after ==="
    ($afterGoodix | ForEach-Object { $_.Line })
) | Out-File (Join-Path $OutDir "20_goodix_irq_window.txt") -Encoding utf8

$patterns = @(
    "TouchFeature",
    "ITouchFeature",
    "HwBinder Error",
    "boost for qcom touch up failed",
    "RefreshRateSelector: Touch Boost",
    "InputDispatcher",
    "InputReader",
    "irq/305-goodix",
    "goodix",
    "jank",
    "frame duration"
)

$logAfter = Get-Content (Join-Path $OutDir "18_logcat_after.txt")
$selected = foreach ($line in $logAfter) {
    foreach ($p in $patterns) {
        if ($line -match [regex]::Escape($p)) {
            $line
            break
        }
    }
}
$selected | Out-File (Join-Path $OutDir "21_touch_log_summary.txt") -Encoding utf8

Compress-Archive -Path (Join-Path $OutDir "*") -DestinationPath ($OutDir + ".zip") -Force
Write-Host "Created: $OutDir.zip"
