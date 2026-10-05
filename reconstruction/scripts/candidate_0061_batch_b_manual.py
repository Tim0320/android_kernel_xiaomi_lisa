from pathlib import Path

# Batch B (5.4.292 -> 5.4.296) starts with no pre-approved semantic adapters.
# The first CI pass is intentionally strict: any non-clean downstream overlap must
# stop and be classified before an adapter is added.
MANUAL={}

def adapt(root:Path,path:str,target_ref:str,target_blob):
    raise RuntimeError("unreviewed Batch B semantic conflict: "+path)
