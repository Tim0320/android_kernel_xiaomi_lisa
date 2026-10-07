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
- reconstruction/c0061_phase10_device_validation_20261007.md

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
Status: REOPENED - C0059 SOURCE RECONSTRUCTION CONTRACT REPAIR

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
Status: STATIC PASS BUT RUNTIME INVALIDATED - ONE-SCREEN REBOOT

Run one target build after Phase 5 conflict closure.

Exit:
- kernel source identity = 5.4.302;
- Image/modules/dtbs + modpost PASS;
- Candidate0059 removed ABI symbols = 0;
- changed/added ABI symbols provenance-reviewed;
- static/identity/packaging automation ready;
- then proceed to Phase 7 touch/jank correction.

2026-10-07 ordering audit:
- run 37571737761 completed successfully and proved the repaired C0059 IPA/PAS reconstruction, 34/34 semantic closure, compile/modpost, removed ABI symbols = 0, exact 5.4.302 identity and boot static packaging;
- however its workflow applied `candidate_0061_touch_jank_hotpath.py` before the Phase 6 target config/build, so this run mixes the Phase 7 TOUCH_PERF_ONLY intervention into the base Direct-302 gate;
- therefore run 37571737761 is useful evidence but is NOT accepted as the canonical Phase 6 stable-only gate under the current strategy;
- the integrated workflow must first be rerun without the Phase 7 hot-path step. Only after that pure Direct-302 static/ABI/identity/packaging gate passes may Phase 7 be entered.

### Phase 7 - Touch/jank hot-path correction on 5.4.302
Status: DONE - STATIC/ABI/IDENTITY/PACKAGING PASS; DEVICE EFFECT PENDING

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
Status: BLOCKED ON PURE PHASE6 BASE + ORDERED PHASE7 REBUILD

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

## 2026-10-07 Candidate0059 reconstruction correction

Runtime evidence from the first Candidate0061 device test invalidated the previous Phase10 entry:
- artifact 11437434497 / boot SHA256 65e94493f1b41cc889074b3ccc9c19bfea6977c50b0a56754c535aeb9889f8d4 showed one-screen boot then reset before System;
- re-audit of integrated run 37513703360 confirmed the reconstruction step printed C0059_INHERITED_SOURCE_STACK_RECREATED=PASS but did not contain LISA0046_IPA, LISA0053_IPA, yupik_ipa_fws, ipa_before_pas_auth_reset, or ipa_after_pas_auth_reset markers;
- frozen source 6e568aabc77a06fa787baec1d9e60e4b559874a3 predates the Candidate0046/Candidate0053 recipe-time IPA/PAS runtime contract, while the actual Candidate0059 lineage inherits it through 0054 -> 0053 -> 0046.

Decision:
- retire artifact 11437434497 as a Phase10 candidate;
- keep Candidate0059 r43da7c5 frozen;
- keep the DIRECT 5.4.289 -> 5.4.302 strategy;
- do not restore Batch C/D builds;
- replay only the pinned Candidate0046 prerequisites plus Candidate0053 IPA full-region and PAS15 metadata-retention endpoints inside the C0061 Candidate0059 reconstruction path;
- require C0061_C0059_IPA_PAS_INHERITANCE=PASS before the integrated compile/static/ABI/identity/packaging gate can be accepted again.

Repair history:
- 9dd3fba887d0b543c21d54f898e2ef423b06bca4 — initial bounded C0046 -> C0053 replay; integrated run 37571219318 proved the first real blocker was importing candidate_0053_build.py, whose module tail auto-starts the historical C0053 build and aborts because Candidate0018 IKCONFIG is not present in the C0061 workspace.
- 74597be686dd43270002e938f8f9c953f0539f88 / 90894032203d2b0440be09c3eeab060f78a733e4 / 8807914fcbdfb1bc22c5a8b84345a9d30e594ea1 — superseded workflow-edit attempts; invalid before runner allocation because a JavaScript replacement-token expansion corrupted the YAML payload. These are workflow/tooling failures, not kernel evidence.
- e10d16cb04dc01f38cd4c6688ad54e180effa238 — current repair: pin Candidate0053 blob d3111485e075156687c5eee50546ba42417dd2fa, AST-extract only patch_ipa_pas_metadata_dma_retention() and candidate0053_patch_ipa_pas_shmbridge(), avoid all C0053 module-tail side effects, and restore the last known-valid integrated workflow blob.
- 803b05f1932d3109f7ec1f4f301c20f911de167d — repaired IPA/PAS reconstruction completed end-to-end in run 37571737761, with inheritance PASS, Direct-302 34/34/0, compile/modpost, ABI removed=0, identity and packaging PASS. Its target build also contained the Phase7 TOUCH_PERF_ONLY overlay, so it is evidence but not the canonical Phase6 base gate.
- a8fb21ad55f98453c88d1e43de46514f7073f513 — removed Phase7 script trigger/application/reporting from the integrated Phase6 workflow. Run 37576020824 is the canonical pure Direct-302 Phase6 revalidation.

Current CI:
- integrated run 37571503370 / job 112630951523: in progress from e10d16c;
- Direct-302 provenance scan 37571503382 / job 112630951238: in progress from e10d16c and remains provenance-only, not an intermediate compile/build gate.

Classification:
- primary failure class: STABLE_UPLIFT;
- implementation provenance: reviewed MIXED_CONFLICT preserving Lisa/Yupik Candidate0059 runtime semantics across the Direct-302 reconstruction.

## 2026-10-07 Pure Phase6 canonical acceptance

Canonical pure Direct-302 Phase6 is now accepted:
- run 37576020824 / job 112644987705 completed SUCCESS from commit a8fb21ad55f98453c88d1e43de46514f7073f513;
- Candidate0059 reconstruction PASS;
- Direct-302 semantic closure = 34 reviewed / 0 unresolved;
- integrated 5.4.302 Image/modules/dtbs/modpost PASS;
- ABI/KMI gate PASS with Candidate0059 removed symbols = 0;
- exact kernel release = 5.4.302-qgki-lisa-c0061-ra8fb21a-by-Tim0320;
- boot static packaging PASS;
- boot SHA256 = 70082a01ec0fd3cf1ebf4cfbf9b539626045ce17cb5d94a1349f78b9a135e984;
- canonical pure Phase6 boot artifact = 11463937382;
- integrated evidence artifact = 11464311817;
- Direct-302 scan artifact = 11464371802.

Phase6 is therefore closed. The earlier mixed-order run 37571737761 remains evidence only and is not the canonical Phase6 artifact.

## 2026-10-07 Ordered Phase7 launch

A separate Phase7 workflow was added in commit 9a0495f72e43389f8495ccec72532aa3845a907d:
- workflow: .github/workflows/build-lisa-candidate-0061-phase7-touch-jank.yml;
- run: 37582021048;
- accepted baseline is pinned to pure Phase6 run 37576020824;
- Phase7 applies candidate_0061_touch_jank_hotpath.py only after Direct-302 materialization and post-materialization C0059 KMI restoration;
- Phase7 target release is distinct: c0061p7;
- Phase7 must remain KMI-neutral relative to the accepted pure Phase6 Module.symvers;
- this remains TOUCH_PERF_ONLY. FREQ_QOS/input boost isolation stays conditional and is not mixed into this run.

## 2026-10-07 Pure Phase6 device failure and runtime-equivalence reopen

Device result for canonical pure Phase6 artifact 11463937382 / boot SHA256 70082a01ec0fd3cf1ebf4cfbf9b539626045ce17cb5d94a1349f78b9a135e984:
- one screen appears;
- device immediately crashes/reboots;
- System is not reached.

Therefore run 37576020824 remains a valid static/ABI/identity/packaging proof but is no longer a runtime-valid Phase6 baseline.

Re-audit against the actual verified Candidate0059 r43da7c5 build (run 37254944397) found a concrete reconstruction gap:
- real Candidate0059 verification includes LISA_CANDIDATE_0059_RAW_LATCH_COMPILED_GATE=PASS;
- candidate_0061_recreate_c0059_uplift.py explicitly short-circuits the retained Candidate0057 -> Candidate0056 -> Candidate0055 -> Candidate0054 chain to avoid double-applying UFS/power;
- that shortcut also omitted Candidate0054 raw first-fault latch/persistent module-map layer from C0061;
- this layer is diagnostic-first and is not claimed to be the crash fix, but it is part of the real Candidate0059 source contract and is required to persist PC/LR/register evidence for the current one-screen reboot.

Repair decision:
- keep frozen Candidate0059 r43da7c5 unchanged;
- keep DIRECT 5.4.289 -> 5.4.302 strategy;
- restore only the pinned Candidate0054 raw first-fault latch into the bounded C0059 reconstruction;
- add a post-Direct-302 runtime-contract gate covering raw latch, IPA/PAS, proc_create ABI, UFS, power, camera ownership and package-runtime/MIGT presence;
- current ordered Phase7 run 37582021048 may finish as static evidence but must not become a device-test candidate based on the failed Phase6 runtime baseline;
- do not enter device Phase7 validation until a rebuilt Phase6 artifact passes static gates and provides the restored persistent crash evidence path.

Classification: MIXED_CONFLICT (preserve verified Candidate0059 runtime-equivalence while carrying Direct-302 stable changes).

## 2026-10-07 TWRP deep capture: failure moved to EBS / packaging layer

Latest user capture:
- file: lisa-twrp-deep-20261007-152530.zip;
- capture time: 2026-10-07 15:25:30 +08:00.

Persistent crash-state comparison against the morning boot_65e94493f1b4 capture:
- oops / sda17 block2mtd SHA256 = 402b53f3583612c3cdd0a08a764535426645cff5ac2a8d24bff16d567b511351 in both captures;
- minidump SHA256 = 40bdc781b7e2a2ff8c52e50f9ad713168012b796d60adc8650b32eab2f48ea6d in both captures;
- rawdump SHA256 = 605b2027582ca8c4b3c4d1e04d09ecc7b612dc9fe4ca97208c57bc2e3355710c in both captures;
- no r60f98e6 / 5.4.302 Candidate0061 Linux banner exists in those persistent partitions;
- only logfs changed. Its newest mission-mode record reaches Load Image boot_a / vendor_boot_a, orange-state authentication, DT overlay, Shutting Down UEFI Boot Services, and Start EBS. A following boot records PSHOLD / Hard Reset.

Therefore the failed r60f98e6 boot did not reach the existing Candidate0054 raw-fault / mtdoops / IPA checkpoints. Driver/PAS mutation is not justified from this capture.

Binary boot A/B exposed a concrete packaging regression:
- verified working Candidate0059 boot 21764b30... keeps stock boot header kernel_size=51,436,032 and ramdisk offset=51,441,664;
- Candidate0059 copies the real Image into that fixed region, zero-pads the unused kernel-region bytes, and leaves every byte after the kernel region unchanged;
- Candidate0059 retains AVB0 at fixed logical_end 0x4406000, a 896-byte embedded vbmeta payload, and AVBf at the partition footer; tail nonzero bytes=367;
- failed C0061 r60f98e6 boot abc3568d... changed header kernel_size to the actual 49,283,584-byte Image, moved ramdisk to 49,291,264, and zeroed the entire tail, explicitly requiring stale_avb_footer_absent=1;
- this contradicts the canonical Candidate0059/fixed-region/AVB preservation contract and is now the first packaging blocker.

Decision:
- do not change kernel drivers from this TWRP capture;
- reject abc3568d... as a device-test boot;
- restore Candidate0046/Candidate0059 fixed-region packaging semantics;
- hard-gate exact stock header page, ramdisk placement/content, bytes outside kernel region, AVB0 metadata and AVBf footer;
- additionally hard-gate all 5 changed CRC + 11 added ABI symbols to per-symbol stable or reviewed MIXED_CONFLICT provenance before publishing the replacement boot;
- produce a package-only recovery artifact from the already compiled r60f98e6 Image while the corrected integrated workflow revalidates future builds.

Classification: BOOT_PACKAGING_REPAIR. The Direct-302 source/ABI result remains static evidence; device runtime validity is pending the corrected fixed-region boot.

## 2026-10-07 16:22 fixed-region retest: qxm_ipa Candidate0059 runtime inheritance missing

Latest device capture: lisa-twrp-deep-20261007-162206.zip.

Observed sequence:
- fastboot records flash:boot_a -> flash image status: Success -> reboot;
- subsequent mission boot loads vbmeta_a / boot_a / dtbo_a / vendor_boot_a and reaches Start EBS;
- oops/sda17 SHA256 remains 402b53f3583612c3cdd0a08a764535426645cff5ac2a8d24bff16d567b511351;
- minidump SHA256 remains 40bdc781b7e2a2ff8c52e50f9ad713168012b796d60adc8650b32eab2f48ea6d;
- rawdump SHA256 remains 605b2027582ca8c4b3c4d1e04d09ecc7b612dc9fe4ca97208c57bc2e3355710c;
- fixed-region/AVB packaging therefore did not restore Linux runtime evidence.

Historical controls prevent two false conclusions:
- Candidate0011 already tested watchdog 20000/15000 and still failed; restoring those values is required for a truthful C0059 control but is not claimed as the root cause.
- Candidate0012 already tested fixed-region/AVB preservation and still failed; packaging remains correct but is not sufficient.

The relevant historical breakthrough is Candidate0018: its exact Linux session reached about 0.954 s and faulted with synchronous external abort 0x96000010 in regmap_mmio_read32le, call path qcom_icc_set_qos -> qnoc_probe, at qxm_ipa QoS MAINCTL aggre2_noc@1700000 + 0x10008. Candidate0020 onward and Candidate0046 therefore keep qxm_ipa.qosbox=NULL and never touch that inaccessible MMIO.

C0061 reconstruction audit found that candidate_0061_recreate_c0059_uplift.py replayed selected Candidate0046 helpers but omitted c46.patch_yupik(). The post-302 runtime-contract gate also omitted this qxm_ipa invariant. Thus current C0061 did not actually reconstruct the real Candidate0059 early-runtime contract.

Repair:
- replay bounded c46.patch_yupik() only; no wholesale donor copy;
- hard-gate qxm_ipa.qosbox=NULL plus Candidate0046 runtime marker before and after Direct-302 materialization;
- restore Candidate0059 watchdog 20000/15000 to both control and target configs for equivalence;
- keep Direct-302 semantic strategy, strict ABI provenance, and fixed-region packaging unchanged;
- keep Phase7 blocked.

Classification: MIXED_CONFLICT / C0059_RUNTIME_EQUIVALENCE.

## Current next action

NEXT_ACTION:
Inspect the new pure Direct-302 Phase6 run triggered by this repair. Require C0061_C0059_QXM_IPA_QOS_INHERITANCE=PASS before the control build; require Candidate0059 watchdog 20000/15000 in control and target; require post-302 qxm_ipa hard-disable/qosbox NULL/runtime marker PASS before target compilation; then require 34/34 semantic closure, compile/modpost, strict 16/16 ABI provenance, identity, fixed-region AVB packaging, and a new device artifact. If the new boot still fails, compare the next persistent evidence specifically against Candidate0018/0019 early-Linux interconnect fault lineage before changing PAS, touch, or frequency controls.
