# Meeting-Ops

Meeting-Ops is a self-hostable meeting recorder and conversation-intelligence
app. The browser handles live, on-device work; the server stores meetings and
provides the API, agent tools, and optional completion providers.

## Quick start

The following is the complete public install path. It needs a Linux host with
Docker Engine, Docker Compose v2, `curl`, and `openssl`. No GPU, model download,
Node.js, Python, external identity provider, or suite network is required.

```bash
git clone https://github.com/Unicorn-Commander/meeting-ops-community.git
cd meeting-ops-community
./install-meeting-ops.sh
```

The installer creates a local-only Postgres + Redis + API + web stack, runs the
schema bootstrap, and generates a unique admin username and password. It prints
those credentials once; store them in a password manager. The generated
`.env` remains on the host with mode `0600` and must never be committed.
The self-host identity is local email/password; an external identity provider
is not part of this quickstart.

Open the UI at <http://127.0.0.1:7777>. The API health check is:

```bash
curl -fsS http://127.0.0.1:9050/health
```

The API docs are at <http://127.0.0.1:9050/docs>. The default ports are bound
to loopback: API `9050`, web `7777`, Postgres `5434`, and Redis `6381`.

## Agent credential

After signing in with the generated admin at the web UI, or after obtaining an
app access token from the password-login endpoint, create a user PAT. The PAT
plaintext is returned only at creation time and begins with `mops_pat_`.

```bash
# Use the generated values printed by ./install-meeting-ops.sh.
ADMIN_USERNAME='generated-admin-username'
ADMIN_PASSWORD='generated-admin-password'

curl -fsS -X POST http://127.0.0.1:9050/api/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "username=${ADMIN_USERNAME}" \
  --data-urlencode "password=${ADMIN_PASSWORD}"
```

Copy the returned `access_token` into `ADMIN_ACCESS_TOKEN`, then mint a PAT:

```bash
ADMIN_ACCESS_TOKEN='access-token-from-login-response'

curl -fsS -X POST http://127.0.0.1:9050/api/auth/pats \
  -H "Authorization: Bearer ${ADMIN_ACCESS_TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"name":"my-agent","scope":"user","expires_in_days":90}'
```

Use the returned `plaintext` as the agent's bearer credential. Hosted MCP is
available at `http://127.0.0.1:9050/mcp` and requires that PAT on every
request. Create or rotate credentials from the local admin's app session and
store each plaintext value only in the agent's secret store.

## Optional providers

The default install deliberately does not download a large model or start a
GPU service. Browser recording and the authenticated app can run without those
providers. To enable server-side summaries, transcription, embeddings, or
speech output, configure the relevant provider environment variables in the
local `.env` by name, such as `LITELLM_API_BASE`, `LITELLM_API_KEY`,
`LLM_MODEL_FAST`, `LLM_MODEL_QUALITY`, `INFINITY_ENDPOINT`,
`PARAKEET_SERVER_URL`, `SPEAKER_SVC_URL`, or `KOKORO_ENDPOINT`, then restart:

```bash
docker compose --env-file .env -f docker-compose.selfhost.yml up -d
```

No provider credential belongs in Git. The self-host compose has no external
Docker network and publishes no service beyond loopback.

## Stop and inspect

```bash
docker compose --env-file .env -f docker-compose.selfhost.yml ps
docker compose --env-file .env -f docker-compose.selfhost.yml logs backend
docker compose --env-file .env -f docker-compose.selfhost.yml down
```

`down` preserves the named database and Redis volumes. Do not use `down -v`
unless you intentionally want to erase the local installation.

## License

Meeting-Ops is licensed under the GNU Affero General Public License, version 3.
See [LICENSE](./LICENSE).
