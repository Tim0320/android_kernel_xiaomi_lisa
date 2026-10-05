#!/usr/bin/env python3
from pathlib import Path
import argparse, json, subprocess, tempfile

BASE="upstream-v5.4.289"
TARGET="upstream-v5.4.292"

def run(root,*args,check=True):
    return subprocess.run(["git","-C",str(root),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=check)

def blob(root,ref,path):
    p=run(root,"show",f"{ref}:{path}",check=False)
    return None if p.returncode else p.stdout

def work(root,path):
    p=root/path
    return p.read_bytes() if p.is_file() else None

def mergeable(ours,base,theirs):
    if None in (ours,base,theirs) or any(b"\0" in x[:8192] for x in (ours,base,theirs)):
        return False
    with tempfile.TemporaryDirectory() as d:
        d=Path(d)
        for n,x in (("o",ours),("b",base),("t",theirs)): (d/n).write_bytes(x)
        p=subprocess.run(["git","merge-file","-p",str(d/"o"),str(d/"b"),str(d/"t")],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return p.returncode==0

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kernel",type=Path,required=True)
    ap.add_argument("--out",type=Path,default=Path("candidate-0061-batch-a-review.json"))
    a=ap.parse_args(); root=a.kernel
    paths=run(root,"diff","--name-only","--no-renames",BASE,TARGET).stdout.decode().splitlines()
    rows=[]
    for path in paths:
        b,t,o=blob(root,BASE,path),blob(root,TARGET,path),work(root,path)
        vendor=o!=b
        if o==t: cls="ALREADY_PRESENT"
        elif not vendor: cls="DIRECT"
        elif mergeable(o,b,t): cls="AUTO_3WAY"
        else: cls="SEMANTIC_REVIEW"
        rows.append({"path":path,"class":cls,"vendor_diverged":vendor})
    result={"candidate":"0061","batch":"A","from":"5.4.289","to":"5.4.292","counts":{},"semantic_review":[]}
    for r in rows:
        result["counts"][r["class"]]=result["counts"].get(r["class"],0)+1
        if r["class"]=="SEMANTIC_REVIEW": result["semantic_review"].append(r["path"])
    result["files"]=rows
    a.out.write_text(json.dumps(result,indent=2)+"\n")
    print("C0061_BATCH_A_REVIEW=PASS")
    print("semantic_review="+str(len(result["semantic_review"])))
    return 0
if __name__=="__main__": raise SystemExit(main())
