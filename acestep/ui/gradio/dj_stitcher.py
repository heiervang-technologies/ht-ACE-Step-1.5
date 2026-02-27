"""Sliding-window DJ stitcher for continuous ACE-Step music generation.

Uses the repaint task type to achieve model-level audio continuity:
the tail of the previous segment is passed as context (src_audio),
and the DiT generates new audio that seamlessly continues from it.
No post-hoc crossfading is needed.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx
import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)


@dataclass
class DJConfig:
    """Configuration for a DJ session."""

    api_base: str = "http://127.0.0.1:8001"
    segment_duration: float = 30.0
    context_duration: float = 10.0
    end_guard: float = 10.0
    weirdness: float = 0.3
    inference_steps: int = 8
    guidance_scale: float = 7.0
    thinking: bool = False
    bpm: Optional[int] = None
    key_scale: str = ""
    vocal_language: str = "en"
    audio_format: str = "wav"
    poll_interval: float = 2.0
    poll_timeout: float = 600.0


@dataclass
class DJSegment:
    """A single generated segment."""

    index: int
    full_audio: np.ndarray  # Full output including context (channels, samples)
    playback_audio: np.ndarray  # Context-trimmed portion for playback
    sample_rate: int
    duration: float  # Duration of playback_audio
    prompt: str
    lyrics: str
    metas: dict = field(default_factory=dict)


class DJStitcher:
    """Continuous segment generation with repaint-based context prefill."""

    SAMPLE_RATE = 48000

    def __init__(self, config: DJConfig) -> None:
        self.config = config
        self.segments: list[DJSegment] = []
        self.accumulated_audio: Optional[np.ndarray] = None
        self._stop_requested = False
        self._current_prompt = ""
        self._current_lyrics = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_prompt(self, prompt: str, lyrics: str) -> None:
        """Update prompt/lyrics for the *next* segment."""
        self._current_prompt = prompt
        self._current_lyrics = lyrics

    def stop(self) -> None:
        """Signal the generation loop to stop after the current segment."""
        self._stop_requested = True

    @property
    def is_stopped(self) -> bool:
        return self._stop_requested

    async def generate_next(self) -> DJSegment:
        """Generate the next segment using repaint-based context prefill.

        First segment: text2music (no context).
        Subsequent: repaint with tail of previous segment as audio context.
        The model outpaints beyond the context, producing seamless continuation.

        End guard: extra audio generated at the tail (then discarded) so the
        model's natural song ending falls outside the playback window.
        """
        prompt = self._current_prompt
        lyrics = self._current_lyrics
        end_guard = self.config.end_guard

        # Extract context from previous segment's *playback* audio
        # (excludes end guard so we don't use discarded ending as context)
        ctx_audio = None
        context_dur = self.config.context_duration
        if self.segments:
            prev_playback = self.segments[-1].playback_audio
            ctx_samples = min(
                int(context_dur * self.SAMPLE_RATE),
                prev_playback.shape[-1],
            )
            ctx_audio = prev_playback[:, -ctx_samples:]

        task_id = await self.submit_segment(prompt, lyrics, ctx_audio, context_dur)
        result = await self.poll_segment(task_id)
        full_audio, sr = await self.download_audio(result["file_url"])

        # Trim context prefix and end guard tail for playback
        trim_start = int(context_dur * sr) if ctx_audio is not None else 0
        trim_end = int(end_guard * sr) if end_guard > 0 else 0
        total_samples = full_audio.shape[-1]
        play_end = max(total_samples - trim_end, trim_start + sr)  # at least 1s
        playback_audio = full_audio[:, trim_start:play_end]

        logger.info(
            "Trimmed %0.1fs prefix + %0.1fs end guard → %0.1fs playback",
            trim_start / sr,
            trim_end / sr,
            playback_audio.shape[-1] / sr,
        )

        segment = DJSegment(
            index=len(self.segments),
            full_audio=full_audio,
            playback_audio=playback_audio,
            sample_rate=sr,
            duration=playback_audio.shape[-1] / sr,
            prompt=prompt,
            lyrics=lyrics,
            metas=result.get("metas", {}),
        )

        # Append playback audio to accumulated stream (gapless, no crossfade)
        if self.accumulated_audio is None:
            self.accumulated_audio = playback_audio.copy()
        else:
            self.accumulated_audio = np.concatenate(
                [self.accumulated_audio, playback_audio], axis=-1
            )

        self.segments.append(segment)
        return segment

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _encode_wav(self, audio: np.ndarray) -> bytes:
        """Encode numpy audio (channels, samples) as WAV bytes."""
        buf = io.BytesIO()
        # soundfile expects (samples, channels)
        sf.write(buf, audio.T, self.SAMPLE_RATE, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    async def submit_segment(
        self,
        prompt: str,
        lyrics: str,
        ctx_audio: Optional[np.ndarray] = None,
        context_dur: float = 0.0,
    ) -> str:
        """Submit a generation job. Returns task_id.

        First segment (ctx_audio=None): text2music via JSON.
        Subsequent (ctx_audio provided): repaint via multipart FormData
        with the context audio uploaded as ctx_audio.
        """
        url = f"{self.config.api_base}/release_task"

        # Generation duration includes end guard so the model's natural
        # ending falls in the discarded tail, not the playback region.
        gen_dur = self.config.segment_duration + self.config.end_guard
        cover_strength = max(0.0, min(1.0, 1.0 - self.config.weirdness))

        if ctx_audio is not None:
            # Repaint mode: upload context as ctx_audio
            total_dur = context_dur + gen_dur
            wav_bytes = self._encode_wav(ctx_audio)
            files = {"ctx_audio": ("context.wav", wav_bytes, "audio/wav")}
            data = {
                "prompt": prompt,
                "lyrics": lyrics or "[inst]",
                "audio_duration": str(total_dur),
                "task_type": "repaint",
                "repainting_start": str(context_dur),
                "repainting_end": str(total_dur),
                "audio_cover_strength": str(cover_strength),
                "inference_steps": str(self.config.inference_steps),
                "guidance_scale": str(self.config.guidance_scale),
                "thinking": str(self.config.thinking).lower(),
                "batch_size": "1",
                "audio_format": self.config.audio_format,
                "vocal_language": self.config.vocal_language,
            }
            if self.config.bpm:
                data["bpm"] = str(self.config.bpm)
            if self.config.key_scale:
                data["key_scale"] = self.config.key_scale

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, data=data, files=files)
                resp.raise_for_status()
                resp_data = resp.json()
        else:
            # First segment: text2music via JSON
            body: dict = {
                "prompt": prompt,
                "lyrics": lyrics or "[inst]",
                "audio_duration": gen_dur,
                "task_type": "text2music",
                "inference_steps": self.config.inference_steps,
                "guidance_scale": self.config.guidance_scale,
                "thinking": self.config.thinking,
                "batch_size": 1,
                "audio_format": self.config.audio_format,
                "vocal_language": self.config.vocal_language,
            }
            if self.config.bpm:
                body["bpm"] = self.config.bpm
            if self.config.key_scale:
                body["key_scale"] = self.config.key_scale

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=body)
                resp.raise_for_status()
                resp_data = resp.json()

        task_id = resp_data["data"]["task_id"]
        logger.info("Submitted segment job %s", task_id)
        return task_id

    async def poll_segment(self, task_id: str) -> dict:
        """Poll until segment generation completes. Returns parsed result."""
        url = f"{self.config.api_base}/query_result"
        elapsed = 0.0

        async with httpx.AsyncClient(timeout=30.0) as client:
            while elapsed < self.config.poll_timeout:
                resp = await client.post(url, json={"task_id_list": [task_id]})
                resp.raise_for_status()
                data = resp.json()

                item = data["data"][0]
                status = item["status"]

                if status == 1:  # succeeded
                    result_list = json.loads(item["result"])
                    first = result_list[0]
                    return {
                        "file_url": first["file"],
                        "metas": first.get("metas", {}),
                        "prompt": first.get("prompt", ""),
                        "lyrics": first.get("lyrics", ""),
                    }

                if status == 2:  # failed
                    raise RuntimeError(
                        f"Segment generation failed: {item.get('result', 'unknown')}"
                    )

                await asyncio.sleep(self.config.poll_interval)
                elapsed += self.config.poll_interval

        raise TimeoutError(
            f"Segment {task_id} timed out after {self.config.poll_timeout}s"
        )

    async def download_audio(self, file_url: str) -> tuple[np.ndarray, int]:
        """Download audio from the API and decode to numpy array.

        Returns (audio_data, sample_rate) where audio_data is (channels, samples).
        """
        # file_url is relative like /v1/audio?path=...
        url = f"{self.config.api_base}{file_url}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        audio_data, sr = sf.read(io.BytesIO(resp.content), dtype="float32")
        # soundfile returns (samples, channels) — transpose to (channels, samples)
        if audio_data.ndim == 2:
            audio_data = audio_data.T
        else:
            audio_data = audio_data[np.newaxis, :]
        return audio_data, sr
