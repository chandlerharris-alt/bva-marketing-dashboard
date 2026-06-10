"""Throwaway: extract inline <script> blocks from index.html and node --check each."""
import re, subprocess, tempfile, sys
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
html = (Path(__file__).resolve().parent.parent / "dashboard" / "index.html").read_text(encoding="utf-8")
blocks = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.S | re.I)
print(f"{len(blocks)} inline script block(s)")
ok = True
for i, b in enumerate(blocks):
    if len(b.strip()) < 5:
        print(f"block {i}: (trivial, skipped)")
        continue
    f = Path(tempfile.gettempdir()) / f"_jscheck_{i}.js"
    f.write_text(b, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    if r.returncode == 0:
        print(f"block {i} ({len(b):,} chars): OK")
    else:
        ok = False
        print(f"block {i} ({len(b):,} chars): SYNTAX ERROR")
        print(r.stderr[:1500])
print("== ALL BLOCKS OK ==" if ok else "== SYNTAX ERRORS FOUND ==")
