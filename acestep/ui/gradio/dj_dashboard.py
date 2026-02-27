"""ACE-Step DJ Dashboard — continuous music generation via repaint-based prefill.

Uses the repaint task type for model-level audio continuity: the tail of
the previous segment is passed as context, and the DiT generates new audio
that seamlessly continues from it.

Launch standalone:
    python -m acestep.ui.gradio.dj_dashboard [--port 7861] [--server-name 0.0.0.0]
"""

from __future__ import annotations

import argparse
import logging
from typing import Any

import gradio as gr
import httpx
import numpy as np

from acestep.ui.gradio.dj_stitcher import DJConfig, DJStitcher

logger = logging.getLogger(__name__)

# Musical keys for the dropdown
KEYS = [
    "",
    "C Major", "C Minor",
    "D Major", "D Minor",
    "E Major", "E Minor",
    "F Major", "F Minor",
    "G Major", "G Minor",
    "A Major", "A Minor",
    "B Major", "B Minor",
]

LANGUAGES = ["en", "zh", "ja", "ko", "es", "fr", "de", "pt", "ru", "unknown"]


async def _check_health(url: str) -> str:
    """Check API server health."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{url.rstrip('/')}/health")
            data = r.json()
            if data.get("code") == 200:
                info = data.get("data", {})
                model = info.get("loaded_model", "?")
                llm = "LLM ready" if info.get("llm_initialized") else "no LLM"
                return f"Connected — {model} ({llm})"
            return f"Unexpected response: {data}"
    except Exception as e:
        return f"Connection failed: {e}"


def _audio_for_gradio(audio: np.ndarray | None, sr: int = 48000) -> Any:
    """Convert (channels, samples) numpy array to Gradio audio tuple."""
    if audio is None:
        return None
    # Gradio expects (sample_rate, array) where array is (samples,) or (samples, channels)
    return (sr, audio.T)


async def _generation_loop(
    api_url: str,
    prompt: str,
    lyrics: str,
    seg_dur: float,
    context_dur: float,
    bpm: float | None,
    key: str,
    lang: str,
    steps: float,
    guidance: float,
    thinking: bool,
):
    """Async generator that yields UI updates after each segment."""
    config = DJConfig(
        api_base=api_url.rstrip("/"),
        segment_duration=seg_dur,
        context_duration=context_dur,
        inference_steps=int(steps),
        guidance_scale=guidance,
        thinking=thinking,
        bpm=int(bpm) if bpm else None,
        key_scale=key,
        vocal_language=lang,
    )
    stitcher = DJStitcher(config)
    stitcher.update_prompt(prompt, lyrics)

    rows: list[list] = []

    while not stitcher.is_stopped:
        seg_num = len(stitcher.segments) + 1
        is_repaint = seg_num > 1
        status = f"Generating segment {seg_num}..."
        if is_repaint:
            status += f" (repaint: {context_dur}s context from seg {seg_num - 1})"
        yield (None, _audio_for_gradio(stitcher.accumulated_audio), status, rows)

        try:
            segment = await stitcher.generate_next()
        except Exception as exc:
            logger.exception("Generation failed")
            yield (
                None,
                _audio_for_gradio(stitcher.accumulated_audio),
                f"Error on segment {seg_num}: {exc}",
                rows,
            )
            break

        rows.append([
            segment.index + 1,
            (segment.prompt or "")[:50],
            f"{segment.duration:.1f}s",
            segment.metas.get("bpm", "-"),
            segment.metas.get("keyscale", "-"),
        ])

        total_dur = stitcher.accumulated_audio.shape[-1] / 48000 if stitcher.accumulated_audio is not None else 0
        yield (
            _audio_for_gradio(segment.playback_audio),
            _audio_for_gradio(stitcher.accumulated_audio),
            f"Segment {segment.index + 1} done. Total mix: {total_dur:.1f}s",
            rows,
        )

    # Final yield
    yield (
        gr.skip(),
        _audio_for_gradio(stitcher.accumulated_audio),
        "Stopped.",
        rows,
    )


def create_dj_dashboard() -> gr.Blocks:
    """Build the DJ Dashboard Gradio app."""

    with gr.Blocks(title="ACE-Step DJ Dashboard") as demo:

        # -- Header --------------------------------------------------------
        gr.HTML(
            "<h1 style='margin:0'>ACE-Step DJ Dashboard</h1>"
            "<p style='margin:0;color:#888'>Continuous music generation with repaint-based context prefill</p>"
        )

        with gr.Row():
            api_url = gr.Textbox(
                label="API Server",
                value="http://127.0.0.1:8001",
                scale=3,
            )
            health_box = gr.Textbox(label="Status", interactive=False, scale=2)
            check_btn = gr.Button("Check", scale=1)

        check_btn.click(fn=_check_health, inputs=[api_url], outputs=[health_box])

        with gr.Row():
            # -- Left column: controls -------------------------------------
            with gr.Column(scale=1, min_width=320):
                prompt = gr.Textbox(
                    label="Prompt / Caption",
                    placeholder="chill lo-fi hip hop, jazzy piano, female vocal...",
                    lines=3,
                )
                lyrics = gr.Textbox(
                    label="Lyrics",
                    placeholder="[Instrumental] or [verse]\\nYour lyrics here...",
                    lines=5,
                )

                with gr.Row():
                    seg_dur = gr.Slider(
                        label="Segment (s)", minimum=15, maximum=120, value=30, step=5,
                    )
                    context_dur = gr.Slider(
                        label="Context Prefill (s)", minimum=2, maximum=30, value=10, step=1,
                    )

                with gr.Row():
                    bpm = gr.Number(label="BPM", value=None, precision=0)
                    key_scale = gr.Dropdown(label="Key", choices=KEYS, value="")
                    language = gr.Dropdown(label="Language", choices=LANGUAGES, value="en")

                with gr.Row():
                    steps = gr.Slider(label="Steps", minimum=1, maximum=100, value=8, step=1)
                    guidance = gr.Slider(
                        label="CFG", minimum=1.0, maximum=15.0, value=7.0, step=0.5,
                    )

                thinking = gr.Checkbox(label="Thinking (5Hz LM)", value=False)

                with gr.Row():
                    play_btn = gr.Button("Play / Generate", variant="primary", scale=2)
                    stop_btn = gr.Button("Stop", variant="stop", scale=1)

            # -- Right column: output --------------------------------------
            with gr.Column(scale=2):
                status_box = gr.Textbox(label="Pipeline Status", interactive=False, lines=2)

                current_audio = gr.Audio(
                    label="Latest Segment",
                    type="numpy",
                    interactive=False,
                )
                accumulated_audio = gr.Audio(
                    label="Full Mix (accumulated)",
                    type="numpy",
                    interactive=False,
                )

                history = gr.Dataframe(
                    headers=["#", "Prompt", "Duration", "BPM", "Key"],
                    label="Segment History",
                    interactive=False,
                    column_count=(5, "fixed"),
                )

        # -- Events --------------------------------------------------------
        play_event = play_btn.click(
            fn=_generation_loop,
            inputs=[
                api_url, prompt, lyrics,
                seg_dur, context_dur,
                bpm, key_scale, language,
                steps, guidance, thinking,
            ],
            outputs=[current_audio, accumulated_audio, status_box, history],
        )

        # Clicking Stop cancels the running generation loop.
        stop_btn.click(fn=None, cancels=[play_event])

    return demo


def main() -> None:
    """Entry point for standalone launch."""
    parser = argparse.ArgumentParser(description="ACE-Step DJ Dashboard")
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument("--server-name", type=str, default="127.0.0.1")
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    demo = create_dj_dashboard()
    demo.launch(
        server_name=args.server_name,
        server_port=args.port,
        share=args.share,
        theme=gr.themes.Soft(),
    )


if __name__ == "__main__":
    main()
