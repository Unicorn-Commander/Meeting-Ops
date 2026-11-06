# Meeting-Ops deployment surface

These notes document the public-surface guardrails without modifying any
deployment compose file.

## Native-OIDC public router

The `meet-prod.rule` label in
`deploy/unicorncommander/docker-compose.unicorncommander.yml` must not publish
Prometheus. The exact label change is:

```text
- "traefik.http.routers.meet-prod.rule=Host(`meeting-ops.unicorncommander.ai`) && (PathPrefix(`/api`) || PathPrefix(`/ws`) || PathPrefix(`/docs`) || PathPrefix(`/redoc`) || PathPrefix(`/openapi.json`) || PathPrefix(`/health`) || PathPrefix(`/metrics`) || PathPrefix(`/mcp`))"
+ "traefik.http.routers.meet-prod.rule=Host(`meeting-ops.unicorncommander.ai`) && (PathPrefix(`/api`) || PathPrefix(`/ws`) || PathPrefix(`/docs`) || PathPrefix(`/redoc`) || PathPrefix(`/openapi.json`) || PathPrefix(`/health`) || PathPrefix(`/mcp`))"
```

That removal is already present on this branch. The rule also carries
``PathPrefix(`/.well-known/oauth-protected-resource`)`` so the hosted MCP OAuth
door's RFC 9728 metadata (both `/.well-known/oauth-protected-resource` and
`/.well-known/oauth-protected-resource/mcp`) reaches the backend instead of the
SPA; `backend/tests/test_public_metrics_route.py` pins both facts. Do not add a broad backend
catch-all that would put `/metrics` back on the native-OIDC host. The backend
mount remains available for internal scraping and can additionally require a
bearer token when `METRICS_TOKEN` is configured.

## API documentation

`MEETING_OPS_PUBLIC_DOCS` defaults off. Set `MEETING_OPS_PUBLIC_DOCS=1` only in
the development compose environment when interactive `/docs`, `/redoc`, and
`/openapi.json` are wanted. Leave it unset in production rings.
