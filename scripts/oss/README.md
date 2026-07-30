# OSS release gate

`Meeting-Ops-OSS` (Forgejo, mirrored to GitHub) is the **full product source** under
AGPL-3.0. It is *generated* from this private repo — never edited directly.

```bash
git clone <this repo> /tmp/ossbuild
scripts/oss/sanitize-oss.sh /tmp/ossbuild     # rewrites in place, then VERIFIES
scripts/oss/publish-oss.sh  /tmp/ossbuild     # squashes to one commit
cd /tmp/ossbuild && git push origin main && git push github main
```

## Rules

1. **The gate fails closed.** `sanitize-oss.sh` exits non-zero if any internal address,
   deploy path, ssh target, customer-data screenshot, known secret format, or unretracted
   performance claim survives. A non-zero exit means *do not publish*.

2. **The OSS history is append-only.** Later releases add commits. Never force-push to
   GitHub: force-pushed commits stay fetchable by SHA forever, so a sanitize mistake
   published once cannot be taken back. If a bad snapshot ever reaches GitHub, the only
   real remedy is deleting and recreating the repository.

3. **Verify the published artifact, not your working tree.** Clone from GitHub and re-run
   the checks. The first release passed locally and still shipped stale claims.

4. **Never `git add -A` when rebuilding history.** It re-applies `.gitignore` and silently
   drops force-added files — it ate `backend/models/*.py` and `backend/alembic.ini` on the
   first attempt, which would have shipped a repo that could not run migrations.
   `publish-oss.sh` re-adds from an explicit list with `-f` and aborts on a count mismatch.

5. **A green gate proves nothing until it has failed.** The checks are mutation-tested:
   inject a fake tailnet IP, ssh target, foreign home path, private key, and AWS key, and
   confirm each one trips the gate. Re-run that after changing any check.

## What is deliberately omitted from the public tree

- `deploy/` — host-specific compose, Traefik, and object-storage configs for our machines.
  Not part of the product. Self-hosters start from `docker-compose.prod.yml`.
- Internal addresses / deploy paths / ssh targets, rewritten to the in-cluster service
  names that are the correct defaults anyway.
- Unreferenced dev-era screen captures and committed test artifacts.
