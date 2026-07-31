#!/usr/bin/env bash
# Meeting-Ops OSS sanitize gate.
#
#   private (Forgejo UC-Meeting-Ops)  --sanitize-->  Meeting-Ops-OSS  --mirror-->  GitHub
#
# Run against a clean clone of the private repo. Rewrites the working tree in place,
# then VERIFIES. Exits non-zero if any known-bad value survives, so a partial scrub
# can never be mistaken for a clean one.
#
# Scrubs by VALUE, not by pattern -- a blind `sed s/pattern/x/` both breaks config and
# leaves the real secret behind (learned the hard way).
set -uo pipefail

ROOT="${1:?usage: sanitize-oss.sh <path-to-clone>}"
cd "$ROOT" || exit 2

echo "== Meeting-Ops OSS sanitize gate =="
echo "tree: $ROOT"
echo "head: $(git log -1 --format='%h %s')"
echo

# ---------------------------------------------------------------- 1. drop paths
# Our own infrastructure, not the product: host-specific compose/traefik/garage
# configs pinned to bigboy / midboy1 / the UC VPS.
DROP_PATHS=(
  deploy
  # Release tooling stays private: the scrub map necessarily contains every literal it
  # removes, so publishing it re-leaks exactly what it exists to remove.
  scripts/oss
)
# Unreferenced dev-era captures; not audited for customer data, and nothing links them.
DROP_FILES=(
  Frontend_GUI.png
  screenshot.png
  frontend_session_manager_verification.png
  backend/live_transcription_verification.png
)

echo "-- dropping internal-only paths"
for p in "${DROP_PATHS[@]}"; do
  [ -e "$p" ] && { git rm -rq --cached "$p" 2>/dev/null; rm -rf "$p"; echo "   dropped dir  $p"; }
done
for f in "${DROP_FILES[@]}"; do
  [ -e "$f" ] && { git rm -q --cached "$f" 2>/dev/null; rm -f "$f"; echo "   dropped file $f"; }
done

# ---------------------------------------------------------------- 2. value map
# Tailnet IPs -> the in-cluster service name that is the CORRECT default anyway.
# (Hardcoding a tailnet IP as a code default was a latent bug, not just a leak.)
python3 - <<'PY'
import pathlib, subprocess, re

# host:port -> in-cluster DNS name. Order matters: longest/most specific first.
HOSTPORT = {
    "100.66.42.57:8881":   "meet-parakeet-svc:8881",
    "100.66.42.57:8889":   "meet-speaker-svc:8889",
    "100.66.42.57:8890":   "meet-speaker-svc:8890",
    "100.66.42.57:8895":   "meet-parakeet-stream-svc:8895",
    "100.66.42.57:8896":   "meet-sortformer-svc:8896",
    "100.66.42.57:7997":   "infinity:7997",
    "100.66.42.57:8088":   "llm-gateway:8088",
    "100.121.80.175:8881": "meet-parakeet-svc:8881",
    "100.121.80.175:8088": "llm-gateway:8088",
    "100.121.80.175:8087": "llm-gateway:8087",
    "100.126.207.157:8088":"llm-gateway:8088",
    "100.121.80.220:4000": "litellm:4000",
    "100.79.41.137:8084":  "ops-center:8084",
    "100.79.41.137:4000":  "litellm:4000",
}
# bare IPs (no port) -> generic placeholder
BARE = {
    "100.66.42.57":    "<gpu-node>",
    "100.121.80.175":  "<gpu-node>",
    "100.121.80.220":  "<llm-gateway-host>",
    "100.126.207.157": "<gpu-node>",
    "100.79.41.137":   "<ops-center-host>",
    "100.87.46.87":    "<vps-host>",
    "192.168.10.68":   "<infinity-host>",
}
# internal paths / ssh targets
PATHS = {
    "/home/ucadmin/Development/Unicorn-Commander-Meeting-Ops": "/srv/meeting-ops",
    "/home/ucadmin/UC-Meeting-Ops":         "/srv/meeting-ops",
    "/home/ucadmin/Meeting-Ops":            "/srv/meeting-ops",
    "/home/ucadmin/Development":            "/srv",
    "/home/ucadmin":                        "/srv",
    "/home/muut/Production/UC-Meeting-Ops": "/srv/meeting-ops",
    "/home/muut/UC-Cloud-production":       "/srv/uc-cloud",
    "/home/muut/backups":                   "/srv/backups",
    "/home/muut":                           "/srv",
    "muut@":                                "deploy@",
    " (magicunicorn on Tailscale, <gpu-node>)": " (private network)",
    "magicunicorn on Tailscale":             "the private network",
    "ssh magicunicorn ":                     "ssh <deploy-host> ",
}

files = subprocess.run(["git","ls-files"],capture_output=True,text=True).stdout.split()
# Never rewrite this script. It previously scrubbed its OWN map into a useless
# {"x": "x"} table, and bash reads a script incrementally so self-modification can
# also break the running shell mid-execution.
SELF = {"scripts/oss/sanitize-oss.sh"}
changed = 0
for fp in files:
    if fp in SELF:
        continue
    p = pathlib.Path(fp)
    if not p.is_file():
        continue
    try:
        t = p.read_text()
    except (UnicodeDecodeError, ValueError):
        continue          # binary
    orig = t
    for k, v in HOSTPORT.items():
        t = t.replace(k, v)
    for k, v in BARE.items():
        t = t.replace(k, v)
    for k, v in PATHS.items():
        t = t.replace(k, v)
    if t != orig:
        p.write_text(t); changed += 1
# drop .gitignore rules for the deploy/ tree we just removed
gi = pathlib.Path(".gitignore")
if gi.exists():
    lines = gi.read_text().splitlines(keepends=True)
    kept = [l for l in lines if not l.lstrip().startswith(("deploy/", "!deploy/"))]
    if len(kept) != len(lines):
        gi.write_text("".join(kept)); print(f"   .gitignore: dropped {len(lines)-len(kept)} dead deploy/ rules")
print(f"   rewrote {changed} files")
PY

# ---------------------------------------------------------------- 3. verify
echo
echo "-- verification (any hit below = FAIL)"
FAIL=0
check() {                 # check <label> <ere>
  local label="$1" pat="$2" hits
  hits=$(git grep -nE "$pat" 2>/dev/null | grep -vE '^(CHANGELOG\.md|docs/)[^:]*:[0-9]+: *#' | head -20)
  if [ -n "$hits" ]; then
    echo "   FAIL: $label"; echo "$hits" | sed 's/^/       /'; FAIL=1
  else
    echo "   ok:   $label"
  fi
}
check "tailnet IPs (100.64-127.x.x.x)" '100\.(6[4-9]|[7-9][0-9]|1[0-1][0-9]|12[0-7])\.[0-9]{1,3}\.[0-9]{1,3}'
check "internal home paths"            '/home/(muut|ubuntu|ucadmin|admin|deploy|aaron)(/|$)'
check "ssh muut@ targets"              'muut@'
if [ -n "$(git ls-files deploy/ 2>/dev/null)" ]; then
  echo "   FAIL: deploy/ tree still tracked"; FAIL=1
else
  echo "   ok:   deploy/ tree removed"
fi
# knowledge-graph.png renders a person's whole cross-meeting neighbourhood, so it
# cannot be captured without including people who have not consented. speakers.png and
# session-summary.png WERE blocked here for the same reason; they were re-captured in
# PR #23 against a meeting whose only two participants both consented, so they are
# allowed again. This rule is a filename guard, not a content check — if any of these
# views is re-captured, review the image before relaxing anything.
check "unconsentable screenshots"     'knowledge-graph\.png'
check "high-signal secret formats"     '(sk-[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)'
check "known CF tokens"                'cfut_[A-Za-z0-9]{20,}'
# Assertive fabricated-performance claims. Correction/historical text is allowed;
# anything still ASSERTING the number is not. Context-aware: correction language often
# sits on a neighbouring line, so a line-only test false-positives.
python3 - <<'PYCHK'
import pathlib, re, subprocess, sys
PAT = re.compile(r"220x|7866x realtime|speedup_factor\W*:\s*220")
OK  = re.compile(r"never measured|hardcoded|none of which is used|previously claimed|"
                 r"did not describe|were removed|~~|not used by this product|LEGACY|unmeasured",
                 re.I)
EXT = (".md", ".py", ".tsx", ".ts", ".yml", ".yaml", ".sh")
files = subprocess.run(["git","ls-files"],capture_output=True,text=True).stdout.split()
bad = []
for fp in files:
    if not (fp.endswith(EXT) or "/.env" in fp or fp.startswith(".env") or ".env" in fp):
        continue
    try: lines = pathlib.Path(fp).read_text().splitlines()
    except Exception: continue
    for i, ln in enumerate(lines):
        if PAT.search(ln):
            ctx = "\n".join(lines[max(0,i-3):i+4])   # +/- 3 lines
            if not OK.search(ctx):
                bad.append(f"{fp}:{i+1}: {ln.strip()[:110]}")
if bad:
    print("   FAIL: fabricated performance claims still asserted")
    for b in bad[:10]: print("       " + b)
    sys.exit(1)
print("   ok:   no asserted fabricated perf claims")
PYCHK
[ $? -ne 0 ] && FAIL=1

echo
if [ "$FAIL" -ne 0 ]; then
  echo "SANITIZE GATE: FAILED — do not publish"; exit 1
fi
echo "SANITIZE GATE: PASSED"
echo "files remaining: $(git ls-files | wc -l | tr -d ' ')"
