"""Explicit opt-in copy adapter; never runs during build."""
import os, shutil
from pathlib import Path
if __name__=='__main__':
    target=os.environ.get('ICLOUD_PUBLISH_DIR')
    if not target: raise SystemExit('Set ICLOUD_PUBLISH_DIR explicitly')
    shutil.copytree(Path(__file__).resolve().parents[2]/'apps/web/build',target,dirs_exist_ok=True)
