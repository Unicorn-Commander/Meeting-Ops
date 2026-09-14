# Amanuensis image contract — staged, not deployed

Meeting-Ops remains the meeting application. Engine implementation, build history
and published images belong to Unicorn-Amanuensis. `deploy/amanuensis/images.lock.json`
pins the four images built and tested by Amanuensis run 17 / task 2475 at
`0701f41562d48d0ba30beda142f9d1b3de42e3c1`, imported from Meeting-Ops
`8a17d4e8c8473ae2e6fc1b0fccc8fd27023a1f3f`. The image contract changes no application
code, database schema, remote caller URL, model setting, GPU allocation or live service.

## Remote placement

Append only the appropriate **image-only override** to the host's existing compose
chain in an agreed future window. Compose >=2.24.4 is required for `!reset` to remove
legacy build definitions; otherwise `--build` could silently replace a pinned image.
The original compose files remain unchanged and default operation does not opt in.

| Existing placement | Reviewed override | Services affected |
|---|---|---|
| bigboy `deploy/bigboy/docker-compose.bigboy.yml` | `deploy/bigboy/docker-compose.amanuensis.yml` | emergency, profile-gated `meet-speaker-svc` only |
| midboy1 `/home/muut/uc-meeting-ops-deploy/midboy1/docker-compose.4070.yml` | `deploy/midboy1/docker-compose.amanuensis.yml` | `parakeet`, `parakeet-stream` only; voice-parakeet stays untouched |
| midboy2 `/home/muut/uc-meeting-ops-deploy/midboy2/docker-compose.p40.yml` | `deploy/midboy2/docker-compose.amanuensis.yml` | `speaker-svc` |
| shim's existing compose chain | `deploy/amanuensis/shim/docker-compose.amanuensis.yml` | `parakeet-openai-shim` |

The repository's midboy1 base contains VibeVoice, not the live 4070 services. Do not
append the 4070 override to that base. The unicorncommander deployment is a remote
consumer, not an engine host; its caller environment remains unchanged. No production
configuration is activated by this PR. No host compose files were copied into git.

## Live patch discrepancy — must reconcile before cutover

Read-only inspection on 2026-09-14 found host-mounted `/app/main.py` overrides.
An image swap alone does NOT replace these files. The image-only overrides deliberately
preserve them rather than silently removing fixes. Neither a patched nor unpatched
rollout is proven by the synthetic image tests.

| Source | SHA-256 |
|---|---|
| midboy1 `.../midboy1/patches/main.py` | `94edbd465e871edfc3b0b282c608e3e4bdb88686c74469926d78f3524538f3d8` |
| imported `services/parakeet-svc/main.py` | `fafa239ea469364d3f0c362c9d1a9342781d7b45595eaaa342565b24855842b6` |
| midboy2 `.../midboy2/patches/main.py` | `a83f245b095b587a90df8b00cf872a226e7999b5a8af9368ac8714cd83d1bd40` |
| imported `services/speaker-svc/main.py` | `8cbfbbfa8f23184a52c62a951c36e3882b45d35ce339c6e6fa018a94bc7af156` |

The live patches add seekable-file ffmpeg decoding for media containers absent from
the imported sources. Batch also differs in model precision handling; speaker uses
`SPEAKER_GPU_ACQUIRE_TIMEOUT`, while the imported implementation reads
`SPEAKER_GPU_QUEUE_TIMEOUT`. Preserve actual behavior deliberately: reconcile in
Amanuensis with regression tests and republish the lock before removing any bind mount.
This PR does not port runtime changes into Meeting-Ops or claim patch equivalence.

## Bundled engine (appliance / OSS placement)

`deploy/bundled-engine/docker-compose.yml` is an opt-in `bundled-engine` profile.
It runs the same Amanuensis-owned images without publishing host ports or reserving
GPUs. Its own `amanuensis-local` network and model-cache volume keep the service DNS
names stable. `docker-compose.callers.yml` connects the existing dev backend to that
network and sets `PARAKEET_SERVER_URL`, `PARAKEET_STREAM_URL`, `SPEAKER_SVC_URL`.
Other app networks stay attached. A worker-based appliance must attach every worker
to that network and give it the same three URLs; this dev example has no worker.

Validate only (does not contact a Docker daemon or start containers):

```sh
docker compose --env-file /dev/null -f docker-compose.dev.yml \
  -f deploy/bundled-engine/docker-compose.yml \
  -f deploy/bundled-engine/docker-compose.callers.yml \
  --profile bundled-engine config --quiet
python3 ci/test_amanuensis_contract.py
```

This is a self-contained **engine placement**, not a new production app installer.
The existing dev app retains its host-audio requirements. CPU/1070 throughput and
full offline inference remain unmeasured. Do not advertise offline readiness until
models are seeded, licenses/gated model access are satisfied and inference is measured.
Registry access and first-use model downloads may require operator credentials;
none are included. Speaker's model credential is supplied by environment at runtime.
GPU acceleration requires a separately reviewed hardware profile, never automatic
selection of a shared GPU. The shim defaults to no metering endpoint in this local
profile; configure it explicitly when metering is required.

## CI and rollout gates

Forgejo validates merged compose contracts and pulls the exact digest references,
then runs batch syntax, speaker synthetic health tests, stream Opus tests and shim
route import checks in ephemeral containers. No GPU, model token, host mount, host
network, application upload or live service is used. These are compatibility checks,
not speech-accuracy or performance measurements. Upstream image build evidence is
run 17; the consumer workflow verifies those published artifacts can actually be pulled.

Cutover remains blocked on the patch reconciliation and an Aaron/Persephone window.
Before any approved recreation: preserve old image IDs/tags, full compose chain and
mounted patches in a rollback checkpoint; render a before/after config diff. Recreate
one specifically approved engine service at a time, stream last, never during a live
meeting/show. Verify synthetic upload/transcription rows/speaker labels and stream
session behavior over the wire. On failure restore that service's image/config/patch
checkpoint. Retain old images. No prod cutover is authorized.

The inspected repository has no `scripts/deploy.sh`; do not invent a replacement
fleet deploy command or run a generic compose up across the stack. The operator must
supply/review the actual host deployment procedure before the window.
