"""Bounded worker execution; on Windows stop the exact spawned process tree."""
from pathlib import Path
import os,subprocess,sys
def run_worker(root,timeout=150):
    root=Path(root)
    command=[sys.executable,'-B',str(root/'worker.py')]
    process=subprocess.Popen(command,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        stdout,stderr=process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(command,process.returncode,stdout,stderr)
    except subprocess.TimeoutExpired:
        if os.name=='nt':
            # venv's redirector can have a child interpreter; killing only the
            # redirector would leave native optimization running in the child.
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=10)
        else:process.kill()
        try:process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill();process.communicate(timeout=10)
        raise subprocess.TimeoutExpired(command,timeout) from None
