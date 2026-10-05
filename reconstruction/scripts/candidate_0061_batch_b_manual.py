from pathlib import Path

# STABLE_ONLY Batch B (5.4.292 -> 5.4.296) semantic adapters.
# Keep downstream Qualcomm/Xiaomi structure and apply only reviewed stable semantics.
MANUAL={
    "Makefile":"ADAPT",
    "arch/arm64/include/asm/cputype.h":"ADAPT",
}

def once(s,old,new,label):
    n=s.count(old)
    if n!=1:
        raise RuntimeError(f"{label}: anchor count={n}")
    return s.replace(old,new,1)

def adapt(root:Path,path:str,target_ref:str,target_blob):
    p=root/path
    s=p.read_text()
    if path=="Makefile":
        # The downstream top-level Makefile carries vendor kbuild changes, so replacing
        # it with upstream would be incorrect. Stable Batch B only needs the release
        # identity advanced after Batch A has already established SUBLEVEL 292.
        s=once(s,"SUBLEVEL = 292\n","SUBLEVEL = 296\n","Batch B Makefile SUBLEVEL")
    elif path=="arch/arm64/include/asm/cputype.h":
        stable=target_blob(path).decode()
        additions=[line for line in stable.splitlines() if "CORTEX_A76AE" in line]
        if len(additions)!=2:
            raise RuntimeError("unexpected stable cputype delta")
        s=once(s,
            "#define ARM_CPU_PART_CORTEX_A77\t\t0xD0D\n",
            "#define ARM_CPU_PART_CORTEX_A77\t\t0xD0D\n"+additions[0]+"\n",
            "Batch B cputype part")
        s=once(s,
            "#define MIDR_CORTEX_A77\tMIDR_CPU_MODEL(ARM_CPU_IMP_ARM, ARM_CPU_PART_CORTEX_A77)\n",
            "#define MIDR_CORTEX_A77\tMIDR_CPU_MODEL(ARM_CPU_IMP_ARM, ARM_CPU_PART_CORTEX_A77)\n"+additions[1]+"\n",
            "Batch B cputype MIDR")
    else:
        raise RuntimeError("unreviewed Batch B semantic conflict: "+path)
    p.write_text(s)
