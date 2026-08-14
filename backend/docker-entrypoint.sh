#!/bin/sh
# Backend container entrypoint.
#
# Alembic is the canonical source of schema truth. Run migrations BEFORE
# starting uvicorn so the app never serves traffic against a schema that
# was raced ahead by SQLAlchemy's Base.metadata.create_all (which silently
# creates tables WITHOUT the FK / index / default additions a real
# alembic revision would apply). If alembic fails, exit non-zero so the
# container's restart policy surfaces the problem instead of silently
# running on a partial schema.
set -e

echo "[entrypoint] Running alembic upgrade head..."
alembic upgrade head || { echo "[entrypoint] Alembic migration failed"; exit 1; }
echo "[entrypoint] Alembic upgrade head complete"

echo "[entrypoint] Starting uvicorn..."
# Trust the reverse proxy's X-Forwarded-* headers.
#
# uvicorn enables proxy-header parsing by default, but only honours it from
# --forwarded-allow-ips, which defaults to 127.0.0.1. Behind Traefik the peer
# is a Docker-network address, so the headers were being ignored and every
# request looked like plain HTTP to Starlette. The visible symptom was that
# the canonical-slash redirect on the hosted MCP mount answered
#   POST https://<host>/mcp   ->  307  http://<host>/mcp/
# i.e. an HTTPS request redirected to HTTP. HTTP clients drop the
# Authorization header across a scheme downgrade, so a customer who
# configured the MCP URL without the trailing slash saw an unauthenticated
# failure — and any client that did follow it would have put their PAT on a
# cleartext URL.
#
# The container port is not published to the host (see the compose file), so
# only the proxy and sibling containers can reach it; "*" is the correct
# default here. Override with FORWARDED_ALLOW_IPS for a deployment that
# exposes the port directly.
exec python -m uvicorn main:app --host 0.0.0.0 --port 9050 \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}"
