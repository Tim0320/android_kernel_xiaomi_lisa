# Candidate0059 User B runtime result - touch regression

Date: 2026-10-05
Device: Xiaomi lisa
Candidate: Candidate0059
Kernel identity observed in supplied live bundle:
- 5.4.289-qgki-lisa-c0059-r43da7c5-by-Tim0320

## User result

User B reports:
- Android16 stutter/jank feels somewhat improved compared with the earlier baseline.
- Touch behavior is noticeably worse / more severe.

This is a runtime regression and blocks blindly inheriting Candidate0059's full performance path into the later 5.4.302 integrated candidate.

## Evidence from lisa-live-20261005-122522

Developer/debug property tuple is healthy:
- ro.debuggable=0
- ro.force.debuggable=0
- ro.secure=1
- ro.adb.secure=1

Therefore this User B test does not reproduce the separate Android14 Developer Options debug-property fault.

Touch stack observations:
- touchfeature HAL/service is present and reports v2 support.
- one TouchFeatureUtil request fails:
  - HwBinder Error: (-74)
  - getModeWhitelist failed
- Linux errno 74 on generic arm64 is EBADMSG ("Bad message").
- SELinux logs contain denied service-manager lookup attempts for
  vendor.xiaomi.hw.touchfeature.ITouchFeature/default, but the client subsequently
  obtains the v2 service, so this log alone is not proof that SELinux is the touch root cause.
- SurfaceFlinger logs 79 "RefreshRateSelector: Touch Boost" events.
- framework logs 18:
  "boost for qcom touch up failed because of timediff < 100ms"
  These appear to be a touch-up boost rate-limit/failure path and need comparison
  with a known-good kernel before they can be called Candidate0059-specific.
- Goodix threaded IRQ is active as irq/305-goodix_.

AM_CPU samples for irq/305-goodix_:
- uptime 22.239 s, system CPU 0.090 s
- uptime 56.223 s, system CPU 0.810 s
- uptime 70.168 s, system CPU 2.940 s
- uptime 140.669 s, system CPU 8.670 s

The later intervals show substantial Goodix IRQ-thread CPU activity during the
interactive test. This may be expected during sustained touch input; without
/proc/interrupts deltas and a known-good control it is not yet classified as an IRQ storm.

At 12:22:56 HyperOS SSRU reports system_server CPU usage 82.10% over its monitor
window, with InputDispatcher accounting for about 2.97 percentage points.
This is compatible with elevated input latency but does not identify a single kernel cause.

No direct Goodix firmware/reset/I2C/SPI failure was visible in the supplied
logcat. dmesg_live.txt is empty, so kernel-side touch IRQ/driver diagnostics are missing.

## Candidate0059 source relationship

Candidate0059 does NOT directly replace the Goodix/touchscreen driver.
Historical Lisa ABI work already restored stock-compatible touch-facing CRCs,
including:
- last_touch_events_collect
- update_palm_sensor_value
- xiaomitouch_register_modedata

Candidate0059 performance work instead changes scheduler/performance paths:
- package-runtime accounting in WALT
- MIGT scheduler/render/game-load state
- /dev/migt control
- policy-scoped FREQ_QOS requests

Therefore the first investigation target is interaction between Candidate0059
performance scheduling/accounting and the existing Qualcomm/Xiaomi touch boost
path, not a speculative replacement of the Goodix driver.

## Donor discrepancy found after User B test

The original Xiaomi donor package-runtime implementation does several things
differently from Candidate0059:

1. It exposes a pause_mode control and pkg_enable() returns !pause_mode.
2. update_task_runtime_info() updates each task's current history slot in the
   scheduler hot path, but user-level history snapshots are rolled separately.
3. User-level history roll is queued to system_long_wq.
4. package_runtime_monitor() only schedules that work when the 300-second window
   expires.

Candidate0059's bounded port currently:
- has no donor-equivalent pause_mode control;
- writes user_state history-slot fields during every update_pkg_load() call;
- advances history state directly instead of using the donor's long workqueue roll.

This is not yet proven to be the touch regression cause, but it is a concrete
semantic difference in a WALT hot path and is a stronger lead than modifying the
touchscreen driver blindly.

## Next isolation order

Do NOT modify Candidate0059 r43da7c5; keep it frozen as the User B evidence build.

Touch investigation order:
1. Capture Goodix IRQ rate, affinity, spurious count, InputReader/InputDispatcher,
   TouchFeature/HwBinder state, cpufreq policies and MIGT parameters on Candidate0059.
2. Capture the same data on the previous known control kernel under the same touch workload.
3. If Goodix IRQ delivery itself is abnormal, investigate driver/IRQ scheduling.
4. If IRQ delivery is normal but input latency is worse, isolate the Candidate0059
   package-runtime/WALT hot-path semantic differences first.
5. Only then isolate Stage9 FREQ_QOS interaction with Qualcomm touch boost.

Do not:
- disable thermal,
- globally pin CPU frequency,
- fake touch HAL success,
- weaken SELinux,
- modify Goodix firmware/driver without evidence.

## Integration consequence

Candidate0061 (5.4.302 uplift) may use Candidate0059 as an ABI/functionality
reference, but Candidate0062 must not automatically inherit Candidate0059's
performance implementation until a touch-latency gate passes.

Runtime status:
- jank/stutter subjective result: IMPROVED
- touch regression: FAIL
- Developer Options 0/0/1/1 property state on this test: PASS
- touch root cause: OPEN
