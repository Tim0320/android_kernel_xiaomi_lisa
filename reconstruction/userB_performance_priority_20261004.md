# User B performance is now the first runtime-repair priority

User direction: prioritize user-B lag because newer Android uses the same lower-level architecture. Treat this as a shared-device compatibility problem to investigate, not a reason to dismiss the report as simply a newer ROM. This note changes investigation priority only; it does not change kernel bytes, replace APKs, or claim a jank fix has been tested. Keep current BPF58 work/checkpoints, but do not add more BPF/F2FS/302 features ahead of this investigation.

## Re-read private A/B evidence

A: lisa-live-20261004-150253.zip; B: lisa-live-20261004-150643-userB.zip (original filename has a Chinese user-B suffix). Existing sanitized exact identities/hashes are in c0058_two_device_review_20261004.md. Both booted fa96c94. A is Android14/system+vendor OS2.0.8; B is Android16/system OS3.0.304 with vendor OS2.0.16. Both report ro.product.board/device=lisa, ro.board.platform=lahaina and ro.hardware.egl=adreno. The tests differ in system/vendor, applications, radio and workload; not a controlled OS-only or SIM-only comparison.

Important decoding detail: getprop.txt in BOTH archives is UTF-16LE with BOM. Decode that correctly before comparing; searching raw UTF-8 text misses the actual properties. logcat has134894 lines on A and157087 on B. These are short, differently populated startup/user-activity captures, not equal-duration benchmark trials.

## New first-priority mismatch: enabled TurboSched features, unavailable Metis interface

B logcat lines6708-6727:

- 15:05:20.008: TurboSchedManagerService starts.
- 15:05:20.011: read /sys/module/metis/parameters/version failed.
- The same initialization enables local core-app optimization, TurboSched v2, top20, link/priority policy, wakeup feature and VIP balancing.

B lines49160-49168 (15:06:13.962 onward) show repeated perf/FPS errors interleaved with NativeTurboSchedManagerJni failing to open /dev/metis. The open failure appears1118 times, first15:06:13.962, last15:06:59.258 (about45.3s). A has zero such open-failure lines in its capture. No errno is printed: do not claim that every open failure is ENOENT rather than DAC/SELinux/device-registration trouble.

Actual captured property values:

| Property | A | B |
|---|---|---|
| persist.sys.turbosched.enable | false | false |
| persist.sys.turbosched.enable_v2 | false | true |
| persist.sys.turbosched.enable.coreApp.optimizer | false | true |
| persist.sys.turbosched.enabletop20app | false | true |
| persist.sys.turbosched.gaea.enable | false | true |
| persist.sys.turbosched.policy_list | empty | link,priority |

B also has local.enable_v2/coreApp/coreAppTop20 properties enabled. Therefore merely setting the already-false master 'enable' flag is not a meaningful repair. Framework/cloud initialization may override individual properties. Do not blindly set a collection of persistent properties, create a fake /dev/metis, or return success from unknown ioctls.

This is direct evidence of an unavailable requested performance interface and repeated calls. It is a stronger lead than Android-version labels, but it does not measure the fraction of jank caused by the retries. Both current inspected kernel sources (including the MiYume reference search) did not yield a complete applicable Xiaomi Metis implementation. A search miss does not prove none exists. Before adding one, establish actual library/ioctl versions, expected device/module owner and permissions, and the scheduler hook contracts. If the platform lacks the feature, use a capability-aware supported fallback rather than pretending boosts succeeded; test any fallback against frame timing and existing CPU/GPU protections.

Published reference evidence, not byte-identical B source:
- Xiaomi-derived init scripts expose /dev/metis and /sys/module/metis/parameters, e.g. Xiaomi-SM8475/android_device_xiaomi_liuqin@6a3b38f4c13878a73fe7e75c38028b360156a890 init/init.target.rc. Do not copy another device's permissions blindly.
- raghavt20/miui-services@d9e4df4bed682f316f555858588e2130611ad768 sources/com/miui/server/turbosched/TurboSchedManagerService.java reads persist.sys.turbosched.enable_v2, default true. This is a published reconstructed reference, NOT an independently matched B framework binary.

## Do not misdiagnose 'Unknown params' as a proven kernel frequency-write failure

B:3502 Unknown params, first15:06:13.962 last15:06:59.348.
B:2734 Content FPS Hint not delivered, same window, fps=90 handle=-1.
A:92 Unknown params over its own different window; no matching Content-FPS or Metis-open failures. Counts are not a controlled speed comparison.

Published Qualcomm-source mirror Sushrut1101/android_vendor_qcom_proprietary@39c82425849dc674f9e65a45fa3df3065f527652 android-perf/perf-hal/Perf.cpp shows this literal in the default branch parsing extra reserved-vector entries. In that implementation, code then continues to PerfGlueLayerSubmitRequest. Thus the message alone does not prove all CPU boosts were rejected or that a sysfs node is missing. It is an older reference, not a verified reconstruction of B's2.2 HAL. Trace client hint ID/payload, actual service/library hashes, vendor perf resource XML, return handle, and actual frequency/scheduling before changing kernel code. The FPS handle=-1 is an observed failed hint, but not a proof of a stuck governor.

## Cgroup/task-profile mapping is another concrete compatibility lead

B has8 'JoinCgroup: controller schedtune is not found' warnings. Example line69671 at15:06:18.802 follows iorapd's cpuset-policy request. A has0 matching warnings. Need actual /proc/cgroups, mounts and merged default/API-specific/vendor cgroups.json and task_profiles.json. Vendor profiles can override API defaults; replacing the whole scheduler or merely adding a directory is not a fix.

Verified0057 config already has CONFIG_SCHED_WALT, CONFIG_UCLAMP_TASK, CONFIG_UCLAMP_TASK_GROUP, CONFIG_CGROUP_SCHED, CONFIG_CPUSETS and CONFIG_CPU_FREQ_GOV_SCHEDUTIL enabled. Its configured default governor is performance, but post-boot code can select a different governor. Static config is NOT an actual current-frequency, thermal-cap or task-placement measurement. Do not infer B is pinned low or that a high frequency proves no scheduling problem.

Primary platform references:
https://source.android.com/docs/core/perf/cgroups
https://source.android.com/docs/core/tests/debug/jank_capacity
https://perfetto.dev/docs/data-sources/cpu-scheduling
https://perfetto.dev/docs/data-sources/cpu-freq

## Priority and next bounded verification

1. Confirm the Metis node/module/permissions and framework capability mismatch; obtain actual target library hashes and observe retry cost. Implement a correct interface adaptation or capability-aware fallback once the contract is known. Do not treat a fake-success stub or suppressing logs as repair.
2. Resolve perf-hint client/service/resource configuration and top-app task profiles against actual kernel interfaces. Fix the demonstrated layer, including kernel exposure when absent, rather than broadly blaming system or replacing the kernel tree.
3. Measure frame deadlines, runnable time vs CPU frequency, binder waits, GPU frequency/busy and thermal limits on the same workload. Confirm whether remaining stutter is CPU placement, frequency response, graphics/fence or service work. Use repeated same-device comparisons, not just fewer warning lines.
4. Retain the definite com.android.phone hasRemote() NoSuchMethodError and PowerInsight exception as separate findings. They cannot be repaired by renaming a kernel or adding BPF, but they do not absolve the kernel/interface investigation.

A30-second non-root collection bundle was prepared: Lisa_UserB_Perf_Diagnostic.zip SHA256 e1f40b624caaddf15515cb150eae431c05e3a2f02de0675e307f4161b77ffa85. It samples relevant interfaces/configs/frequencies and records a bounded Perfetto trace plus filtered performance logs. It never calls su/setprop, writes sysfs, changes permissions, reboots, replaces modules/APKs or changes thermal/radio settings. Permission failures and missing trace sources are retained as evidence gaps. POSIX-shell syntax and bounded static safety checks passed locally; PowerShell/Android execution has NOT been performed. A trace can perturb timing, so use the same recorder for comparisons. The bundle is saved in the user's Library, not published with private logs. No raw private logs/screenshots/identifiers are added to this repository.

## Existing0058 work is saved, not discarded for this priority change

Run37187168089/e476b67 build111391476651 completed successfully and saved UNVERIFIED boot11298495147 plus reusable checkpoint11298057963. Verify111395702823 passed inherited static ABI/ownership/identity/BPF-linked gates, then failed the diskless generic ARM64 guest step. Evidence11298132951 (ZIP SHA256 eff2ec037062fa6c23b853f2e29f1f1f20327968bf110af7665d86ddf92acd70) records INCONCLUSIVE_BOOT, exit0, no probe begin marker and an empty QEMU console. This is NOT a BPF execution pass or proof of a BPF regression. No verified58 artifact was published.

Keep those bytes/checkpoint. A guest/test-environment fix should reverify the original build without make or repackaging. Do not start another30-minute kernel build or add more BPF features just to distract from user-B jank. Do not remove the runtime test gate to claim58 verified. The working57 Wi-Fi/battery baseline remains available. The existing hourly task should prioritize this document, keep the checkpoint rules, and retain the2/2/5-minute Action observer when a run is active. A new runtime kernel change requires an actual new build and all existing safety/ABI tests; this note does not constitute that change.
