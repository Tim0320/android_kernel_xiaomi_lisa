# Candidate0057: retain build outputs before independent verification

## Latest observed failure

Source package `3d372a0e663fcf3fca0bc9c5389c26c1d52ff112`, run
`37181431324`, build job `111374641052`: compilation and packaging succeeded.
Verification stopped at `candidate_0057_identity.py:97`:

```
RuntimeError: Final Image branding differs from requested identity: Linux version %s (%s)
```

Failure artifact `11296320085`, SHA256
`3a50c82aec889379f0efe4d24c3fe7aeccb2172b7e8f6374a8747350c6938679`,
contains the complete small verify log, generated identity record, config,
symbol maps and donor flash module. It does NOT contain boot.img or Image.
The disposed runner's unsaved binaries cannot be reconstructed from those
reports. A new build is needed to establish the first reusable checkpoint.

The log confirms the stock flash/battery contract, 84/84 module ownership,
power 2/2, UFS 7/7 plus linked call, display 736 imports, prior source gates
and artifact gate passed before identity checking failed. This is not evidence
of a new device runtime failure.

## Identity correction

A raw first-match search selected the kernel's `linux_proc_banner` formatting
string rather than its concrete compiled `linux_banner`. The new parser ignores
non-numeric printf templates and requires exactly one distinct concrete version
banner. It still rejects wrong releases, authors, build numbers, missing
banners and conflicting concrete banners. It additionally checks the saved
identity, compiled UTS header and unchanged module-loader hash/policy.

The builder and ownership patch remain byte-exact:

- candidate_0057_build.py blob `dd3eca7bcbd3a5914b8b766ec34950359ab690c6`
- candidate_0057_ownership_patch.py blob `4c3152361dc338fbc92673a9be7d8941da9de200`

No runtime driver, ABI/CRC/CFI policy, battery algorithm, GPU setting or kernel
base upgrade is introduced. Identity-generation/install functions are unchanged.

## Pipeline and artifact meanings

`plan -> build -> saved UNVERIFIED boot -> saved checkpoint -> separate verify job`

1. `lisa-c0057-UNVERIFIED-boot-aN` is uploaded immediately after packaging,
   before checkpoint construction and external verification. Its upload is also
   attempted if packaging has exited with an error but a nonempty boot exists.
   It includes a prominent DO-NOT-FLASH warning, fresh boot SHA256, Image,
   configs, identity and symbol maps. This is diagnostic access, NOT approval.
2. `lisa-c0057-reverify-inputs-aN` contains a compressed, hashed checkpoint:
   original build identity, exact required source/config/ELF/object files,
   reference modules, reports, boot/Image, plus vmlinux when available.
   No .git credentials, .env files or private device logs are collected.
3. `lisa-candidate-0057-verified-aN` is published ONLY after the independent
   verifier and provenance checks succeed. It is a static verification pass,
   not a claim that the phone, Wi-Fi, camera or graphics have passed testing.
4. Build and verification evidence are always uploaded separately. All these
   artifacts request 14-day retention, subject to repository storage limits.

The checkpoint tar is already compressed; artifact ZIP uses compression level0.
The raw boot package uses level1. Hidden files are enabled only for explicitly
allowlisted paths, including the checkpoint container and .config. Artifact
names include the attempt number so reruns do not overwrite prior evidence.
Automatic cancellation of in-progress builds is disabled.

## No-rebuild retry

For transient verification failures, rerun the failed jobs (verify/observe),
NOT the successful build job. After a verifier-only code fix, use the workflow's
`workflow_dispatch` input `source_run_id` to select the ORIGINAL build run.

For connector workflows without an Actions-dispatch write action, atomically
commit the verifier fix together with a change to:

`reconstruction/candidate_0057_reverify_request.json`

Example schema (replace the example number with a run that really has a saved
checkpoint; do not use the old failed run, which has no checkpoint):

```json
{"source_run_id":"ORIGINAL_BUILD_RUN_ID", "request":"unique repair revision"}
```

The value must be a positive numeric string. The request file must change in
that same push. `plan` recognizes it and skips compilation. If the file is not
changed, a normal matching push requests a new build. Changing the request
nonce allows another verification of the same original source. The request
file is intentionally NOT created with an active old run by this initial fix.

The restore process checks source repository/workflow/run/commit, every payload
SHA256 and an independent build-recipe fingerprint. Runtime recipe functions,
parent recipes, overlays, source checkout pins and toolchain/build environments
must match. A differing build fingerprint refuses reuse rather than silently
compiling or applying new kernel edits to an old binary.

Both original build commit/run and verifier commit/run are recorded. The kernel
release keeps the ORIGINAL build short SHA and `-by-Tim0320`, even if a later
commit only corrects the verifier. Boot bytes must remain identical to the
checkpoint. Missing/expired checkpoints are explicit failures, never fake PASS.

## Local validation and limits

10 identity-parser tests, 14 checkpoint/restore tests and the existing 11
flash-contract tests pass. Full inherited preflight and the 505-input battery
host test pass. Python syntax, embedded Python and YAML pipeline structure
checks pass. Tests include template-before-banner, conflicting/wrong identity,
archive tampering, traversal, symlinks, secret exclusion, source identity,
verifier-only reuse and refusal after kernel/source-pin changes.

The test fixtures copy ONLY scripts/overlays/workflows, never stock LFS images.
A local actionlint installation could not be downloaded because network/DNS was
unavailable; do not report actionlint as passed. The first complete hosted
build/checkpoint/independent verification remains to be read back from CI.
No architecture can recover unuploaded bytes after an abrupt runner loss or
expired/deleted artifacts. These changes specifically decouple ordinary
verification failures from artifact retention and recompilation.

Keep the existing hourly Lisa automation `6ab2be5b63348191a2883afc462945b7`.
The observer watches both build and verification on its existing 2/2/5-minute
pattern; it is not a self-modifying repair agent. Read current CI before acting.
