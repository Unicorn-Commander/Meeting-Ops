#!/usr/bin/env bash
# Build + publish the Meeting-Ops OSS snapshot.
# Assumes sanitize-oss.sh has already PASSED against $BUILD.
set -uo pipefail

BUILD="${1:?usage: publish-oss.sh <path-to-sanitized-clone>}"
cd "$BUILD" || exit 2

SRC=$(git log -1 --format=%H)

# The authoritative list is what git tracked in the sanitized tree.
# NOTE: a fresh `git init` + `git add -A` re-applies .gitignore and silently drops
# force-added files (it ate backend/models/*.py and alembic.ini on the first run).
# Always re-add from this explicit list with -f.
git add -A >/dev/null 2>&1
git ls-files > /tmp/tracked.txt
EXPECT=$(wc -l < /tmp/tracked.txt | tr -d ' ')
echo "authoritative file count: $EXPECT"

rm -rf .git && git init -q -b main
tr '\n' '\0' < /tmp/tracked.txt | xargs -0 git add -f
GOT=$(git ls-files | wc -l | tr -d ' ')
echo "staged: $GOT"
[ "$GOT" != "$EXPECT" ] && { echo "COUNT MISMATCH ($GOT != $EXPECT) — aborting"; exit 1; }

for f in backend/alembic.ini backend/models/__init__.py backend/models/settings.py; do
  git ls-files --error-unmatch "$f" >/dev/null 2>&1 || { echo "MISSING CRITICAL FILE: $f — aborting"; exit 1; }
done
echo "critical-file check: ok"

git -c user.name="Magic Unicorn Unconventional Technology & Stuff Inc" \
    -c user.email="opensource@unicorncommander.ai" commit -q -F - <<EOF
Meeting-Ops — initial public release (v3.58.0)

Browser-first conversation intelligence: live transcription and summarization run
in the user's browser on small on-device models; a single server pass at meeting
end produces the high-quality transcript, diarization, summary, and search index.
No third-party AI, no per-audio-minute meter.

This is the full product source, not a reduced edition. The Free / Pro / Enterprise
tiers are runtime entitlements enforced server-side, not separate codebases.

Licensed AGPL-3.0-or-later. A commercial license is available for organizations
that cannot meet the network-copyleft terms — licensing@unicorncommander.ai.

Sanitized snapshot of the private development repo at $SRC.
Omitted from the public tree:
  - deploy/  host-specific compose, Traefik, and object-storage configs for our own
             machines. Not part of the product; start from docker-compose.prod.yml.
  - internal network addresses, deploy paths, and ssh targets, replaced with the
    in-cluster service names that are the correct defaults anyway
  - unreferenced dev-era screen captures

Produced by a sanitize gate that fails closed: it verifies the absence of internal
addresses, deploy paths, ssh targets, customer-data screenshots, known secret
formats, and unretracted performance claims before a snapshot may be published.
The gate is mutation-tested — each check is proven to fail on an injected leak.

This history is append-only. Later releases add commits; they never rewrite these,
because a force-push to GitHub leaves the old commits fetchable by SHA forever.
EOF
echo "commit: $(git log -1 --format='%h %s')"
