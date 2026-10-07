# Candidate0061 Phase 10 device validation

Date: 2026-10-07
Active device baseline: HyperOS 3.0.9 / Android 16
Device: Xiaomi lisa
Candidate: Candidate0061
Frozen comparison reference: Candidate0059 r43da7c5

## Static-verified Candidate0061 under test

- Build commit: `803b05f1932d3109f7ec1f4f301c20f911de167d`
- Integrated run: `37571737761`
- Kernel release: `5.4.302-qgki-lisa-c0061-r803b05f-by-Tim0320`
- Static-verified boot artifact: `11462052521`
- Artifact name: `lisa-c0061-5.4.302-static-verified-pending-device-a1`
- boot.img SHA256: `ffcad0916bd53d17d6c8bd8f336dab878a2862404846e390fc00c7bb48bb38e7`
- Kernel Image SHA256: `5b3bd0f7e12ee729da7c83b78909c90696cfc22ef5a9b543224c7b8ceec84e3f`

## Automated gates already complete

Run 37571737761 passed:
- repaired Candidate0059 IPA/PAS inheritance: PASS
- Direct-302 semantic closure: 34 reviewed / 0 unresolved
- Phase7A TOUCH_PERF_ONLY overlay
- Image/modules/dtbs/modpost
- ABI/KMI with removed symbols = 0
- exact kernel identity
- boot static packaging and metadata preservation

Artifact 11437434497 is retired because it failed with a one-screen reset before System and was later shown to have an incomplete Candidate0059 IPA/PAS reconstruction. Artifact 11462052521 is the repaired Phase10 candidate.

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
