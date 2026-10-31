#!/usr/bin/env bash
# Stage the proposed public `thrubound` repository into an EMPTY directory (no git, no network).
#   bash release/stage_public_repo.sh <empty-target-dir>
# Copies only the ThruBound paths listed in LICENSING.md as Apache-2.0 plus the vendored Thru C SDK.
# Legacy AgentVault EVM code (MIT), third-party EVM vendor code (Apache/MIT/LGPL) and git history
# are NOT included. This script publishes nothing; creating and pushing a repository is a separate,
# owner-approved step.
set -euo pipefail
SRC=$(cd "$(dirname "$0")/.." && pwd); DST=${1:?target directory}
mkdir -p "$DST"; [ -z "$(ls -A "$DST")" ] || { echo "target not empty: $DST"; exit 1; }
cd "$SRC"
INCLUDE=(README.md LICENSE NOTICE LICENSING.md CONTRIBUTING.md SECURITY.md CHANGELOG.md .env.example
         thru examples/subscription-payer docs m2/thru-baseline m2/thru-phase1 m2/thru-phase3
         m2/thrubound-ce1 m2/thrubound-p2 m2/thrubound-p3 m2/thrubound-p5 m2/thrubound-p6
         m2/thrubound-phase6 m2/thrubound-phase7 m2/thrubound-p8 release .github)
EXCLUDE='^docs/legacy/|^docs/PUBLIC_RELEASE_CHECKLIST\.md$'   # the checklist is an internal owner document
git ls-files --cached --others --exclude-standard -- "${INCLUDE[@]}" | grep -Ev "$EXCLUDE" > "$DST/.filelist"
while IFS= read -r f; do mkdir -p "$DST/$(dirname "$f")"; cp -p "$f" "$DST/$f"; done < "$DST/.filelist"
cat > "$DST/.gitignore" <<'GI'
node_modules/
__pycache__/
*.pyc
.env
.env.*
!.env.example
thru/build/
thru/program/build/
thru/sdk/dist/
examples/*/out/
*.pem
*.key
id_rsa*
**/.thru/
*.keypair.json
.DS_Store
Thumbs.db
.vscode/
.idea/
GI
# Owner decision 2026-10-31: hide personal data and sandbox internals in the PUBLIC copy only.
python3 - "$DST" <<'PY'
import re, sys, pathlib
d = pathlib.Path(sys.argv[1])
for p in d.rglob("*.md"):
    s = p.read_text(encoding="utf-8"); t = re.sub(r"C:\\Users\\(?!<user>)[A-Za-z0-9._-]+\\", lambda m: "C:\\Users\\<user>\\", s)
    t = re.sub(r"\| GitHub account `exelance25` \(inferred from[^|]*\| [^|]*?none for this project;", "| The owner's GitHub account | no repository for this project;", t)
    if t != s: p.write_text(t, encoding="utf-8")
nc = d / "m2/thrubound-phase7/net-cloud.txt"
if nc.exists():
    s = nc.read_text(); head, _, js = s.partition("## proxy status endpoint\n")
    ents = re.findall(r'"ts": "([^"]+)",\s*"kind": "([^"]+)",\s*"detail": "([^"]*)",\s*"host": "([^"]+)"', js)
    lines = [f'{ts}  {k}  host={h}  detail="{det}"' for ts, k, det, h in ents if "thru.org" in h]
    nc.write_text(head + "## proxy status endpoint (excerpt: relay failures for thru.org hosts only; the rest of the sandbox proxy configuration was removed for publication)\n" + "\n".join(lines) + "\n")
PY
grep -rIlE "C:.Users.[A-Za-z0-9]|exelance25/axora|anthropic\.com|__agentproxy" "$DST" --exclude=.filelist --exclude=stage_public_repo.sh && { echo "personal or sandbox data left in the public copy"; exit 1; }
echo "staged $(wc -l < "$DST/.filelist") files into $DST (file list: $DST/.filelist)"
