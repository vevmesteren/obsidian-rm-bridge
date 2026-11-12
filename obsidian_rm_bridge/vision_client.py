"""Vision LLM transcription via OpenRouter (DC-4).

Sends each rendered PDF page (PNG) to a vision-capable model and returns the
transcribed handwritten annotations. The model is configurable; the default is
GLM-4.5V (``z-ai/glm-4.5v``) via OpenRouter. When accuracy matters, run a
second model and cross-verify (DC-9).
"""

from __future__ import annotations

import base64
from pathlib import Path

import requests

__all__ = [
    "DEFAULT_MODEL",
    "NO_ANNOTATIONS_MARKER",
    "OPENROUTER_URL",
    "VISION_PROMPT",
    "cross_verify",
    "transcribe_page",
    "transcribe_pages",
]

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "z-ai/glm-4.5v"
NO_ANNOTATIONS_MARKER = "no annotations"

VISION_PROMPT = (
    "Transcribe ALL handwritten annotations visible on this page. "
    "Only output the handwritten text, not the printed document text. "
    "If there are no handwritten annotations, respond with exactly: No annotations"
)


def _image_data_url(png_path: str | Path) -> str:
    with Path(png_path).open("rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/png;base64,{b64}"


def transcribe_page(
    png_path: str | Path,
    api_key: str,
    *,
    model: str = DEFAULT_MODEL,
    timeout: int = 60,
) -> str | None:
    """Send one PNG to the vision model; return transcribed text or ``None``.

    Returns ``None`` when the model reports no annotations
    (``NO_ANNOTATIONS_MARKER``).
    """
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": _image_data_url(png_path)},
                        },
                    ],
                }
            ],
            "max_tokens": 2048,
            "temperature": 0.1,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"].strip()
    # Use exact match against the sentinel, not substring (Copilot #11).
    # "No annotations on the previous draft" is real handwriting, not a
    # no-annotation signal. The prompt asks for exactly "No annotations".
    if text.lower() == NO_ANNOTATIONS_MARKER:
        return None
    return text


def transcribe_pages(
    png_paths: list,
    api_key: str,
    *,
    model: str = DEFAULT_MODEL,
) -> list:
    """Transcribe every page; return ``[(page_number, text), ...]`` for annotated pages.

    All pages are sent to the model — no pre-filtering by drawing count (DC-6).
    """
    out = []
    for i, png_path in enumerate(png_paths, 1):
        text = transcribe_page(png_path, api_key, model=model)
        if text:
            out.append((i, text))
    return out


def cross_verify(
    png_path: str | Path,
    api_key: str,
    *,
    primary_model: str = DEFAULT_MODEL,
    cross_verify_model: str = "gpt-4o",
) -> tuple[str | None, str | None]:
    """Run two models on the same page and return ``(primary_text, verify_text)``.

    Use when transcription accuracy matters (DC-9). When both agree (same text,
    or both ``None``) the result is trustworthy; disagree → review manually.
    """
    primary = transcribe_page(png_path, api_key, model=primary_model)
    verify = transcribe_page(png_path, api_key, model=cross_verify_model)
    return primary, verify