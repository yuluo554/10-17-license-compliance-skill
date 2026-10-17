"""One-off desensitization scan (M6). Not part of the release surface."""
import re, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

PATTERNS = [
    ("win-drive", re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\/](?![\/])")),
    ("win-drive-escaped", re.compile(r"[A-Za-z]:\\\\")),
    ("posix-home", re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+")),
    ("gitbash-drive", re.compile(r"(?<![A-Za-z0-9])/(?:[a-z])/(?:Program|Users|home|tmp|mnt)\b")),
    ("unc", re.compile(r"\\[A-Za-z0-9._-]+\[A-Za-z0-9._$-]+")),
    ("token-ish", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,})\b")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("password-assign", re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['\"][^'\"]{4,}['\"]")),
]

def listed():
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"],
                         cwd=str(REPO), capture_output=True, text=True, check=True)
    return [p for p in out.stdout.splitlines() if p.strip()]

def main():
    hits = 0
    for rel in listed():
        p = REPO / rel
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:8000]:
            continue
        text = raw.decode("utf-8", "replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, rx in PATTERNS:
                m = rx.search(line)
                if m:
                    # the handoff files legitimately carry user-side absolute launch commands
                    print("%s:%d\t[%s]\t%s\t%s" % (rel, lineno, name, m.group(0)[:60], line.strip()[:120]))
                    hits += 1
    print("TOTAL HITS: %d" % hits)

main()
