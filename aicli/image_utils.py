"""
image_utils.py — Multimodal image support for aicli (F2).

Loads local image files and builds the content array format
required by vision-capable providers (OpenRouter, Gemini).

Supported formats: PNG, JPEG, GIF, WebP
New dependencies: none — base64 and pathlib are stdlib.
"""

import base64
from pathlib import Path

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

MIME_TYPES = {
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif":  "image/gif",
    ".webp": "image/webp",
}


def load_image_b64(path: str) -> tuple[str, str]:
    """
    Load an image file and return (base64_data, mime_type).
    Raises ValueError for unsupported formats or missing files.
    """
    p = Path(path)
    if not p.exists():
        raise ValueError(f"Image file not found: {path}")
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported image format: {ext}. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    file_size = p.stat().st_size
    if file_size > 20 * 1024 * 1024:  # 20MB
        import warnings
        warnings.warn(f"Image file is large ({file_size // (1024*1024)}MB) — may exceed provider limits.")
    with open(p, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return data, MIME_TYPES[ext]


def build_multimodal_content(text: str, image_paths: list[str]) -> list[dict]:
    """
    Build a content array for vision API requests.
    Returns a list with image blocks first, then the text block.
    Compatible with OpenAI-format APIs (OpenRouter, Gemini).
    """
    content = []
    for path in image_paths:
        b64_data, mime_type = load_image_b64(path)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}
        })
    content.append({"type": "text", "text": text})
    return content


def is_multimodal(messages: list[dict]) -> bool:
    """Check if any message in the list contains image content."""
    for msg in messages:
        if isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if block.get("type") == "image_url":
                    return True
    return False
