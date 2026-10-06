# Lisa 5.4.302 + Touch/Jank stabilization execution plan

Plan version: 1.1
Updated: 2026-10-06
Active device baseline: HyperOS 3.0.9 / Android 16
Canonical runtime reference: Candidate0059 r43da7c5

## Purpose

This file is the canonical continuation plan for the Lisa kernel project while:
1. uplifting the reconstructed kernel from Linux 5.4.289 to 5.4.302;
2. fixing the Candidate0059 touch regression;
3. retaining Candidate0059's observed jank/stutter improvement;
4. preparing the later Android17/HyperOS4 BPF compatibility overlay.

Every future execution must read this file and the machine-readable state file first.
Do not rely on chat memory alone.

Machine state:
- reconstruction/lisa_5_4_302_touch_plan_state.json

Related evidence:
- reconstruction/c0059_userb_touch_regression_20261005.md
- reconstruction/lisa_runtime_baseline_hyperos_3_0_9_a16_20261005.md
- reconstruction/c0061_linux_5_4_302_uplift_plan_20261005.md
- reconstruction/tools/collect_lisa_touch_runtime.ps1

## Current observed state

Candidate0059:
- kernel: 5.4.289-qgki-lisa-c0059-r43da7c5-by-Tim0320
- static/ABI/identity/packaging: PASS
- User B jank/stutter subjective result: IMPROVED
- User B touch result: REGRESSED
- Developer Options property tuple on User B: 0/0/1/1, PASS
- direct Goodix firmware/I2C/SPI failure in supplied log: NOT OBSERVED
- touch root cause: OPEN

5.4.302 uplift audit:
- official stable changed files: 1760
- stable/Lisa vendor-overlap files: 271
- sensitive overlap files: 140
- overlap files also modified by MiYume: 237
- Candidate0060 planned core surface: 27 files
- Candidate0060 files changed by 289->302 stable: 2
- Candidate0060 files modified by MiYume vs official 302: 27
- three-way Candidate0060 files: net/core/filter.c, fs/file.c

## Public-source research verdict

### Result: the current method is technically justified, but not yet proven on Lisa

The planned approach is:
- reduce unnecessary scheduler/WALT hot-path work;
- restore donor-equivalent deferred accounting behavior;
- preserve input/touch boost responsiveness;
- use objective input-latency tracing rather than judging only frame smoothness;
- uplift to 5.4.302 first where stable code overlaps.

This has strong public technical support:

1. Android Perfetto distinguishes smooth rendering from low input latency.
   FrameTimeline explicitly documents a high-latency state where frames appear smooth but are presented late, increasing input latency.
   This matches User B's observation that jank improved while touch became worse.
   Reference:
   - https://perfetto.dev/docs/data-sources/frametimeline

2. Perfetto exposes android_input_events with:
   - dispatch_latency_dur
   - handling_latency_dur
   - ack_latency_dur
   - total_latency_dur
   - end_to_end_latency_dur
   This provides an objective A/B touch gate instead of subjective feel only.
   Reference:
   - https://perfetto.dev/docs/analysis/stdlib-docs

3. Qualcomm's public cpu-boost implementation treats touchscreen input as latency-sensitive.
   Input events queue a CPU-boost work item, enforce a MIN_INPUT_INTERVAL, update cpufreq policy and later remove the boost through delayed work.
   Therefore changes in scheduler/cpufreq/FREQ_QOS timing can plausibly affect touch responsiveness.
   References:
   - https://android.googlesource.com/kernel/msm.git/+/0f324698e476a247eed127f0745a4ef2805bf54a/drivers/cpufreq/cpu-boost.c
   - https://android.googlesource.com/kernel/msm/+/2137a397e1465913f0aa63f75f00319e29d1ad9e/drivers/cpufreq/cpu-boost.c

4. Linux cpufreq documentation explicitly keeps rate limiting because governor updates from scheduler context can create excessive scheduler overhead.
   Linux utilization-clamp documentation also notes that frequency changes can take milliseconds and worker scheduling/rate limiting can prevent short critical tasks from getting performance at the needed time scale.
   This supports treating frequent/new FREQ_QOS activity as a possible latency interaction, but does not prove Stage9 is the root cause.
   References:
   - https://kernel.org/doc/html/next/admin-guide/pm/cpufreq.html
   - https://kernel.org/doc/html/latest/scheduler/sched-util-clamp.html

5. Linux latency tracers provide the correct tool for proving kernel-side latency:
   - irqsoff
   - preemptoff
   - preemptirqsoff
   - wakeup
   These can identify periods where IRQ delivery or task scheduling is blocked.
   Reference:
   - https://www.kernel.org/doc/html/v4.20/trace/ftrace.html

6. Xiaomi donor evidence already shows package-runtime work is designed with:
   - pause_mode
   - deferred history roll
   - system_long_wq
   Candidate0059's bounded port differs by writing additional user history state in the WALT hot path.
   This is a concrete semantic difference worth fixing first.

Conclusion:
- YES: reducing hot-path accounting and restoring deferred behavior is a valid first intervention.
- YES: preserving/validating touch boost and cpufreq timing is important.
- NO: public evidence does not prove either change alone will fix Lisa; A/B measurements remain mandatory.

## Core rule: do not optimize for FPS alone

Acceptance requires BOTH:
- frame/jank improvement;
- input/touch latency no worse than control.

A build that is smoother but has worse touch latency FAILS the runtime gate.

## Execution phases

### Phase 0 - Baseline freeze and provenance
Status: DONE

- Freeze Candidate0059 r43da7c5 as the behavioral reference.
- Keep User B logs and touch-regression report.
- Set HyperOS 3.0.9 / Android16 as active system baseline.
- Do not rewrite Candidate0059.

Exit:
- reference kernel identity recorded;
- runtime baseline recorded.

### Phase 1 - 5.4.302 conflict inventory
Status: DONE

- Diff official v5.4.289 -> v5.4.302.
- Identify Lisa vendor-overlap set.
- Use MiYume only as final-state Qualcomm/Xiaomi 5.4.302 reference.
- Record high-risk Qualcomm stable changes.

Exit:
- stable provenance known;
- conflict-risk set known;
- MiYume role constrained.

### Phase 2 - HyperOS 3.0.9 A16 touch control capture
Status: NEXT DEVICE DATA

Use:
- reconstruction/tools/collect_lisa_touch_runtime.ps1

Capture on HyperOS 3.0.9 A16 with Candidate0059 or the closest known-good control:
- /proc/interrupts before/after touch workload;
- Goodix irq affinity/spurious;
- cpufreq policy state;
- MIGT parameters;
- InputReader/InputDispatcher;
- TouchFeature/HwBinder;
- logcat;
- dmesg if available.

Preferred additional measurement:
- Perfetto input trace with android_input_events;
- FrameTimeline;
- sched/cpufreq/frequency events.

Metrics:
- p50/p95/p99 dispatch latency;
- p50/p95/p99 total input latency;
- end-to-end input-to-frame latency where available;
- Goodix IRQ rate;
- irq/305 CPU time;
- frame jank count/rate;
- high-latency smooth-frame count.

Exit:
- measurable control values recorded.

### Phase 3 - Historical stable provenance checkpoint: Batch A
Status: DONE / REFERENCE ONLY

Historical target:
- 5.4.289 -> 5.4.292

Evidence retained:
- clean build/ABI gate PASS at run 37331513181;
- Candidate0059 build/KMI reconstruction path is proven;
- reviewed Batch A semantic adapters remain reusable provenance evidence.

Important:
- Phase 3 is no longer a required intermediate build gate for future Candidate0061 work.
- It remains a trusted reference for reconstruction, ABI policy, and provenance classification.

### Phase 4 - Direct Candidate0061 Linux 5.4.302 uplift
Status: DONE

Target:
- Candidate0059/Lisa 5.4.289 -> Linux 5.4.302 in one integrated source/build gate.

This supersedes the old requirement to compile separately at 5.4.296, 5.4.299 and 5.4.302.

#### Direct-302 execution model

1. Recreate the frozen Candidate0059 source/build contract from r43da7c5 without modifying Candidate0059.
2. Fetch official linux-stable v5.4.289 and v5.4.302 and construct the complete stable delta.
3. Keep A/B/C/D only as provenance labels:
   - A: 5.4.289 -> 5.4.292
   - B: 5.4.292 -> 5.4.296
   - C: 5.4.296 -> 5.4.299
   - D: 5.4.299 -> 5.4.302
   A/B/C/D identify where a stable hunk originated; they are not separate compile gates.
4. Auto-apply clean stable hunks across the complete 5.4.289 -> 5.4.302 range.
5. Pre-scan every non-clean overlap before the build and classify it as:
   - STABLE_ONLY
   - MIXED_CONFLICT
   - NOT_APPLICABLE
6. Resolve common Linux/Android/Qualcomm/Xiaomi semantics toward the 5.4.302 endpoint:
   - official linux-stable remains canonical patch provenance;
   - MiYume SM8350/Xiaomi 5.4.302 is the first downstream final-state oracle;
   - AOSP android11-5.4.302_r00 is the Android/GKI endpoint oracle;
   - CLO/CodeLinaro msm-5.4 is fallback only when MiYume/stable/AOSP do not resolve the Qualcomm lineage.
7. Do not wholesale-copy MiYume files. Explicitly exclude or adapt:
   - SM8350 / Lahaina / venus-only clock, interconnect, OPP, regulator, pinctrl, DTS and platform IDs;
   - MiYume custom ReSukiSU/SuSFS, BPF 5.10 backports, F2FS tuning and Android17-only additions unless separately required later.
8. Preserve Lisa-specific:
   - SM7325 / Yupik platform semantics;
   - Candidate0059 device/KMI build contract;
   - Lisa vendor functionality that does not conflict with official stable semantics.
9. Set final source identity directly to 5.4.302 and run only the integrated target gate:
   - olddefconfig;
   - Image/modules/dtbs;
   - modpost;
   - static compatibility checks;
   - Module.symvers / ABI / KMI review;
   - identity and packaging preparation.
10. Acceptance for the direct uplift:
   - source reports 5.4.302;
   - compile/modpost PASS;
   - Candidate0059 exported symbols removed = 0;
   - every changed/added ABI symbol is explicitly traced to stable provenance or a separately reviewed MIXED_CONFLICT;
   - no touch/performance intervention is mixed into this stable gate unless required to preserve semantics.

#### Provenance progress retained from the retired per-Batch build loop

- Segment A 5.4.289 -> 5.4.292: provenance reviewed, historical build/ABI PASS.
- Segment B 5.4.292 -> 5.4.296: partial semantic review already completed:
  - top-level Makefile SUBLEVEL adaptation;
  - Cortex-A76AE CPU-ID adaptation;
  - HID identity additions;
  - QCOM pinctrl IRQ valid-mask adaptation.
- Segment C 5.4.296 -> 5.4.299: provenance reviewed inside Direct-302; no separate build.
- Segment D 5.4.299 -> 5.4.302: provenance reviewed inside Direct-302; no separate build.

The in-flight legacy Batch B run may be retained only as evidence that already-reviewed Segment B adapters are valid. It must not cause the project to continue the retired 296 -> 299 -> 302 build loop.

### Phase 5 - Direct-302 semantic conflict closure
Status: DONE

Purpose:
- close the full non-clean 5.4.289 -> 5.4.302 conflict set before the integrated build;
- resolve conflicts in final-state order rather than discovering one conflict per intermediate build.

Priority review surfaces:
- qcom mdt_loader;
- dwc3/qcom and gadget/core changes;
- UFS/reset paths;
- bam_dma;
- q6v5;
- rpmh-rsc;
- qcom smem;
- pinctrl/QCOM paths;
- any Android/GKI ABI-sensitive headers.

Exit:
- all direct-302 non-clean overlaps classified and adapted;
- no unreviewed semantic conflict remains;
- Direct-302 materialization passed with 1760 paths, no `.rej`, `git diff --check` PASS and source identity 5.4.302;
- integrated compile exposed one textually-clean but semantically incompatible runtime-PM path; `drivers/base/power/runtime.c` is now the 34th reviewed path, classified MIXED_CONFLICT for Segments B+C: keep the Segment-B timer-expiry `<=` stable fix, but reject the Segment-C `needs_force_resume` reinit write because frozen Lisa intentionally retains `pm_runtime_need_not_resume()` and no `dev_pm_info.needs_force_resume` field.

### Phase 6 - Direct-302 integrated static/ABI gate
Status: ACTIVE

Run one target build after Phase 5 conflict closure.

Exit:
- kernel source identity = 5.4.302;
- Image/modules/dtbs + modpost PASS;
- Candidate0059 removed ABI symbols = 0;
- changed/added ABI symbols provenance-reviewed;
- static/identity/packaging automation ready;
- then proceed to Phase 7 touch/jank correction.

### Phase 7 - Touch/jank hot-path correction on 5.4.302
Status: NOT STARTED

Do this on top of the established 5.4.302 semantic base.

Intervention order:

A. Package-runtime/WALT semantics
- restore donor-equivalent pause/enable behavior if safe;
- stop copying user history slots in every WALT accounting update;
- move history rolling to deferred work equivalent to donor system_long_wq behavior;
- keep task accounting required by MIGT;
- do not introduce a large global lock in WALT hot path.

B. Rebuild and static gate.

C. Device A/B on HyperOS 3.0.9 A16.

Decision:
- if touch improves while jank benefit remains -> KEEP.
- if no change -> revert/adjust only this intervention and proceed to FREQ_QOS isolation.
- if jank regresses materially -> reconsider accounting reduction granularity.

### Phase 8 - FREQ_QOS / Qualcomm touch-boost isolation
Status: CONDITIONAL

Only run if Phase 7 does not resolve touch regression.

Check:
- current MIGT boost_policy state;
- FREQ_QOS request lifetime;
- interaction with existing Qualcomm input/touch boost;
- cpufreq policy update frequency;
- repeated boost suppression/rate-limit behavior.

Do NOT:
- globally pin CPU frequency;
- disable thermal;
- force max frequency;
- remove input boost blindly.

Possible safe changes:
- avoid redundant freq_qos_update_request calls when value is unchanged;
- avoid refresh across policies when no boost/ceiling state changed;
- make request lifetime/event frequency match donor semantics more closely;
- preserve Qualcomm touch boost priority.

Exit:
- measurable input latency improves;
- jank improvement remains.

### Phase 9 - Kernel latency tracing if still unresolved
Status: CONDITIONAL

Use supported tracing on the device:
- irqsoff
- preemptoff
- preemptirqsoff
- wakeup
- sched_switch/sched_wakeup
- irq_handler_entry/exit
- cpu_frequency

Correlate:
- Goodix IRQ timestamp
-> IRQ thread wake
-> InputReader
-> InputDispatcher
-> app receive/ACK
-> SurfaceFlinger frame present

Goal:
identify whether latency is:
- IRQ delivery;
- irq thread scheduling;
- system_server/InputDispatcher;
- cpufreq response;
- render/present.

### Phase 10 - Candidate0061 integrated A16 validation
Status: NOT STARTED

Candidate0061 can progress only if all are PASS:
- Linux 5.4.302 stable provenance;
- compile/modpost;
- ABI/CRC;
- identity/packaging;
- boot;
- Wi-Fi;
- battery/charging;
- UFS;
- touch latency;
- jank/performance retention;
- SELinux enforcing;
- HyperOS 3.0.9 A16 baseline identity.

Label before device PASS:
"5.4.302 static/ABI verified; device validation pending".

### Phase 11 - Candidate0060 overlay / Candidate0062
Status: BLOCKED ON C0061

After Candidate0061 passes:
- apply Android17/BPF compatibility overlay;
- build Candidate0062;
- later switch to HyperOS4/A17 baseline intentionally.

## Touch/performance acceptance thresholds

Until enough samples exist, do not invent hard absolute millisecond limits.

Use relative A/B gates:
- p95/p99 input latency must not regress versus known-good control;
- Goodix IRQ rate must not show unexplained multiplication;
- InputDispatcher latency must not materially regress;
- jank rate must retain Candidate0059 improvement;
- no sustained CPU-frequency pinning is allowed.

After two comparable captures, freeze numeric thresholds into this plan.

## Failure classification

When a test fails, assign exactly one primary class:

- TOUCH_IRQ
- TOUCH_HAL
- INPUT_DISPATCH
- SCHED_WALT
- CPUFREQ_QOS
- FRAME_PIPELINE
- STABLE_UPLIFT
- ABI_MODULE
- PACKAGING
- UNKNOWN

Do not make unrelated fixes in the same commit.

## Commit classification

Every implementation commit must include one tag in its evidence note:

- STABLE_ONLY
- TOUCH_PERF_ONLY
- MIXED_CONFLICT

For MIXED_CONFLICT:
1. record official stable hunk/provenance;
2. record touch/performance adaptation;
3. verify both gates independently.

## Persistent progress protocol

At the beginning of every future execution:
1. read this plan;
2. read reconstruction/lisa_5_4_302_touch_plan_state.json;
3. read latest GitHub commit;
4. read latest Action run/job/log;
5. execute state.next_action;
6. update state and this plan if a decision changes.

At the end of every execution:
- set last_checked_commit;
- set last_checked_run;
- set current_phase;
- set completed_steps;
- set blocker;
- set next_action;
- set next_expected_evidence;
- commit the state change.

## Current next action

NEXT_ACTION:
Migrate Candidate0061 from the retired per-Batch build loop to a Direct-302 workflow.

1. Do not create Batch C or Batch D build workflows.
2. Treat run 37360064366 and earlier Batch B runs only as semantic/provenance evidence.
3. Build a new direct 5.4.289 -> 5.4.302 scanner/apply workflow that:
   - reconstructs frozen Candidate0059;
   - fetches linux-stable v5.4.289 and v5.4.302;
   - pins MiYume 5.4.302 final-state oracle;
   - uses AOSP android11-5.4.302_r00 for GKI/Android endpoint semantics;
   - uses CLO only as fallback;
   - scans the complete non-clean overlap set before target build;
   - reuses already-reviewed Segment A/B adapters where still valid;
   - labels each applied change with provenance segment A/B/C/D without compiling at each segment.
4. Resolve all remaining non-clean overlaps toward the 5.4.302 final state while preserving Lisa SM7325/Yupik-specific semantics.
5. Run one integrated 5.4.302 compile/modpost/ABI gate.
6. Only after the direct 5.4.302 static/ABI gate passes, begin the package-runtime/WALT touch/jank correction.

Strategic rule:
"MiYume 5.4.302 alignment is primary for common Xiaomi/Qualcomm final-state semantics; Lisa SM7325/Yupik difference exclusion is secondary. Linux-stable remains canonical provenance."
