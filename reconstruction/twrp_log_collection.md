# Lisa TWRP failure-log collector

This repository includes scripts/collect_lisa_twrp_logs.ps1, a Windows PowerShell collector for post-failure Lisa boot debugging through TWRP/recovery ADB.

## Goal

After flashing a candidate boot.img, if the phone fails to enter Android, boot into TWRP and run one command. The collector creates a new immutable iteration directory, captures persistent kernel/recovery evidence, records the candidate boot hash and version metadata, updates a cumulative iteration index, and creates a ZIP that can be uploaded for analysis.

The collector never intentionally reuses an existing iteration number or overwrites an existing ZIP.

## Requirements

- Windows PowerShell 5.1 or newer.
- Android Platform Tools with adb.exe available in PATH.
- Phone booted into TWRP/recovery with ADB visible.
- Keep the twrp_logs directory between tests. It contains the cumulative iteration registry.

## Normal use

If the candidate boot.img is in the current directory:

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\collect_lisa_twrp_logs.ps1 -Outcome "black-screen-reboot"
~~~

For the most precise mapping, pass the exact candidate image and optional source commit:

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\collect_lisa_twrp_logs.ps1 `
  -BootImagePath "F:\Rom_Port\candidate\boot.img" `
  -KernelCommit "2081aeb8d69a101fb596514ca494b943e44d931c" `
  -BuildLabel "qgki-repack-v2" `
  -Outcome "black-screen-reboot" `
  -Note "black screen for several seconds, then automatic reboot"
~~~

This command is intended to run on your own Windows PC after the failed boot attempt, while the phone is connected in TWRP/recovery over ADB. Upload only the generated ZIP for analysis.

KernelCommit is optional. The boot.img SHA256 is the primary identity. If the repository is cloned locally and KernelCommit is omitted, the script tries to record the local Git HEAD.

## What to upload

At the end, the script prints a line beginning with:

~~~text
UPLOAD_THIS_ZIP:
~~~

Upload that ZIP. Do not rename files inside it.

## Iteration model

Default output is:

~~~text
twrp_logs/
  ITERATIONS.csv
  ITERATIONS.md
  LATEST.txt
  iter-0001_YYYYMMDD-HHMMSS_<label>_<boot-hash>/
    manifest.json
    SUMMARY.txt
    SHA256SUMS.txt
    ITERATIONS.csv
    ITERATIONS.md
    raw/
    pulled/
  lisa-twrp-iter-0001_....zip
  lisa-twrp-iter-0001_....zip.sha256
~~~

Each new run becomes iter-0002, iter-0003, and so on. The newest ZIP contains a snapshot of the cumulative iteration index, so later analysis can map the new failure back to previous candidate boot hashes and outcomes.

## Evidence captured

The collector attempts to capture:

- /sys/fs/pstore, including console-ramoops, dmesg-ramoops, pmsg-ramoops, and related persistent crash records when available.
- /proc/last_kmsg when exposed by the recovery kernel.
- /data/vendor/ramoops when present.
- TWRP /tmp/recovery.log.
- /cache/recovery/log and /cache/recovery/last_log when present.
- Current recovery dmesg.
- Current recovery logcat -b all -d when available.
- /proc/cmdline, /proc/bootconfig, mount state, block-device aliases, boot reason, active slot, AVB state, model/device, and TWRP version.
- Candidate boot.img SHA256, byte size, timestamp, build label, optional kernel commit, outcome, and note.
- SHA256 for every file in the iteration package.

The complete getprop capture is filtered for obvious serial/IMEI/MEID/MAC-style property keys before it is written.

## Recommended test loop

1. Keep the exact candidate boot.img.
2. Flash it using the intended Lisa slot/test procedure.
3. Observe the failure mode.
4. Boot into TWRP without performing unrelated wipes or log-clearing operations.
5. Connect USB and confirm adb devices.
6. Run the collector once.
7. Upload the generated ZIP.
8. Keep the local twrp_logs directory for later comparison.
9. For the next kernel/boot candidate, repeat; a new iteration number is created automatically.

The most useful files for an early boot failure are normally pulled/pstore, raw/09_pstore_contents.txt, raw/10_last_kmsg.txt, and the TWRP recovery logs.
