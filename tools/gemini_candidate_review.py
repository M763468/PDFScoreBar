#!/usr/bin/env python3
"""Send page image + candidate JSON to Gemini and return per-candidate labels.

This script is standalone and does not depend on existing evaluation scripts.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_candidates(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError("Candidates JSON must be a list")
    for item in data:
        if "id" not in item or "bbox" not in item:
            raise ValueError("Each candidate must include id and bbox")
    return data


def load_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    env: Dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def build_prompt(candidates: List[Dict[str, Any]], output_mode: str) -> str:
    if output_mode == "false_only":
        output_hint = (
            "Return ONLY the candidates that are NOT barlines as a JSON array of "
            "{id, is_barline=false, confidence}."
        )
    else:
        output_hint = "Return JSON array: [{id, is_barline, confidence}]."
    # Keep it short and strict. Candidate list is appended for grounding.
    return (
        "You are a music-notation reviewer. For each candidate bbox, decide if it is a true barline.\n"
        "Rules:\n"
        "- A barline is a straight vertical line that spans the staff height.\n"
        "- Reject note stems, beams, sharps/flats/naturals, clefs, and other symbols.\n"
        "- BBox coordinates are in the provided image's pixel coordinate system.\n"
        "- If uncertain, return false with low confidence.\n"
        f"{output_hint}\n"
        "Candidates JSON:\n"
        f"{json.dumps(candidates, ensure_ascii=True)}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--candidates", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--model", type=str, default="gemini-1.5-flash")
    ap.add_argument("--api-key-env", type=str, default="GEMINI_API_KEY")
    ap.add_argument("--prompt", type=Path, default=None, help="Optional prompt template file")
    ap.add_argument("--env-file", type=Path, default=Path(".env"))
    ap.add_argument("--max-candidates", type=int, default=0, help="Limit candidates for quick tests.")
    ap.add_argument(
        "--media-resolution",
        type=str,
        default="high",
        choices=["low", "medium", "high", "ultra_high"],
        help="Image resolution hint for Gemini (ultra_high is mapped to high).",
    )
    ap.add_argument(
        "--thinking-level",
        type=str,
        default=None,
        choices=["minimal", "low", "medium", "high"],
        help="Thinking level for Gemini reasoning (Gemini 2.0+ only).",
    )
    ap.add_argument(
        "--output-mode",
        choices=["all", "false_only"],
        default="all",
        help="Return all labels or only false candidates.",
    )
    args = ap.parse_args()

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        env_from_file = load_env_file(args.env_file)
        api_key = env_from_file.get(args.api_key_env)
    if not api_key:
        raise SystemExit(f"Missing API key in env var {args.api_key_env}")

    try:
        from google import genai
        from google.genai import types
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise SystemExit("google-genai is required. Install via: pip install google-genai") from exc

    # Load inputs
    candidates = load_candidates(args.candidates)
    if args.max_candidates and args.max_candidates > 0:
        candidates = candidates[: args.max_candidates]
    if args.prompt:
        prompt_template = args.prompt.read_text()
        candidates_json = json.dumps(candidates, ensure_ascii=True)
        if "{CANDIDATES_JSON}" in prompt_template:
            prompt = prompt_template.replace("{CANDIDATES_JSON}", candidates_json)
        elif "Candidates JSON:" in prompt_template:
            prompt = f"{prompt_template}\n{candidates_json}"
        else:
            prompt = prompt_template
    else:
        prompt = build_prompt(candidates, args.output_mode)

    from PIL import Image

    image = Image.open(args.image)
    image_format = image.format or "PNG"
    image_bytes = Path(args.image).read_bytes()

    media_resolution = args.media_resolution
    if media_resolution == "ultra_high":
        # google-genai currently supports up to HIGH; map ultra_high to HIGH.
        media_resolution = "high"
    media_resolution_enum = {
        "low": types.MediaResolution.MEDIA_RESOLUTION_LOW,
        "medium": types.MediaResolution.MEDIA_RESOLUTION_MEDIUM,
        "high": types.MediaResolution.MEDIA_RESOLUTION_HIGH,
    }[media_resolution]

    config_args = {
        "response_mime_type": "application/json",
        "media_resolution": media_resolution_enum,
    }

    if args.thinking_level:
        thinking_level_enum = {
            "minimal": types.ThinkingLevel.MINIMAL,
            "low": types.ThinkingLevel.LOW,
            "medium": types.ThinkingLevel.MEDIUM,
            "high": types.ThinkingLevel.HIGH,
        }[args.thinking_level]
        config_args["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level_enum)

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=args.model,
        contents=[
            prompt,
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=f"image/{image_format.lower()}",
            ),
        ],
        config=types.GenerateContentConfig(**config_args),
    )

    # Expect JSON array in text
    output_text = response.text.strip() if response.text else ""
    args.output.write_text(output_text)


if __name__ == "__main__":
    main()
