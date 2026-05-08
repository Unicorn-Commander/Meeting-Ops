"""Per-upload transcription options.

These are the knobs a user can flip on a single upload: STT engine, model,
diarization mode + speaker count override, voice-fingerprint enrichment,
and summary template. The schema is intentionally small — every field is
optional and falls back to the active org's settings when omitted.

Stored on `UploadJob.transcription_options` (JSONB). The pipeline workers
consult this object before falling back to ProviderRegistry / org defaults.
The same shape is reused by the re-process endpoint on SessionDetails so
users can re-run an existing recording with different settings without
re-uploading the file.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


_ALLOWED_PROVIDERS = ("whisper", "local_whisper", "parakeet", "nemo", "parakeet-tdt")
_ALLOWED_DIARIZATION = ("auto", "manual", "off")
_ALLOWED_SUMMARY = ("standard", "executive", "technical")


class TranscriptionOptions(BaseModel):
    """User-selectable per-upload transcription preferences.

    Every field is optional — the pipeline reads the field if present,
    otherwise it inherits from the org's saved provider settings (or the
    code-level default for fields with no org-level analogue).
    """

    # STT engine override. Maps to ProviderRegistry.get_stt() routing.
    stt_provider: Optional[str] = Field(
        default=None,
        description="STT engine override: whisper | parakeet (default: org setting).",
    )
    stt_model: Optional[str] = Field(
        default=None,
        description="Specific model id, e.g. 'whisper-large-v3-turbo' or 'parakeet-tdt-0.6b'.",
    )
    language: Optional[str] = Field(
        default=None,
        description="ISO 639-1 language hint, e.g. 'en'. Default: en.",
    )

    # Diarization mode + speaker count override.
    diarization_mode: Optional[str] = Field(
        default=None,
        description=(
            "off  -> skip speaker diarization entirely (single-speaker output). "
            "auto -> let the diarizer auto-detect speaker count (default). "
            "manual -> use diarization_num_speakers as a hard count."
        ),
    )
    diarization_num_speakers: Optional[int] = Field(
        default=None,
        ge=1,
        le=24,
        description="Used only when diarization_mode='manual'.",
    )

    # Voice fingerprint enrichment: match each diarized cluster against the
    # org's SpeakerProfile library and label automatically.
    voice_fingerprint: Optional[bool] = Field(
        default=None,
        description="If True, run speaker_service.identify_speakers() to label clusters from the library.",
    )

    # Summary template. The pipeline reads this and picks the matching
    # _SUMMARY_PROMPTS entry in services.auto_summarization_service.
    summary_template: Optional[str] = Field(
        default=None,
        description="standard | executive | technical (default: standard).",
    )

    @field_validator("stt_provider")
    @classmethod
    def _norm_provider(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().lower()
        if v not in _ALLOWED_PROVIDERS:
            raise ValueError(f"stt_provider must be one of {_ALLOWED_PROVIDERS}")
        return v

    @field_validator("diarization_mode")
    @classmethod
    def _norm_diar_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().lower()
        if v not in _ALLOWED_DIARIZATION:
            raise ValueError(f"diarization_mode must be one of {_ALLOWED_DIARIZATION}")
        return v

    @field_validator("summary_template")
    @classmethod
    def _norm_summary(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().lower()
        if v not in _ALLOWED_SUMMARY:
            raise ValueError(f"summary_template must be one of {_ALLOWED_SUMMARY}")
        return v

    def to_jsonb(self) -> dict[str, Any]:
        """Serialize to a dict safe to store in JSONB. Drops None fields."""
        return {k: v for k, v in self.model_dump().items() if v is not None}


def coerce_options(raw: Any) -> TranscriptionOptions:
    """Build a TranscriptionOptions from anything (None, dict, or instance).
    Always returns a valid object; missing/None fields stay as defaults."""
    if raw is None:
        return TranscriptionOptions()
    if isinstance(raw, TranscriptionOptions):
        return raw
    if isinstance(raw, dict):
        return TranscriptionOptions(**raw)
    return TranscriptionOptions()


def normalized_provider_name(opts: TranscriptionOptions) -> Optional[str]:
    """Map the user-facing provider string onto the internal name used by
    ProviderRegistry.get_stt. Returns None when no override was set."""
    if not opts.stt_provider:
        return None
    if opts.stt_provider in ("whisper", "local_whisper"):
        return "local_whisper"
    return "parakeet"
