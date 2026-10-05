# Lisa 5.4.302 + Touch/Jank stabilization execution plan

Plan version: 1.0
Updated: 2026-10-05
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

### Phase 3 - Stable uplift Batch A
Status: DONE

Target:
- 5.4.289 -> 5.4.292

Method:
1. Apply official stable semantics only.
2. Resolve vendor conflicts semantically.
3. Compare Qualcomm-sensitive files with MiYume only when necessary.
4. olddefconfig.
5. compile Image/modules.
6. modpost.
7. Module.symvers/CRC gates.
8. ABI review policy: Candidate0059 exports must not disappear. CRC changes/additions are allowed only when their exact symbols are reviewed and traced to official Stable Batch A source changes; do not revert legitimate stable changes merely to force CRC identity.
9. Current reviewed Batch A stable ABI deltas: xhci_dbg_trace, xhci_ext_cap_init, xhci_gen_setup, xhci_resume, xhci_suspend; additions flow_rule_match_ports_range, page_get_link_raw, tasklet_setup.
10. CI evidence/oracle policy: do not depend on short-lived cross-workflow artifact download URLs as the only source of Candidate0059 config/Module.symvers or exact stock IKHEADERS. Preserve a durable oracle or regenerate stock IKHEADERS from the pinned stock boot, and validate hashes before build.
11. If using the reviewed Batch A control run 37306854501, its exact control files are .config SHA256 664d12d837af3e3b26d2f04da0f11cefd8ba2b53e0fa01f3e7e274921f589397 and Module.symvers SHA256 846e9ceec05d4da4a0bf9c3ca4b7677bd1955091ccd0d7c46d4848bb7c14b7ff. Relative to that control, the repaired build must add only lisa_mtdoops_checkpoint=0x002a7d5d and qcom_scm_get_download_mode=0xd9dc8135 with zero changed/removed symbols.
12. Keep stable source application side-effect-free. Candidate0059 config-oracle reconstruction is a separate MIXED_CONFLICT build-gate adaptation and must not be hidden inside the STABLE_ONLY 5.4.289->5.4.292 semantic apply script.
13. The reviewed Candidate0059 control config delta currently consists of the C0059 LOCALVERSION, LOCALVERSION_AUTO=n, COMPAT_VDSO=n, ARM64_USE_LSE_ATOMICS=n, RELR=n, PERF_HELPER=y, and MILLET_CGROUP/SIG/BINDER/PKG/BINDER_GKI/CORE/HS=y; the exact post-olddefconfig SHA256 remains the acceptance oracle.

No touch/performance modifications unless a conflict requires them.

Exit:
- Batch A compile/static/ABI PASS;
- removed Candidate0059 symbols = 0;
- any changed/added ABI symbol is explicitly stable-provenance reviewed.

### Phase 4 - Stable uplift Batch B
Status: BUILD GATE RUNNING

Target:
- 5.4.292 -> 5.4.296

Same gates as Phase 3.

Special attention:
- pinctrl/QCOM/UFS-reset relevant changes.

### Phase 5 - Stable uplift Batch C
Status: NOT STARTED

Target:
- 5.4.296 -> 5.4.299

Special attention:
- qcom mdt_loader;
- dwc3/qcom;
- boot/firmware sequencing.

### Phase 6 - Stable uplift Batch D
Status: NOT STARTED

Target:
- 5.4.299 -> 5.4.302

Special attention:
- qcom mdt_loader follow-up;
- bam_dma;
- q6v5;
- rpmh-rsc;
- qcom smem.

Exit:
- source reports 5.4.302;
- compile/static/ABI gates PASS.

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
Inspect the Candidate0061 Batch B run triggered by commit 83dbe9c or later.

Batch A is now fully closed by run 37331513181:
- stock ABI PASS;
- Candidate0059 inherited source recreation PASS;
- Stable Batch A semantic apply PASS;
- reviewed config PASS;
- same-run control compile/modpost PASS;
- Candidate0059 ABI compatibility PASS;
- target compile/modpost PASS;
- exact ABI gate PASS;
- changed CRCs = 0;
- removed symbols = 0;
- added symbols = exactly lisa_mtdoops_checkpoint=0x002a7d5d and qcom_scm_get_download_mode=0xd9dc8135.

Batch B is 5.4.292 -> 5.4.296 and remains STABLE_ONLY. The first run is
deliberately strict: any downstream overlap that cannot three-way merge must stop
at the first path for semantic classification, and any non-zero changed/added ABI
delta must be reviewed against official Stable Batch B provenance before it can be
accepted. Removed Candidate0059 symbols are not allowed.

If Batch B apply/build/ABI all pass, mark Batch B PASS and immediately start
Batch C 5.4.296 -> 5.4.299. If it fails, repair only the first real blocker.
Do not introduce package-runtime/WALT, MIGT FREQ_QOS, touch boost, Goodix or other
touch/performance changes until the complete 5.4.302 Stable base is established.
