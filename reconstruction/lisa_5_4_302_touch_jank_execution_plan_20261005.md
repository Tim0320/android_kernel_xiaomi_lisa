# Lisa 5.4.302 + Touch/Jank stabilization execution plan

Plan version: 1.2
Updated: 2026-10-10
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
Status: DIRECT-302 SOURCE RECONSTRUCTION AND SEMANTIC CLOSURE PASS; SEE 2026-10-10 RUNTIME BLOCKER

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
Status: STATIC/ABI/IDENTITY/PACKAGING PASS; DEVICE NFC DEPLOYMENT AND BOOT NOT VERIFIED

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
Status: BLOCKED ON ANDROID RUNTIME BOOT, NFC MODULE ALIGNMENT AND FIRST-FAULT PROOF

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

## 2026-10-07 16:33 qxm-IPA rebuild CI failure: watchdog Kconfig recipe inheritance missing

Run 37594316840 failed at Prepare Candidate0059 same-run control config before any kernel build.

First concrete blocker:
- scripts/config requested QCOM_WATCHDOG_BARK_TIME=20000 and PET_TIME=15000;
- frozen 5.4.289 drivers/soc/qcom/Kconfig constrains bark to default/range 11000..11000 and pet to 9360..9360;
- olddefconfig therefore correctly normalized the requested values back to 11000/9360 and the new equivalence grep failed.

This is another bounded Candidate0046->0059 recipe inheritance omission, not a new kernel failure:
- Candidate0046 patch_stock_watchdog_timings() changes bark default to 20000 with range 11000..20000;
- changes pet default to 15000 with range 9360..15000;
- then writes the healthy-stock values to .config;
- real Candidate0059 inherits that recipe.

Repair:
- replay c46.patch_stock_watchdog_timings() immediately after c46.patch_yupik() in bounded Candidate0059 reconstruction;
- require pre-build watchdog Kconfig inheritance markers;
- require post-Direct-302 runtime-contract preservation of all four watchdog default/range invariants;
- retain qxm_ipa hard-disable as the primary early-runtime repair;
- do not treat watchdog timing alone as root cause because Candidate0011 already disproved that.

## 2026-10-07 19:47 device retest: Direct-302 reaches Android, first concrete crash is QTI NFC cdev race

Latest capture:
- lisa-twrp-deep-20261007-194701.zip.

Delta against 16:22 capture:
- minidump unchanged: 40bdc781b7e2a2ff8c52e50f9ad713168012b796d60adc8650b32eab2f48ea6d;
- rawdump unchanged: 605b2027582ca8c4b3c4d1e04d09ecc7b612dc9fe4ca97208c57bc2e3355710c;
- oops/sda17 changed from 402b53f... to 381c0179e25e1406863172eb5c521115a4ebbee724356fb769c2197d0790745d;
- therefore the 4f85557 kernel now reaches and writes fresh persistent Linux evidence.

Important runtime progress:
- kernel identity in the fresh Oops is 5.4.302-qgki-lisa-c0061-r4f85557-by-Tim0320;
- Android userspace/services are active by about 40 s;
- qxm_ipa early-MMIO blocker has been bypassed sufficiently to reach this stage;
- IPA PAS15 still returns -EINVAL (-22) in repeated attempts, but it is no longer the first boot blocker because Android proceeds beyond it.

First concrete Oops at 41.120904 s:
- task: nqnfcinfo, PID 2145;
- ESR 0x96000005, virtual address ffffffffffffffc8;
- pc mutex_lock+0x18/0x40;
- lr nfc_dev_open+0x30/0xf0 [nfc_i2c];
- exact release 5.4.302-qgki-lisa-c0061-r4f85557-by-Tim0320.

Source proof:
- drivers/nfc/qti/nfc_common.c performs container_of(inode->i_cdev, struct nfc_dev, c_dev) before validating the cdev;
- for this struct layout c_dev follows dev_ref_mutex by 0x38 bytes; a NULL inode->i_cdev therefore yields a negative container pointer and &dev_ref_mutex resolves to ffffffffffffffc8, exactly matching the device fault;
- this is a cdev publish/teardown race exposed by nqnfcinfo, not an NFC success condition.

Repair decision:
- add a bounded C0061 NFC cdev guard after Direct-302 materialization/runtime-contract verification;
- if inode or inode->i_cdev is unavailable, nfc_dev_open returns -ENODEV;
- release prefers filp->private_data and returns -ENODEV if the device is already unavailable;
- do not fake NFC success, do not change ioctl success semantics, do not replace NFC firmware;
- keep Candidate0059 frozen control unchanged;
- this mutation is DEVICE_RUNTIME_FIX and is applied only to the C0061 target tree.

## Historical next action (2026-10-07; superseded by the 2026-10-09 gate)

HISTORICAL_NEXT_ACTION:
Run the pure Direct-302 target again with the NFC cdev guard applied only after Candidate0059 control and Direct-302 runtime-contract gates. Require C0061_NFC_CDEV_GUARD=PASS, compile/modpost, strict ABI provenance removed=0, exact identity and fixed-region packaging. The resulting boot is the next device candidate. On retest, verify the ffffffffffffffc8 / nfc_dev_open Oops disappears. If the system still reboots, use the next fresh oops/sda17 delta to identify the next first fault rather than altering PAS/touch/frequency speculatively.


## 2026-10-07 r20b187c userspace evidence refinement

Evidence package:
- lisa-twrp-iter-0005_20261007-224443_boot_deee5ff41b61.zip
- collector version: 1.3.2
- boot SHA256: deee5ff41b617391c9ea88663596fed0cbf8b93d3d89f5d0e3e568f4d2788edf
- /data is decrypted and mounted in recovery.
- pstore is empty and /proc/last_kmsg is unavailable.
- no fresh r20b187c persistent kernel panic record was found; oops remains historical.
- bounded dropbox/tombstone/anr capture succeeded.

First concrete userspace fault retained in the failed-boot evidence:
- adbd runs from u:r:adbd:s0 and attempts a dyntransition to u:r:su:s0;
- SELinux enforcing denies that dyntransition;
- adbd then aborts with "Could not set SELinux context".
- This proves adbd entered the root-retention path, but it is not yet accepted as the sole device-reboot cause because adbd is not itself sufficient evidence of system_server/zygote/SF failure.

Decision:
- do not weaken SELinux and do not patch the kernel for this denial.
- keep qxm_ipa, PAS, watchdog, NFC, WALT, FREQ_QOS and Goodix frozen.
- investigate why a user/release HyperOS 3.0.9 A16 boot caused adbd to enter the root branch.
- collect static property sources, init adbd definition/overrides, debug marker files, /data/adb root-module indicators and persistent-property strings from recovery.
- collector v1.3.3 adds raw/22_adbd_debug_provenance.txt for this read-only provenance capture.
- only after root/debug provenance is established should a new boot/runtime intervention be selected.


## 2026-10-09 NFC runtime provenance collector update

- Collector v1.3.7 is committed at de5ee97bd582593433311f73fdc501f6195fcfdd.
- NFC runtime provenance scanning is symlink-aware for module trees and module files.
- Module membership lookup is limited to text manifests (modules.load*, modules.dep*, modules.order) instead of recursive grep across binary .ko files.
- vendor_dlkm and odm_dlkm fallback inspection remains strict read-only: ext4 ro,noload or EROFS ro only.
- This change does not prove Android runtime deployment. The next required evidence remains a fresh HyperOS 3.0.9 / Android 16 TWRP capture comparing device nfc_i2c.ko path/SHA256/vermagic/guard marker with the guarded CI module SHA256 aa512b78538003a2be63c1c28c03eaa05ff691e54d4f8b1556b282b14c52152b.
- Do not resume WALT/FREQ_QOS/Goodix/PAS intervention or approve a new boot candidate until the module source/deployment mismatch is resolved.

## 2026-10-09 19:54+08:00 — verified Direct-302 static gate; NFC runtime gate is next

Authoritative references at this review: repository HEAD c5469f08d72dcfe94055312dd99570388261f0dc; successful integrated run 37655937871, job 112910508641, target kernel source fb3b3c2c3d136e7f8abee1f45c24e69174fc119f. All 36 job steps completed successfully, including frozen Candidate0059 same-run control, Direct-302 semantic closure, Image/modules/dtbs, modpost, guarded NFC artifact, ABI/KMI (removed=0, reviewed changed/added provenance), identity and fixed-region boot packaging. This is **static/CI evidence**, not proof of a successful HyperOS 3.0.9 / Android 16 boot.

Collector v1.3.8 was committed in 3be8165802fc24feb3ec01d6e66b5232a7e24f4a and 899c225ea65c6457a7c8bb2611de0bc52bd4a2c8. Read-back verifies colon-safe nfc_i2c.ko manifest entries, symlink-aware file/manifest discovery and exact **text** modules.dep matching; modules.dep.bin is deliberately excluded. The prior collector v1.3.7 reference above is historical.

The integrated CI log contains 886 `LLVM ERROR: IO failure on output stream: Broken pipe` lines (443 during the frozen control compilation, 443 during the 5.4.302 target compilation), despite a passing job. A `$(LLVM_NM) ... | grep -q __ksymtab` early-close/SIGPIPE mechanism is a plausible **unproven** explanation; the messages have not been traced to their exact subprocesses. Do not call these diagnostics fixed, nor treat them as proof of broken kernel objects. Preserve the evidence for a future narrow diagnostic investigation; avoid recompiling an unchanged kernel solely to suppress logging.

The first unresolved validation gate is **DEVICE_NFC_RUNTIME_DEPLOYMENT_UNVERIFIED**: no fresh device-side module hash, vermagic, resolved path, manifest membership, or Android actual-load evidence for the guarded CI module is available. Distinguish (1) a partition/module hash match from (2) proof of actual Android module loading and (3) disappearance of the historical nfc_dev_open/ffffffffffffffc8 Oops. If the active device module differs from the guarded CI SHA256 `aa512b78538003a2be63c1c28c03eaa05ff691e54d4f8b1556b282b14c52152b`, investigate packaging/deployment of a **matched kernel+module**, not another blind same-kernel build. If it matches, investigate the next fresh first-fault evidence. Keep Candidate0059 r43da7c5 frozen. No speculative WALT/MIGT/Goodix/PAS changes, false success signals, weakened SELinux, disabled thermal, or global frequency pins.

CURRENT_NEXT_ACTION: obtain fresh collector v1.3.8 read-only evidence `raw/23_nfc_runtime_module_provenance.txt` on HyperOS 3.0.9/A16; audit symlink-resolved nfc_i2c.ko path, SHA256/vermagic/guard, text module manifests and RO vendor_dlkm/odm_dlkm mounts; compare to guarded CI hash; then obtain actual module-load and fresh first-fault evidence before a new runtime intervention.

## 2026-10-10 01:21+08:00 - TWRP NFC provenance collection transport correction

New device evidence: `lisa-twrp-iter-0002_20261010-012126_boot_038e35371c97.zip` is collector v1.3.8 and contains `raw/23_nfc_runtime_module_provenance.txt`, but BOTH `raw/22` and `raw/23` failed with `/system/bin/sh: syntax error: unexpected '('`. Thus module SHA256/vermagic/manifest membership and adbd/root provenance remain **uncollected**, not negative findings. Checking the captured remote source with POSIX `sh -n` and `bash -n` passes: the issue is likely Windows PowerShell/ADB inline command quoting, not shell program grammar or a kernel exception.

The new capture's `oops` SHA256 `5e29f593cfa25b166e28bea8082157544891d34558929531e4fcd3303d20701d`, `logdump` SHA256 `08cf91fa91ba50db1e55bb54fa1d7efda2cee491c97e2f7fd7f1160d2d825f9a`, and `/cache/recovery/last_kmsg` are byte-identical to the 01:06 capture. There is **no new distinguishable current-boot kernel crash record** in those sources. Do not assign old C0054 or IPA/PAS/NFC messages to this reboot without freshness proof.

Collector repair `37a699e` changes only the two long probes to write exact shell script text on the host, transfer to TWRP's RAM-only `/tmp` with `adb push`, execute `adb shell sh /tmp/...` and clean up; other probes are unchanged. Collector version incremented to **v1.3.9** at `76fb6e0`. The evidence-only GitHub Action `37965996926` passed its PowerShell syntax and metadata gates, **not** a physical TWRP execution test and **not** kernel/boot validation. Do not modify Candidate0059, stable uplift, WALT/MIGT, Goodix or PAS just to fix a collector transport failure.

**Current next action:** collect **one** fresh v1.3.9 TWRP ZIP, confirm `raw/22` and `raw/23` include `transport=adb_push_tmp_sh` and a successful `exit_code=0`, and inspect real module path/SHA256/vermagic/manifest and root properties. Compare device NFC module with separate CI guard SHA256 `aa512b78538003a2be63c1c28c03eaa05ff691e54d4f8b1556b282b14c52152b`; independent Android load and current first-fault evidence remain required before any kernel or module deployment intervention.

## 2026-10-10 01:27+08:00 - TWRP v1.3.9 read-only device probe result

Capture: `lisa-twrp-iter-0001_20261010-012711_boot_038e35371c97.zip`, collector **v1.3.9**, boot SHA256 `038e35371c9705fd44908157ce456576100dfcb07f14ef60aa31e3b669c2eed6`, slot `_a`, first-screen reboot reported. The NFC probe `raw/23` now runs with `transport=adb_push_tmp_sh` and `exit_code=0`: the previous inline quotation failure is resolved for this probe. However **no Android NFC module hash or vermagic is available**.

Device evidence shows why: `/vendor/lib/modules/1.1` is TWRP's tmpfs, `/vendor_dlkm/lib/modules` and `/odm_dlkm/lib/modules` are absent, and the collector reported `VENDOR-READONLY_MOUNT_FAILED` plus `ODM-READONLY_MOUNT_FAILED`. Critically, TWRP's by-name table **does** expose the Android `vendor` logical partition as `/dev/block/dm-5` via `/dev/block/by-name/vendor`. This is a **collector partition coverage gap**, NOT proof `nfc_i2c.ko` is absent or that the guarded CI module was deployed. Vendor files were not modified.

The `raw/22` adbd provenance probe used RAM-script transport but still failed with `syntax error: unmatched 'if'`, consistent with a dense shell line not parsing correctly under recovery's shell. No valid Android adbd/root provenance was obtained from this probe. The persistent Oops and Logdump SHA256 remain `5e29f593cfa25b166e28bea8082157544891d34558929531e4fcd3303d20701d` and `08cf91fa91ba50db1e55bb54fa1d7efda2cee491c97e2f7fd7f1160d2d825f9a`, respectively, unchanged from the previous capture. Recovery history and userspace evidence do not establish a new 2026-10-10 first-fault. Do not promote historical C0054/PAS/NFC faults as current-root-cause evidence.

**Collector-only correction**: at `0ff4ddd`, version **v1.4.0** normalizes Windows line endings, replaces adbd's dense one-line shell with simple multiline commands and scans the mapped Android `vendor` logical partition via by-name aliases strictly read-only (ext4 `ro,noload` or EROFS `ro`). On no successful mapped mount, record the failure rather than fabricate module identity. Independent CI `37966876041` (commit `6eecc50`) passed PowerShell AST, bash/dash remote shell syntax and state/static-CI audit. These CI gates do **not** prove actual TWRP execution, Android NFC module loading or stable Android boot.

**Next action:** acquire one fresh v1.4.0 read-only TWRP capture to check `VENDOR_BASE-READONLY_MOUNTED`, module path/hash/vermagic and text manifests against CI guarded NFC SHA256 `aa512b78538003a2be63c1c28c03eaa05ff691e54d4f8b1556b282b14c52152b`; separately investigate a fresh Android first-fault and actual NFC load. Keep C0059 frozen; no same-source rebuild, batch loop or speculative PAS/Goodix/WALT/MIGT changes.

## 2026-10-10 01:35+08:00 - verified vendor NFC module mismatch; deployment-first repair gate

Fresh physical-device capture: `lisa-twrp-iter-0002_20261010-013518_boot_038e35371c97.zip`, collector v1.4.0, same Direct-302 boot SHA256 `038e35371c9705fd44908157ce456576100dfcb07f14ef60aa31e3b669c2eed6`. User's note **"進system層後閃退"** (reaches system layer, then crashes); do not describe this as an independently observed first-screen-only failure. `raw/22` and `raw/23` both complete with `transport=adb_push_tmp_sh` and `exit_code=0`. Recovery adbd root labels are NOT Android adbd/root-state evidence.

TWRP mounted `/dev/block/mapper/vendor_a` EROFS strictly `ro`. Two vendor files exist, both with 5.4.289 vermagic; text `modules.load` and `modules.dep` list each path:
- `/vendor/lib/modules/5.4-gki/nfc_i2c.ko` SHA256 `bb1e8994d0ddf0b15bd038457a850b2a8b5c7b74e1816b97dea5623c2ea5c80b`; vermagic `5.4.289-g5987d69e25da`.
- `/vendor/lib/modules/nfc_i2c.ko` SHA256 `b37dae41aad83b6adaa1f2a16253d2a8ca931b83a534fd5fb57ceaea2424bc68`; vermagic `5.4.289-qgki-g5987d69e25da`.

Freshly downloaded and independently inspected the exact successful integrated-302 run `37655937871` artifact `11500359180`: `candidate-0061-runtime-modules/nfc_i2c.ko` SHA256 `aa512b78538003a2be63c1c28c03eaa05ff691e54d4f8b1556b282b14c52152b`; vermagic `5.4.302-qgki-lisa-c0061-rfb3b3c2-by-Tim0320`; cdev guard marker PRESENT. Therefore **guarded module not deployed in either inspected vendor file**. This proves a deployment/content mismatch, **not** actual Android loading, cause of reboot, or inevitable vermagic rejection. The boot.img intentionally does not modify vendor EROFS. Oops/logdump hashes remain unchanged across the previous captures and no fresh first-fault was identified.

The engineering next step is no longer another identical kernel rebuild. Confirm init/module selection and a reversible Android-16-compatible deployment method for a **matched C0061 kernel+module** (modversions/CRC, AVB and EROFS constraints, backups and rollback). Never write blindly into `/vendor`, weaken SELinux, disable thermal or treat an inspection archive as flashable.

Evidence report: `reconstruction/c0061_vendor_nfc_runtime_mismatch_20261010.md`. Separate new GitHub staging Action `37967884526` **SUCCESS**, artifact `11634242690`, packages original CI-verified guarded .ko, SHA256SUMS, identity and on-device mismatch manifest as an **inspection-only / NOT FLASHABLE** ZIP. Module staging does not count as a newly built boot, actual phone module deployment or Phase10 device PASS. Keep C0059 frozen and Direct-302 uplift immutable until this boundary is resolved.

## 2026-10-10 - AOSP vendor-module-loading references; USER_LOGS_PENDING

The user explicitly requests **priority display of "使用者待處理：取日誌"** whenever a needed physical-device log is blocked, and a pause of the existing single Lisa automation if reliable relevant forum/upstream guidance identifies a specific log-gated hypothesis. This is a pause for evidence, **not** acceptance of boot.img or termination of Candidate0061.

Relevant external documentation (mechanism, NOT proof of this Lisa boot's root cause):
- Android official kernel module guidance: https://source.android.google.cn/docs/core/architecture/kernel/loadable-kernel-modules?hl=zh-tw . Kernel modules are normally built for their target kernel, and CONFIG_MODVERSIONS checks ABI-related symbol CRC during module load. The vendor init/modprobe/module paths must be inspected.
- AOSP module installation / first-stage loading: https://source.android.com/docs/core/architecture/kernel/kernel-module-support . Depending on stage, modules may be in vendor boot ramdisk or Android vendor directories and loaded via modules.load/init.rc.
- Android vendor/odm DLKM layout: https://source.android.com/docs/core/architecture/partitions/vendor-odm-dlkm-partition . The vendor/vendor_dlkm mapping depends on device layout; do not assume Lisa has a separate vendor_dlkm dynamic partition.
- Related *anecdotal* custom GKI community discussion: https://groups.google.com/g/perbenanoun/c/hACT8j0IiSw . It describes core kernel replacement while vendor module files remain on a verified dynamic partition and suggests a vendor-boot-based workaround for some devices. This is NOT verified on Lisa and must NOT be followed blindly; AVB, init ordering and rollback differ.

This matters because the real 2026-10-10 Lisa vendor_a EROFS evidence identifies two 5.4.289 nfc_i2c.ko files while its paired compiled C0061 NFC module has exact 5.4.302 release and a cdev guard. The exact Android-loaded NFC module and whether a failed load or other first fault caused the reboot remain unknown. Neither changing vermagic strings nor disabling verification/SELinux constitutes a valid fix.

**Prioritized new evidence rather than another repeat TWRP dump:**
1. With TWRP ADB=recovery currently available, read-only mount /dev/block/mapper/vendor_a (EROFS ro), retrieve `/etc/init` from that *mapped Android vendor filesystem* and inspect `insmod`, `modprobe`, `nfc_i2c` and `modules.load` paths; also inspect actual vendor-boot module manifests where available. The prior raw/23 capture already contains vendor module hashes/manifests and does not need repeating.
2. Only if Android ADB=device becomes available during a boot attempt, collect Android `logcat -b all`, `/proc/modules` and permitted dmesg entries containing `nfc`, `modprobe`, `vermagic`, `Unknown symbol`, `Invalid module format`, `init`, `watchdog`, and the first contemporaneous fault. If ADB is unavailable, do not misattribute recovery logs as Android runtime evidence.
3. Record exactly which layer each log came from and do not ask user to reflash identical boot only to repeat unchanged historical Oops/Logdump.

**Automation:** single existing task ID `6ac29deeada88191891ff651309f5641`; pause it while awaiting new decisive user log(s), as newly directed by the user, and resume only after an upload or the user's explicit "繼續". No new tasks, no RRULE, no uninformed kernel/firmware modifications.

## 2026-10-10 — new vendor init ZIP confirms loader entrypoint; mandatory Action link reporting

New read-only vendor `.rc` evidence: `lisa_nfc_init_logs.zip`, SHA256 `866164c26a20201f4051732e99441525972d3cfced1e2cf2d1adabcd7b623ec0`, 156 Android vendor `.rc` files. `init.target.rc` has `early-init: exec ... /vendor/bin/vendor_modprobe.sh`; `init.qcom.rc:421` defines `nqnfcinfo` as `late_start` and `oneshot`; `vendor.nxp.hardware.nfc@2.0-service.rc` defines the NFC HAL. No direct literal `nfc_i2c` / `modules.load` appears in any captured `.rc`, so Android-selected 5.4.289 NFC module remains unresolved. See full referenced evidence report `reconstruction/c0061_vendor_init_module_route_20261010.md`. Next highest value file is **`/vendor/bin/vendor_modprobe.sh`** from TWRP read-only mounted vendor_a (no repeat old Oops/Logdump, no boot reflash). If Android ADB becomes available, prefer its real logcat / loaded modules / fresh fault.

**New user-required report contract for every scheduled or interactive round:**
- Always show `最新 Action 網址：<exact GitHub Actions run link>` if a new relevant run occurred, otherwise `最新 Action 網址：無` (older reference runs may be shown separately with clear labels).
- Append **`boot打包可準備測試`** immediately after the Action URL ONLY if that exact run has already built/packaged a new `boot.img`, passed its static/ABI/KMI/identity/packaging gates and its artifact is verified available for a next physical test. Provide kernel commit, boot SHA256 and artifact URL; this label does not imply the phone booted.
- Evidence audits, documentation/state-only commits and the NFC inspection-only module artifact are NEVER tagged as flashable/new boot.
- If additional user logs are needed, begin with `使用者待處理：取日誌`; updated collection scripts must also say `採集腳本已更新` and link the tested version and command.
- Only the existing Lisa one-shot automation ID is allowed; pause when a strong evidence-gated external lead requires a specific user log, then resume same ID upon upload or explicit continue.

## 2026-10-10 — vendor_modprobe.sh read-back: conditional whole-directory fallback

User uploaded `lisa_nfc_loader.zip`, verified one 1429-byte `vendor_modprobe.sh` sourced from Android vendor_a. File ZIP SHA256 `3a39c7aa9ec83900de764064dde663b56c269c593277419d16e53e941d4d8f79`; shell syntax `bash -n` / `dash -n` PASS. Script has a proprietary header: summarize, do not publish full contents. Complete static analysis `reconstruction/c0061_vendor_modprobe_branch_evidence_20261010.md` commit `d8b5e26`.

**Verified algorithm:** vendor early-init enumerates `/vendor/lib/modules`; after trying the first module excluded from `modules.blocklist`, it switches the *entire* remaining batch to `/vendor/lib/modules/5.4-gki` if and only if that first probe returns nonzero. A failure among later modules does **not** cause per-module fallback. It concurrently loads most remaining modules from the selected directory. Both inspected directories currently have 5.4.289 NFC modules, not the separate C0061 5.4.302 guarded NFC CI module. Loader does not itself implement automatic C0061 module deployment. There may be cross-module compatibility issues beyond NFC. No evidence yet identifies which branch was taken or which module actually failed, and 5.4.289 vermagic difference alone does not prove reboot cause.

Official Android documentation corroborates module-directory / init / modversions mechanisms, not a Lisa-specific root cause:
https://source.android.com/docs/core/architecture/kernel/kernel-module-support
https://source.android.com/docs/core/architecture/kernel/loadable-kernel-modules
https://android.googlesource.com/platform/system/core/+/android16-release/init/first_stage_init.cpp
https://android.googlesource.com/platform/system/core/+/android16-qpr2-release/toolbox/modprobe.cpp

**New decisive targeted evidence:** from already usable TWRP ADB=recovery read-only mounted mapped vendor_a, collect `modules.blocklist`, `modules.load`, and `modules.dep` for both `/vendor/lib/modules/` and `/vendor/lib/modules/5.4-gki/`. These are static module-order/dependency/blacklist context, not actual runtime module load proof. Only if Android ADB=device is available during boot, collect its actual `logcat /proc/modules / dmesg` and first error. No repeated unchanged Oops/Logdump or boot flash. Per user request, report `使用者待處理：取日誌`, provide a read-only PowerShell recipe, pause same single automation while awaiting this materially new evidence, then resume when uploaded.

**Every report:** `最新 Action 網址：<new run URL>` or `無`. No Action that only audits metadata is `boot打包可準備測試`. Existing Direct-302 static run 37655937871 is not device PASS; NFC staging 37967884526 is inspection-only.

## 2026-10-10 21:22+08 — two vendor module sets audited; standard Windows log working directory fixed

New ZIP `lisa_nfc_module_configs_20261010-212249.zip`, SHA256 `3a8717640a28b8facbd46e59bf796a577b462bbce1cc7d521d768e7218b6ac0b`, includes valid `modules.load` and `modules.dep` for two read-only Android vendor module locations:
- `/vendor/lib/modules`: 107 distinct `.ko` in load list and 107 matching dep entries; NFC at position 66, no hard dep listed; 211 dependency links, all resolvable by manifest name.
- `/vendor/lib/modules/5.4-gki`: 227 distinct `.ko`, 227 matching dep entries; NFC at position 139, no hard dep listed; 741 dependency links, all resolvable by manifest name.
- 63 names overlap; 44 only in first, 164 only in second. **Both `modules.blocklist` pull operations returned failure**, so blocklist actual existence remains unproven. If absent, the vendor script's pipeline may treat the first `modprobe -l` item as the non-blocklisted probe; its list order is not determined by the first `modules.load` line.
- This strongly supports a **whole-module-set boot compatibility** investigation, not NFC-only speculation. A clean textual `modules.dep` does not prove 5.4.302 KMI/CRC compatibility or actual Android loading.

Complete evidence and boundaries: `reconstruction/c0061_vendor_module_manifest_audit_20261010.md`, commit `bbe9fd7`. Upstream Android modprobe documents the list, blocklist and dependency behaviors but is not the exact proprietary device binary: https://android.googlesource.com/platform/system/core/+/d5e026e1a/toolbox/modprobe.cpp .

**User fixed path, mandatory for all subsequent Lisa TWRP/ADB PowerShell snippets and collection scripts:** always start with `Set-Location "D:\1.ROM_Prot\lisa\pull_log"` and output/download scripts, logs and ZIP in that directory, explicitly supplying output-root parameters where supported. Do not silently use `D:\1.ROM_Prot\lisa` or `D:\1.ROM_Prot\lisa\boot` as working directories.

**Next:** with this new physical evidence, resume the same paused Lisa automation and work on ABI/module compatibility, loader order and reversible deployment planning. Do not request redundant logs or a repeat boot test yet. If truly decisive additional device data is required, clearly label `使用者待處理：取日誌` and provide a narrow read-only request rooted at the fixed path, then pause according to the prior rule. Always include a new Action URL or `無`; only label `boot打包可準備測試` on a new verified matching boot.img artifact run.

## 2026-10-10 21:40+08 — real imported-symbol CRC gate passed; need exact device NFC ELF bytes

New substantive GitHub workflow `.github/workflows/verify-lisa-candidate-0061-nfc-crc.yml` and parser `reconstruction/scripts/candidate_0061_module_crc_preflight.py`: script commit `a1169ef`, workflow `f4d3d0f`, final artifact retention change `6c8199a`. Completed Action `38056564905` **SUCCESS**; artifact `11672061727` contains the actual integrated 5.4.302 `Module.symvers` (830233 bytes) plus machine-readable CRC report. Verified against downloaded report: the real guarded `nfc_i2c.ko` SHA256 `aa512b78538003a2be63c1c28c03eaa05ff691e54d4f8b1556b282b14c52152b` imports **71** symbol CRCs and **all 71 match the same build**; zero missing/mismatches/ambiguous names. CI also confirmed a deliberately corrupted `module_layout` CRC is rejected. This is a useful **same-build ELF/KMI consistency gate**, not an Android device ABI/load or boot pass; no new Kernel or boot.img was compiled.

Official Android docs: https://source.android.com/docs/core/architecture/kernel/loadable-kernel-modules and https://source.android.com/docs/core/architecture/kernel/abi-monitor . With `CONFIG_MODVERSIONS`, comparing imported symbol CRCs is more decisive than release-number differences alone: **5.4.289 versus 5.4.302 vermagic release prefix is not, by itself, proof of failure**. AOSP `libmodprobe` source (https://android.googlesource.com/platform/system/core/+/android16-qpr2-release/libmodprobe/libmodprobe.cpp) shows `ListModules` enumerates `module_deps_`, not explicitly `modules.load` order; still the actual Xiaomi vendor modprobe binary's output is not recorded.

**Decisive narrow user evidence required now:** read-only TWRP pull only TWO existing vendor NFC ELF files from mapped `vendor_a` EROFS, **not** repeat `pstore`/Oops/logdump or reflash Boot. Paths `/vendor/lib/modules/nfc_i2c.ko` (QGKI SHA256 `b37dae41aad83b6adaa1f2a16253d2a8ca931b83a534fd5fb57ceaea2424bc68`) and `/vendor/lib/modules/5.4-gki/nfc_i2c.ko` (GKI SHA256 `bb1e8994d0ddf0b15bd038457a850b2a8b5c7b74e1816b97dea5623c2ea5c80b`). Instructions MUST begin `Set-Location "D:\1.ROM_Prot\lisa\pull_log"`, use only TWRP adb=get-state recovery, mount `/dev/block/mapper/vendor_a` EROFS strictly `ro`, copy files to the fixed Windows directory, verify local SHA256, ZIP privately for conversation. Never commit or publish proprietary OEM module binaries to GitHub.

Once provided, parse each device ELF's `__versions` offline and compare symbol-by-symbol to the actual candidate `Module.symvers` from Action `38056564905`: report matched, mismatched, missing imports and remaining vermagic flags; then decide whether the loader's QGKI/GKI branch has provable failure potential. If no incompatible imports found, do not blame NFC; refocus contemporaneous boot fault and whole-module-set ABI. Avoid editing vendor EROFS/AVB, forcing modules, or building an unchanged kernel. Per user's evidence-gated automation rule, temporarily pause the **same** Lisa automation while waiting for these exact two files and resume that same ID on upload or explicit continue.

**Reporting:** latest Action exact URL or `無`; do **not** append `boot打包可準備測試` to CRC evidence workflow. Include next schedule time and user action in the terminal summary table (no text afterward).

## 2026-10-10 21:55+08 — original vendor NFC ELF CRC comparison closes immediate ABI question

The user supplied `lisa_nfc_crc_20261010-215518.zip` (SHA256 `c7beb4f6de91e6952bd41b2b191be5748f92f3ab8f4e37a5710f9a0dec730a71`). Both stock `nfc_i2c.ko` files were independently verified against prior `vendor_a` TWRP SHA256, inspected offline as AArch64 ELF and compared by **every imported `__versions` CRC** to the exact Candidate0061 5.4.302 `Module.symvers` saved in CRC Action `38056564905`, artifact `11672061727`.

**New grounded results:** the actual QGKI `/vendor/lib/modules/nfc_i2c.ko` (SHA `b37dae41aad83b6adaa1f2a16253d2a8ca931b83a534fd5fb57ceaea2424bc68`) matches **71 of 71 CRCs**, has **zero** missing exports and **zero** CRC mismatches, with `module_layout=0xba39cbb8` matching the C0061 build. The stock GKI `/vendor/lib/modules/5.4-gki/nfc_i2c.ko` (SHA `bb1e8994d0ddf0b15bd038457a850b2a8b5c7b74e1816b97dea5623c2ea5c80b`) matches **36 of 68**, has **32** symbol CRC mismatches, zero missing exports, and `module_layout=0x1e5b7ab7` rather than C0061 `0xba39cbb8`. Included among the mismatched 32: `module_layout`, cdev, I2C, GPIO, regulator symbols. Shared 68 import symbols differ in exactly those 32 CRCs between QGKI and GKI. Release-string-only comparison was misleading for modversions-enabled kernel; the CRC evidence is the correct discriminator.

**Interpretation:** QGKI stock NFC has confirmed *import CRC identity* vs C0061, not proven actual module loading or guarded cdev fix. GKI NFC has concrete imported-symbol ABI incompatibility under normal modversions if chosen. This strengthens the *conditional* risk of a whole-directory GKI fallback, but **does not prove the fallback occurred** or caused the recent system-stage reboot. Before requesting more user logs, use already captured loader, QGKI/GKI manifests, Linux/AOSP modprobe code and kernel build artifacts to prioritize actual first-probe ordering and implications. If a live first-fault diagnostic becomes required, design a narrowly scoped feasible ADB/TWRP collection; don't demand repeat full TWRP ZIP or flash unchanged boot.

**Reusable code committed without OEM binaries:** `reconstruction/scripts/candidate_0061_stock_nfc_crc_compare.py` at `aaab25f`. Detailed read-only evidence: `reconstruction/c0061_stock_nfc_crc_comparison_20261010.md` at `9a968d3`. Keep proprietary `.ko` contents in private conversation only; commit no binaries to GitHub.

**Automation:** user has delivered the specific files which blocked the single Lisa task. Resume **existing** automation ID `6ac29deeada88191891ff651309f5641` for the next autonomous analysis turn; pause again only if a truly new log-gated decision arises. Continue no-flash, preserve Candidate0059. Latest Action URL, Kernel Build, Boot packaging, next scheduled time, technical description, and user action must be in the report-ending table.

## 2026-10-10 22:08+08 — dependency graph gate and vendor loader exit-status interpretation

The user requested continuing **autonomous** Candidate0061 triage. Latest GitHub HEAD was `0380e58`, last full Direct-302 kernel build `37655937871`; no new kernel/boot was available at the start. With the previously supplied real vendor manifests (ZIP SHA256 `3a8717640a28b8facbd46e59bf796a577b462bbce1cc7d521d768e7218b6ac0b`), an independent Python graph traversal verified QGKI 107 modules/211 hard dependency edges vs GKI 227 modules/741 edges; 63 shared names, 44 only QGKI, 164 only GKI. Both dependency sets have **zero unresolved references and zero cycles**. QGKI high fan-in `q6_pdr_dlkm` 20, `q6_notifier_dlkm` 19, `snd_event_dlkm` 19; GKI `qmi_helpers` 76, `subsystem_restart` 68, `service-locator` 45. These are **structural only**, not symbol ABI or observed Android-loaded modules. Raw OEM manifest content stays local/private.

**New guarded implementation:** `reconstruction/scripts/candidate_0061_vendor_manifest_graph.py` commit `3e4c3c9`; added fixture-based no-missing-deps/cycle-detection/first-probe-unknown tests to existing CRC workflow commit `d07ace2`; Action `38058408963` **SUCCESS**, not a Kernel Build. Detailed evidence `reconstruction/c0061_vendor_fallback_graph_and_exit_status_20261010.md` at `5f6546a`.

**Important loader limitation:** AOSP `modprobe -l` lists from its internal dependency collection, not necessarily first line of `modules.load`; actual Xiaomi binary ordering is unmeasured. Both modules.blocklist ADB pulls failed, *not* proof file absence. The vendor script performs a **single initial** QGKI modprobe failure test to switch the **whole remaining batch** to GKI; later background individual modprobe failures do not trigger per-module fallback. The script ends with **bare `wait`**, which POSIX specifies returns zero after waiting for all children even when some child commands fail. Host bash/dash tests confirmed `(exit 7) & wait` returns zero. Hence an init-script SUCCESS alone cannot establish every module load succeeded. Mechanisms: https://android.googlesource.com/platform/system/core/+/android16-qpr2-release/libmodprobe/libmodprobe.cpp and https://www.man7.org/linux/man-pages/man1/wait.1p.html ; not current Android log proof.

Next round should first examine the exact C0061 boot/module packaging and vendor loader candidate sets against available Kernel exports, not request duplicated TWRP logs or repeat identical Boot. A future actionable physical request must justify how it could distinguish the actual initial QGKI probe/fallback and contemporary first fault, and obey fixed PowerShell workdir `Set-Location "D:\1.ROM_Prot\lisa\pull_log"`. Safeguard C0059 frozen, preserve EROFS/AVB, do not mislabel CRC/graph audit as a flashable boot. Resume the one existing Lisa single-shot schedule for autonomous review, using actual next DTSTART in the report-ending table.

## 2026-10-10 22:15+08 — verified ELF export-provider closure for 5.4.302 and stock NFC (not Android boot)

New `reconstruction/scripts/candidate_0061_module_provider_gate.py` at commit `ea04448` walks the *actual* C0061 `Module.symvers` provider table and differentiates imports exported by `vmlinux` from imports requiring other compiled `.ko` providers. CI integration initially corrupted workflow YAML (`c9f6871`; no jobs started, Action `38058881768` failure), then **restored the prior passing workflow** and added isolated provider check at `fd04d8e`. The corrected Action [`38058926584`](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/38058926584) **SUCCESS** with artifact `11670969708`; downloaded its real JSON and confirmed the guarded NFC `aa512b78538003a2be63c1c28c03eaa05ff691e54d4f8b1556b282b14c52152b` imports **71/71 names from `vmlinux`**, has zero symbols supplied by other modules, zero absent exports and zero CRC mismatches. No Kernel or Boot build was run.

Using the earlier user-uploaded **private** original QGKI/GKI NFC ELF binaries, independently cross-joined their real `__versions` records to the **same** Direct-302 `Module.symvers` (14434 exports / 14059 from `vmlinux`). Full stock results:
- QGKI NFC SHA `b37dae41aad83b6adaa1f2a16253d2a8ca931b83a534fd5fb57ceaea2424bc68`: **71 imports; 71 `vmlinux`; zero other-module providers; 71 CRC match; zero missing**.
- GKI NFC SHA `bb1e8994d0ddf0b15bd038457a850b2a8b5c7b74e1816b97dea5623c2ea5c80b`: **68 imports; 68 `vmlinux`; zero other-module providers; 36 CRC match; 32 mismatch; zero missing**.
- Therefore a *missing intermediate module provider* does **not** explain the direct NFC imports in this C0061 build. The conditional GKI NFC `module_layout`/CRC conflict still exists. Other 107 QGKI / 227 GKI drivers are NOT implicitly ABI cleared, and neither Android selected branch nor first-fault was observed. No OEM proprietary `.ko` were published to GitHub or Actions.

Exact methodology and source evidence: `reconstruction/c0061_nfc_export_provider_analysis_20261010.md` at `aacbcb9`. The fixed-region `boot.img` workflow packs Kernel Image only with stock ramdisk/AVB bytes preserved, while guarded `nfc_i2c.ko` is an independent artifact, not automatically deployed to EROFS vendor. Do not reflash unchanged boot or install standalone inspection-only module.

**Next autonomous work:** investigate QGKI *first `modprobe -l` probe* and selection of conditional GKI whole-module fallback using grounded loader binary/source; prioritize high-impact non-NFC module ABI/provisioning if evidence permits. Confirm boot-module packaging compatibility and rollback feasibility before any future source fix. User does not need to provide more NFC CRC files or repeat historic TWRP logs. Existing single Lisa automation continues; only a truly decisive missing **new** runtime log justifies pause. Report exact new Action URLs, whether Kernel Build/new boot exists, schedule, and user operation as final table.
