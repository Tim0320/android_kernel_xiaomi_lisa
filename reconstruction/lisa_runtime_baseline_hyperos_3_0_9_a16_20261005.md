# Lisa runtime system baseline

Updated: 2026-10-05

## Active device-system baseline

From this point forward, the default real-device validation environment is:

- Xiaomi lisa
- HyperOS 3.0.9
- Android 16
- user-supplied designation: "3.0.9 A16"

Unless a test explicitly requires a deep-flash / full base-system replacement,
all subsequent kernel, boot.img, touch, performance, BPF and 5.4.302 validation
must assume this system baseline.

Do not silently switch conclusions between older A14/A16 system images.

## Exception policy

A different system/base may be used only when:
- the user explicitly performs or requests a deep flash;
- a firmware/vendor partition mismatch requires a controlled base change;
- Android17/HyperOS4 boot validation intentionally switches to the A17 target.

When that happens, record the new system build/fingerprint before comparing
kernel behavior.

## Current comparison rule

Candidate0059 User B evidence collected before/around this transition remains
valid as Candidate0059 runtime evidence, but all new device captures should
record:
- ro.build.version.release
- ro.build.version.sdk
- ro.build.fingerprint
- ro.build.version.incremental
- ro.product.system.name
- ro.product.vendor.name
- kernel /proc/version

This prevents a system-version change from being mistaken for a kernel regression.

## Current development direction

The Candidate0059 touch regression and the Linux 5.4.289 -> 5.4.302 uplift may
be worked on in the same implementation stream because stable changes overlap
scheduler/cpufreq/fs/net/Qualcomm-sensitive code.

However they retain separate acceptance gates:
- STABLE_UPLIFT_GATE: official 5.4.289 -> 5.4.302 provenance and ABI integrity
- TOUCH_LATENCY_GATE: no regression versus the HyperOS 3.0.9 Android16 baseline
- PERFORMANCE_GATE: retain Candidate0059's observed jank/stutter improvement
- DEVICE_BASELINE_GATE: test actually ran on the declared system baseline

A change may only be accepted when its own gate passes; this avoids hiding a
touch workaround inside a stable-version uplift.
