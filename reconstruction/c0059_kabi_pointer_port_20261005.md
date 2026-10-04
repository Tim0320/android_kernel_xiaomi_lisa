# Candidate0059 KABI-safe package-runtime plan

The stock-era Xiaomi `struct package_runtime_info` cannot be embedded directly into a single Lisa Android KABI reserve. It contains a lock, list head, multiple history arrays, cpumask and MIGT accounting fields, so treating one 64-bit reserve as the full object would be invalid.

Candidate0059 therefore uses a **pointer-backed external-state strategy** for the Android16 performance repair:

- `task_struct`: consume only `ANDROID_KABI_RESERVE(8)` as a `struct package_runtime_info *pkg_rt` pointer.
- `user_struct`: consume only `ANDROID_KABI_RESERVE(2)` as a `struct package_runtime_info *pkg_rt` pointer.
- The real `package_runtime_info` objects are dynamically allocated outside the frozen structures.
- Donor direct accesses such as `p->pkg` and `user->pkg` must be converted to accessors. Do not append the large donor struct to Lisa structures.
- Allocation and cleanup must be wired through every fork/credential/user lifetime failure path before a source patch can be accepted.

Why this preserves the intended ABI boundary:
- Lisa is arm64, so the pointer is 8 bytes.
- Android KABI reserve entries are `u64`.
- `ANDROID_KABI_USE` preserves the original reserve declaration to GENKSYMS and statically rejects replacements that exceed the reserve size/alignment.
- Current Candidate0059 baseline has not consumed task reserve 8 or user reserve 2 elsewhere.

This is still a source-port plan, not runtime proof. The first source patch must compile with CFI/MODVERSIONS intact and must pass the existing module/display/ownership gates before any device test.
