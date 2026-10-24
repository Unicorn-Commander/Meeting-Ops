# Contributing

Thanks for improving Meeting-Ops. Keep changes focused, preserve organization and authorization boundaries, and include a test or documentation update when behavior changes.

## Local workflow

Use the Docker development compose for an end-to-end source checkout:

```bash
docker compose -f docker-compose.dev.yml up --build
```

For the self-host path, use `./install-meeting-ops.sh` and keep the generated `.env` untracked.

## Checks

Run the relevant checks before opening a pull request:

```bash
make test
(cd frontend && npm run lint)
(cd frontend && npm run build)
(cd backend && python3 -m pytest tests/ -v)
```

Do not include credentials, customer data, private deployment details, or generated recordings in a change. Explain the user-visible behavior and verification performed in the pull request description.
