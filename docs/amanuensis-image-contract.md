# Amanuensis image contract — ready for an approved cutover

Meeting-Ops remains the meeting application; engine implementation and image builds
belong to Unicorn-Amanuensis. `deploy/amanuensis/images.lock.json` pins all four
services to main commit `76a90de7fccfa3bf38e054711107e02e3656c0e1`, published by
Forgejo CI run **2538**. Amanuensis PR **#18** adds the speaker-svc readiness `/health`
(503 until the diarizer is loaded) and `/livez`, ported from Meeting-Ops #43.
Amanuensis PR **#5** includes the live seekable-file media
decode patches. The overrides now remove the superseded batch and speaker
`/app/main.py` binds. Original host files and patches remain available for rollback.

**This PR does not execute a cutover.** Follow the [cutover runbook](amanuensis-cutover.md).
PRODUCTION Meeting-Ops on **centerdeep** also calls midboy1 **:8881/:8895**;
**Aaron must approve the maintenance window** before any service recreation.

## Remote placement

Compose >=2.24.4 is required: `!reset` removes legacy builds and `!override`
replaces mount lists. Append each override to the **live** compose chain.

| Placement | Override | Compose services |
|---|---|---|
| midboy1 `/home/muut/uc-meeting-ops-deploy/midboy1/docker-compose.4070.yml` | `deploy/midboy1/docker-compose.amanuensis.yml` | `parakeet`, `parakeet-stream` |
| midboy2 `/home/muut/uc-meeting-ops-deploy/midboy2/docker-compose.p40.yml` | `deploy/midboy2/docker-compose.amanuensis.yml` | `speaker-svc` |
| midboy1 `/home/muut/uc-meeting-ops-deploy/midboy1/parakeet-openai-shim/docker-compose.shim.yml` | `deploy/amanuensis/shim/docker-compose.amanuensis.yml` | `parakeet-openai-shim` |
| bigboy emergency, profile-gated speaker | `deploy/bigboy/docker-compose.amanuensis.yml` | `meet-speaker-svc`; outside this cutover |

The repository's midboy1 base contains VibeVoice, not the live 4070 services.
The cutover script discovers each live project's compose chain from container labels.
It renders and checks the complete override, then stages a service-specific override
so each recreation applies only that service's change. Voice-parakeet and its shim
remain outside the cutover. No host compose files or runtime credentials are committed.

Read-only live compose rendering on 2026-09-15 verified all other mounts,
environment values, GPU placement, ports, volumes and unrelated services survive
unchanged. Runtime checks repeat that validation in the window and reject drift.
The two replaced mount lists preserve `parakeet_models:/models` on midboy1 and
`/home/muut/speaker-models:/models` on midboy2. If live mounts change, revise and
review the override; the script will refuse an unexpected difference.

Batch explicitly sets `PARAKEET_MODEL_PRECISION=fp32`. The live patch ignored its
configured fp16 value, so fp32 preserves effective behavior. The benchmark on the
3090/6000 matched fp32 transcripts within one character at fp16, but **fp16 remains
a separate change requiring approval**. Stream retains its live fp16 setting.
Speaker retains `SPEAKER_GPU_ACQUIRE_TIMEOUT=1500` (the new image accepts that
legacy alias), `CHUNK_THRESHOLD_SECONDS=28800`, `CHUNK_WINDOW_SECONDS=3600`, and
`CHUNK_STITCH_THRESHOLD=0.50`.

## Bundled engine (appliance / OSS placement)

`deploy/bundled-engine/docker-compose.yml` remains an opt-in `bundled-engine`
profile, sharing the same four commit tags. It publishes no host ports and reserves
no GPUs. The `amanuensis-local` network and model-cache volume keep service DNS
stable. `docker-compose.callers.yml` connects the dev backend and sets
`PARAKEET_SERVER_URL`, `PARAKEET_STREAM_URL`, and `SPEAKER_SVC_URL`. A worker-based
appliance must attach each worker to that network and supply the same URLs.

Validate without contacting a Docker daemon:

```sh
docker compose --env-file /dev/null -f docker-compose.dev.yml \
  -f deploy/bundled-engine/docker-compose.yml \
  -f deploy/bundled-engine/docker-compose.callers.yml \
  --profile bundled-engine config --quiet
python3 ci/test_amanuensis_contract.py
python3 ci/test_amanuensis_cutover.py
bash -n ci/test_amanuensis_images.sh deploy/cutover/amanuensis-images.sh
```

This is an engine placement, not a production app installer. CPU/1070 throughput
and offline inference remain unmeasured. Seed models and satisfy model access and
license requirements before advertising offline readiness. Model credentials stay
in runtime environment. GPU allocation needs a separately reviewed hardware profile.

## CI

Forgejo renders compose contracts, checks pins, fp32 and patch-mount removal, and
runs offline cutover failure tests. Existing container contract tests pull the four
commit tags and run batch syntax, speaker synthetic tests, stream Opus tests and
shim route import checks. These CPU checks do not establish speech accuracy or
live GPU readiness; the approved cutover includes model health and synthetic probes.
The operator's preflight records each pulled **RepoDigest** and image ID, and
recreation uses `--pull never` after checking that the tag still resolves to that ID.
