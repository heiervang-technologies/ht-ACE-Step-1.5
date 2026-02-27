"""Sliding-window DJ stitcher for continuous ACE-Step music generation.

Manages segment generation via the ACE-Step API, cross-fading overlaps,
and accumulating a continuous audio stream.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote

import httpx
import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)


@dataclass
class DJConfig:
    """Configuration for a DJ session."""

    api_base: str = "http://127.0.0.1:8001"
    segment_duration: float = 30.0
    overlap_duration: float = 5.0
    crossfade_duration: float = 2.0
    inference_steps: int = 8
    guidance_scale: float = 7.0
    thinking: bool = False
    bpm: Optional[int] = None
    key_scale: str = ""
    vocal_language: str = "en"
    audio_format: str = "mp3"
    poll_interval: float = 2.0
    poll_timeout: float = 600.0


@dataclass
class DJSegment:
    """A single generated segment."""

    index: int
    audio_path: str  # Server-side file path (for reference_audio_path chaining)
    audio_data: np.ndarray  # Shape: (channels, samples), float32
    sample_rate: int
    duration: float
    prompt: str
    lyrics: str
    metas: dict = field(default_factory=dict)


class DJStitcher:
    """Continuous segment generation with cross-fade stitching."""

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
        """Generate, download, crossfade, and append the next segment."""
        ref_path = self.segments[-1].audio_path if self.segments else None
        prompt = self._current_prompt
        lyrics = self._current_lyrics

        task_id = await self.submit_segment(prompt, lyrics, ref_path)
        result = await self.poll_segment(task_id)
        audio_data, sr = await self.download_audio(result["server_path"])

        segment = DJSegment(
            index=len(self.segments),
            audio_path=result["server_path"],
            audio_data=audio_data,
            sample_rate=sr,
            duration=audio_data.shape[-1] / sr,
            prompt=prompt,
            lyrics=lyrics,
            metas=result.get("metas", {}),
        )

        self.crossfade_and_append(audio_data)
        self.segments.append(segment)
        return segment

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def submit_segment(
        self,
        prompt: str,
        lyrics: str,
        reference_audio_path: Optional[str] = None,
    ) -> str:
        """Submit a generation job. Returns task_id."""
        body: dict = {
            "prompt": prompt,
            "lyrics": lyrics or "[inst]",
            "audio_duration": self.config.segment_duration,
            "task_type": "text2music",
            "inference_steps": self.config.inference_steps,
            "guidance_scale": self.config.guidance_scale,
            "thinking": self.config.thinking,
            "batch_size": 1,
            "audio_format": self.config.audio_format,
            "vocal_language": self.config.vocal_language,
        }
        if reference_audio_path:
            body["reference_audio_path"] = reference_audio_path
        if self.config.bpm:
            body["bpm"] = self.config.bpm
        if self.config.key_scale:
            body["key_scale"] = self.config.key_scale

        url = f"{self.config.api_base}/release_task"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()

        task_id = data["data"]["task_id"]
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
                    file_url = first["file"]
                    # Extract raw server path from the URL-encoded query param
                    # file looks like: /v1/audio?path=%2Fhome%2F...
                    from urllib.parse import parse_qs, urlparse

                    parsed = urlparse(file_url)
                    server_path = parse_qs(parsed.query).get("path", [""])[0]
                    return {
                        "server_path": server_path,
                        "file_url": file_url,
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

    async def download_audio(self, server_path: str) -> tuple[np.ndarray, int]:
        """Download audio from the API and decode to numpy array.

        Returns (audio_data, sample_rate) where audio_data is (channels, samples).
        """
        url = f"{self.config.api_base}/v1/audio?path={quote(server_path)}"
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

    # ------------------------------------------------------------------
    # Cross-fade and accumulation
    # ------------------------------------------------------------------

    def crossfade_and_append(self, new_audio: np.ndarray) -> None:
        """Cross-fade new_audio with the tail of accumulated audio and append.

        Args:
            new_audio: shape (channels, samples), float32
        """
        if self.accumulated_audio is None:
            self.accumulated_audio = new_audio.copy()
            return

        xfade_samples = int(self.config.crossfade_duration * self.SAMPLE_RATE)
        # Clamp to available audio
        xfade_samples = min(
            xfade_samples,
            self.accumulated_audio.shape[-1],
            new_audio.shape[-1],
        )

        if xfade_samples <= 0:
            self.accumulated_audio = np.concatenate(
                [self.accumulated_audio, new_audio], axis=-1
            )
            return

        fade_out = np.linspace(1.0, 0.0, xfade_samples, dtype=np.float32)
        fade_in = np.linspace(0.0, 1.0, xfade_samples, dtype=np.float32)

        tail = self.accumulated_audio[:, -xfade_samples:]
        head = new_audio[:, :xfade_samples]
        blended = tail * fade_out + head * fade_in

        self.accumulated_audio = np.concatenate(
            [
                self.accumulated_audio[:, :-xfade_samples],
                blended,
                new_audio[:, xfade_samples:],
            ],
            axis=-1,
        )
