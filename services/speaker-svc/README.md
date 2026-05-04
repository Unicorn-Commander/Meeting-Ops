# speaker-svc

Internal microservice for **speaker embedding + diarization**, deployed alongside the
Meeting-Ops backend on bigboy GPU 1.

## Models

| Model | Source | Required token? | What it does |
|---|---|---|---|
| `speechbrain/spkrec-ecapa-voxceleb` | open weights, baked into the image | no | 192-d speaker embeddings (`/embed`, `/identify`) |
| `pyannote/speaker-diarization-3.1` | gated on Hugging Face | **yes** (`HUGGINGFACE_TOKEN`) | turn-level diarization (`/diarize`) |

If `HUGGINGFACE_TOKEN` is not set, `/diarize` gracefully degrades to a single
ECAPA segment — admins can still enroll and identify speakers, just without
turn-level diarization.

## Build + run on bigboy

```bash
cd /home/muut/Production/UC-Meeting-Ops/services/speaker-svc
docker build -t meet-speaker-svc:local .

docker run -d --name meet-speaker-svc \
  --gpus '"device=1"' \
  --network meet-internal \
  -e HUGGINGFACE_TOKEN=hf_xxx \
  -v /opt/speaker-models:/models \
  -p 127.0.0.1:8889:8889 \
  meet-speaker-svc:local
```

The Meeting-Ops backend reaches it as `http://meet-speaker-svc:8889` over the
internal network. There is **no** public ingress for this service.

## Enabling Pyannote 3.1 (admin one-time setup)

1. Visit https://huggingface.co/pyannote/speaker-diarization-3.1 and accept the terms.
2. Visit https://huggingface.co/pyannote/segmentation-3.0 and accept the terms (it's a dependency).
3. Mint a token at https://huggingface.co/settings/tokens (read scope is enough).
4. Set `HUGGINGFACE_TOKEN=hf_xxx` in the speaker-svc env (e.g. in `.env.bigboy`) and restart.
5. Verify: `curl http://meet-speaker-svc:8889/health` should now show
   `"diarizer_available": true` and `"diarizer_error": null`.

The token is **only** used by speaker-svc — the embeddings/RAG service uses
`INFINITY_ENDPOINT` and is unrelated.

## API quick reference

```bash
# Embed a clip
curl -F audio=@speaker_clip.wav http://meet-speaker-svc:8889/embed | jq .embedding_dim
# -> 192

# Diarize a meeting
curl -F audio=@meeting.wav http://meet-speaker-svc:8889/diarize | jq .num_speakers

# Score a query embedding against enrolled speakers
curl -X POST -H 'Content-Type: application/json' http://meet-speaker-svc:8889/identify \
  -d '{"embedding":[...192 floats...],"candidates":[{"speaker_id":1,"embedding":[...]}],"threshold":0.55}'
```

All embeddings are 192-d float32 and ship as JSON arrays. The DB column is
`embedding_dim INT` + `embedding BYTEA` so swapping in a wider model later
(e.g. ECAPA-XL at 256-d, or WavLM at 768-d) is a config change, not a schema change.
