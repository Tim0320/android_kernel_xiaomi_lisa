#!/usr/bin/env python3
from pathlib import Path
import argparse,json,subprocess,tempfile
from candidate_0061_batch_a_manual import MANUAL, adapt

BASE="upstream-v5.4.289"
TARGET="upstream-v5.4.292"

def git(root,*args,check=True):
    return subprocess.run(["git","-C",str(root),*args],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=check)

def blob(root,ref,path):
    p=git(root,"show",f"{ref}:{path}",check=False)
    return None if p.returncode else p.stdout

def work(root,path):
    p=root/path
    return p.read_bytes() if p.is_file() else None

def write(root,path,data):
    p=root/path
    if data is None:
        if p.exists(): p.unlink()
        return
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(data)

def merge3(ours,base,theirs):
    with tempfile.TemporaryDirectory() as d:
        d=Path(d)
        for n,x in (("o",ours),("b",base),("t",theirs)):
            (d/n).write_bytes(x)
        p=subprocess.run(["git","merge-file","-p",str(d/"o"),str(d/"b"),str(d/"t")],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if p.returncode:
            raise RuntimeError("three-way merge conflict")
        return p.stdout

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",type=Path,required=True)
    ap.add_argument("--report",type=Path,default=Path("candidate-0061-batch-a-apply.json"))
    a=ap.parse_args()
    root=a.source.resolve()
    paths=git(root,"diff","--name-only","--no-renames",BASE,TARGET).stdout.decode().splitlines()
    stats={"DIRECT":0,"AUTO_3WAY":0,"ALREADY_PRESENT":0,"ADAPT":0,"NOT_APPLICABLE":0}
    rows=[]
    for path in paths:
        b,t,o=blob(root,BASE,path),blob(root,TARGET,path),work(root,path)
        manual=MANUAL.get(path)
        if manual:
            stats[manual]+=1
            rows.append({"path":path,"class":manual})
            continue
        if o==t:
            cls="ALREADY_PRESENT"
        elif o==b:
            write(root,path,t); cls="DIRECT"
        else:
            if None in (o,b,t):
                raise RuntimeError(path+": non-manual add/delete conflict")
            write(root,path,merge3(o,b,t)); cls="AUTO_3WAY"
        stats[cls]+=1
        rows.append({"path":path,"class":cls})
    for path,cls in MANUAL.items():
        if cls=="ADAPT": adapt(root,path,TARGET,lambda p: blob(root,TARGET,p))
    if "SUBLEVEL = 292" not in (root/"Makefile").read_text():
        raise RuntimeError("Makefile did not reach 5.4.292")
    p=git(root,"diff","--check",check=False)
    if p.returncode:
        raise RuntimeError("git diff --check failed\n"+p.stdout.decode()+p.stderr.decode())
    result={"candidate":"0061","batch":"A","from":"5.4.289","to":"5.4.292",
      "classification":"STABLE_ONLY","counts":stats,"files":rows,
      "candidate0059_reference_untouched":True}
    a.report.write_text(json.dumps(result,indent=2)+"\n")
    print("C0061_BATCH_A_APPLY=PASS")
    print(json.dumps(stats,sort_keys=True))

if __name__=="__main__":
    main()
