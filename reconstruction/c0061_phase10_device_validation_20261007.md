# Candidate0061 Phase 10 device validation

Date: 2026-10-07
Active device baseline: HyperOS 3.0.9 / Android 16
Device: Xiaomi lisa
Candidate: Candidate0061
Frozen comparison reference: Candidate0059 r43da7c5

## Static-verified Candidate0061 under test

- Build commit: `55105aacd809e748de41230c3ad11ca98ef8cd05`
- Integrated run: `37513703360`
- Kernel release: `5.4.302-qgki-lisa-c0061-r55105aa-by-Tim0320`
- Static-verified boot artifact: `11437434497`
- Artifact name: `lisa-c0061-5.4.302-static-verified-pending-device-a1`
- boot.img SHA256: `65e94493f1b41cc889074b3ccc9c19bfea6977c50b0a56754c535aeb9889f8d4`
- Kernel Image SHA256: `542c80563f11f759ce8837fd8526acb751af701097042e6bc8033fa12d1a77a6`

## Automated gates already complete

Run 37513703360 passed:
- Direct-302 semantic closure: 34 reviewed / 0 unresolved
- Phase7A TOUCH_PERF_ONLY overlay
- Image/modules/dtbs/modpost
- ABI/KMI with removed symbols = 0
- exact kernel identity
- boot static packaging and metadata preservation

No additional kernel source change is justified until runtime evidence exists.

## Runtime validation order

1. Confirm exact kernel identity.
2. Confirm boot completes and device remains stable.
3. Confirm SELinux remains Enforcing.
4. Confirm Wi-Fi works.
5. Confirm battery reporting and charging work.
6. Confirm UFS/data mount behaves normally.
7. Reproduce the same touch workload used against Candidate0059.
8. Record subjective touch latency and jank result.
9. Compare Goodix IRQ activity, affinity/spurious state, cpufreq state, MIGT/package-runtime state, InputReader/InputDispatcher and TouchFeature logs.
10. Only if touch remains regressed, enter Phase 8 FREQ_QOS / Qualcomm touch-boost isolation.

## Required capture

Use:

`reconstruction/tools/collect_lisa_touch_runtime.ps1`

Example:

```powershell
powershell -ExecutionPolicy Bypass -File .\reconstruction\tools\collect_lisa_touch_runtime.ps1 -WindowSeconds 20
```

The collector checks the expected Candidate0061 kernel identity automatically and captures:
- kernel/system identity
- boot_completed
- SELinux state
- Wi-Fi state
- battery/charging
- UFS/storage and /data mount
- touch services / getevent / InputReader / InputDispatcher
- dynamic Goodix IRQ number and before/after IRQ evidence
- cpufreq policies before/after
- MIGT parameters and /proc/package state
- top thread snapshots
- logcat and dmesg
- focused touch/kernel error summaries

## Pass criteria

Candidate0061 can pass Phase 10 only when all of the following are true:
- exact expected kernel release is running;
- boot remains stable;
- SELinux is Enforcing;
- Wi-Fi PASS;
- battery reporting/charging PASS;
- UFS/data PASS;
- no new panic/oops/watchdog/RCU-stall regression;
- touch is not worse than the known-good control and is materially better than Candidate0059 User B;
- Candidate0059's observed jank/stutter improvement is retained or improved.

## Failure routing

If boot or subsystem functionality fails:
- classify the first kernel/runtime blocker before making source changes.

If Goodix IRQ delivery is abnormal:
- investigate IRQ scheduling/affinity/rate before changing touchscreen firmware or driver.

If IRQ delivery is normal but touch latency remains poor:
- proceed to Phase 8 and isolate MIGT FREQ_QOS versus Qualcomm input/touch boost.

Do not use:
- global CPU frequency pinning;
- thermal disable;
- SELinux weakening;
- fake device/ioctl/property success;
- speculative Goodix driver/firmware replacement.
