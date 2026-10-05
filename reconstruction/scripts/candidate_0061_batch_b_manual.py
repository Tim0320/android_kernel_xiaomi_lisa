from pathlib import Path

# STABLE_ONLY Batch B (5.4.292 -> 5.4.296) semantic adapters.
# Keep downstream Qualcomm/Xiaomi structure and apply only reviewed stable semantics.
MANUAL={
    "Makefile":"ADAPT",
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
    else:
        raise RuntimeError("unreviewed Batch B semantic conflict: "+path)
    p.write_text(s)
