from __future__ import annotations

import base64
import csv
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI


ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"}
ALLOWED_VIDEO_EXTS = {".mp4", ".mov"}
DERIVED_DIRNAME = "_derived"
DERIVED_FRAMES_DIRNAME = "frames"
DERIVED_HIGHLIGHT_NAME = "highlight_first3s.mp4"


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _env(name: str, default: Optional[str] = None) -> str:
    v = os.getenv(name)
    if v is None or v == "":
        return default or ""
    return v


def _env_required(name: str) -> str:
    v = _env(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v


def _is_image(p: Path) -> bool:
    return p.suffix.lower() in ALLOWED_IMAGE_EXTS


def _is_video(p: Path) -> bool:
    return p.suffix.lower() in ALLOWED_VIDEO_EXTS


def _sorted_media_files(folder: Path) -> tuple[list[Path], list[Path]]:
    files = [p for p in folder.iterdir() if p.is_file()]
    images = sorted([p for p in files if _is_image(p)], key=lambda p: p.name.lower())
    videos = sorted([p for p in files if _is_video(p)], key=lambda p: p.name.lower())
    return images, videos


def _mime_type_for(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".png":
        return "image/png"
    if ext == ".gif":
        return "image/gif"
    if ext == ".webp":
        return "image/webp"
    if ext in (".heic", ".heif"):
        return "image/heic"
    return "image/jpeg"


def _which_or_none(exe: str) -> Optional[str]:
    return shutil.which(exe)


def _require_ffmpeg() -> tuple[str, str]:
    ffmpeg = _which_or_none("ffmpeg")
    ffprobe = _which_or_none("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError(
            "ffmpeg/ffprobe not found on PATH. Install ffmpeg to enable video support. "
            "Then restart your terminal and retry."
        )
    return ffmpeg, ffprobe


def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr.strip()}")
    return (p.stdout or "").strip()


def _probe_duration_seconds(ffprobe: str, video_path: Path) -> float:
    out = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ]
    )
    data = json.loads(out)
    # Prefer container duration, fallback to first video stream duration.
    fmt = data.get("format") or {}
    if fmt.get("duration"):
        return float(fmt["duration"])
    for s in data.get("streams") or []:
        if s.get("codec_type") == "video" and s.get("duration"):
            return float(s["duration"])
    raise RuntimeError("Could not determine video duration.")


def extract_first3s_highlight(ffmpeg: str, *, video_path: Path, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Re-encode (copy can fail if no keyframe at t=0).
    _run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-t",
            "3",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            str(out_path),
        ]
    )


def extract_keyframes_first_mid_last(
    ffmpeg: str, *, video_path: Path, out_dir: Path, duration_s: float
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)

    # Guard: very short videos still get sane timestamps.
    mid = max(duration_s / 2.0, 0.0)
    last = max(duration_s - 0.1, 0.0)
    stamps = [
        ("frame_first.jpg", 0.0),
        ("frame_middle.jpg", mid),
        ("frame_last.jpg", last),
    ]

    out_paths: list[Path] = []
    for name, ts in stamps:
        out_path = out_dir / name
        # -ss before -i seeks faster; we re-decode 1 frame.
        _run(
            [
                ffmpeg,
                "-y",
                "-ss",
                f"{ts:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(out_path),
            ]
        )
        out_paths.append(out_path)
    return out_paths


@dataclass(frozen=True)
class ListingOutput:
    title: str
    description: str
    condition: str
    category: str
    price: str
    quantity: str
    shipping_cost: str
    selling_points: list[str]
    keywords: list[str]
    brand: str
    model: str
    dimensions: str
    weight: str
    notes: str


def analyze_folder_with_chatgpt(
    client: OpenAI, *, product_folder: Path, images: list[Path], hint_name: Optional[str] = None
) -> dict:
    """
    Sends all images for a product folder to ChatGPT Vision and returns JSON dict.
    """
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                "You are an expert eBay listing writer.\n\n"
                "Analyze these product images and generate a complete eBay listing.\n"
                "If something is unknown, say so and ask a clarifying question in the notes.\n\n"
                "Return ONLY valid JSON with these keys:\n"
                "- name (max 80 chars)\n"
                "- description (HTML)\n"
                "- condition (one of: New, New with tags, New without tags, New with defects, "
                "Used - Excellent, Used - Very Good, Used - Good, Used - Acceptable, For parts)\n"
                "- category\n"
                "- price (string like \"99.99\")\n"
                "- quantity\n"
                "- shipping_cost (string like \"4.90\")\n"
                "- selling_points (array)\n"
                "- keywords (array)\n"
                "- brand\n"
                "- model\n"
                "- dimensions\n"
                "- weight\n"
                "- notes\n"
                + (f"\nFolder hint: {hint_name}\n" if hint_name else "")
            ),
        }
    ]

    # Add images as data URLs
    for img_path in images:
        raw = img_path.read_bytes()
        b64 = base64.b64encode(raw).decode("utf-8")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{_mime_type_for(img_path)};base64,{b64}"},
            }
        )

    messages = [
        {"role": "system", "content": "Always respond with valid JSON. Do not include markdown."},
        {"role": "user", "content": content},
    ]

    model = _env("OPENAI_VISION_MODEL", "gpt-4o")
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        max_tokens=2200,
        temperature=0.4,
    )
    return json.loads(resp.choices[0].message.content)


def _append_to_master_csv(listing_outputs_dir: Path, product_folder: Path, data: dict) -> None:
    listing_outputs_dir.mkdir(exist_ok=True)
    csv_path = listing_outputs_dir / "listings.csv"
    csv_exists = csv_path.exists()

    fieldnames = [
        "folder",
        "name",
        "condition",
        "category",
        "price",
        "quantity",
        "shipping_cost",
        "brand",
        "model",
        "keywords",
        "notes",
    ]

    with csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not csv_exists:
            writer.writeheader()

        writer.writerow(
            {
                "folder": product_folder.name,
                "name": data.get("name", ""),
                "condition": data.get("condition", ""),
                "category": data.get("category", ""),
                "price": data.get("price", ""),
                "quantity": data.get("quantity", "1"),
                "shipping_cost": data.get("shipping_cost", ""),
                "brand": data.get("brand", ""),
                "model": data.get("model", ""),
                "keywords": ", ".join(data.get("keywords", []) or []),
                "notes": (data.get("notes", "") or "").replace("\n", " ")[:240],
            }
        )


def process_one_product_folder(client: OpenAI, *, product_folder: Path, outputs_dir: Path) -> bool:
    """
    Returns True if processed, False if skipped.
    """
    marker_done = product_folder / ".processed"
    if marker_done.exists():
        return False

    images, videos = _sorted_media_files(product_folder)
    if not images:
        # Still allow video-only folders (turntable workflow)
        if not videos:
            return False

    derived_dir = product_folder / DERIVED_DIRNAME
    derived_frames_dir = derived_dir / DERIVED_FRAMES_DIRNAME
    derived_highlight = derived_dir / DERIVED_HIGHLIGHT_NAME

    derived_frames: list[Path] = []

    # Video support: extract frames for analysis + a short highlight clip.
    if videos:
        # Use the first video by name (user can keep one turntable clip here).
        video = videos[0]
        ffmpeg, ffprobe = _require_ffmpeg()
        duration_s = _probe_duration_seconds(ffprobe, video)

        # Only (re)create derived assets if missing. Delete .processed to force a re-run.
        if not derived_highlight.exists():
            extract_first3s_highlight(ffmpeg, video_path=video, out_path=derived_highlight)
        if not (derived_frames_dir / "frame_first.jpg").exists():
            derived_frames = extract_keyframes_first_mid_last(
                ffmpeg, video_path=video, out_dir=derived_frames_dir, duration_s=duration_s
            )
        else:
            derived_frames = [
                derived_frames_dir / "frame_first.jpg",
                derived_frames_dir / "frame_middle.jpg",
                derived_frames_dir / "frame_last.jpg",
            ]

    # Include derived video frames + any separately-taken photos
    all_images = [*images, *[p for p in derived_frames if p.exists()]]
    if not all_images:
        return False

    print(f"\nProcessing: {product_folder.name} ({len(images)} image(s), {len(videos)} video(s))")

    hint = product_folder.name
    data = analyze_folder_with_chatgpt(client, product_folder=product_folder, images=all_images, hint_name=hint)

    # Save into the product folder
    out_path = product_folder / "listing.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Save a copy into central outputs dir
    outputs_dir.mkdir(exist_ok=True)
    central_path = outputs_dir / f"{product_folder.name}_{_now_stamp()}.json"
    central_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    _append_to_master_csv(outputs_dir, product_folder, data)

    # Mark done
    marker_done.write_text(_now_stamp(), encoding="utf-8")
    print(f"Saved: {out_path}")
    return True


def process_products_root(products_root: Path, *, watch: bool = False, interval_seconds: int = 10) -> None:
    products_root.mkdir(parents=True, exist_ok=True)
    outputs_dir = Path(_env("LISTING_OUTPUTS_DIR", "listing_outputs"))

    client = OpenAI(api_key=_env_required("OPENAI_API_KEY"))

    def run_once() -> None:
        subfolders = sorted([p for p in products_root.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
        any_processed = False
        for folder in subfolders:
            if folder.name.startswith(".") or folder.name.startswith("_"):
                continue
            try:
                processed = process_one_product_folder(client, product_folder=folder, outputs_dir=outputs_dir)
                any_processed = any_processed or processed
            except Exception as e:
                print(f"ERROR processing {folder.name}: {e}")
                (folder / ".error").write_text(f"{_now_stamp()}\n{e}\n", encoding="utf-8")
        if not any_processed:
            print("No new product folders to process.")

    if not watch:
        run_once()
        return

    print(f"Watching {products_root} (poll every {interval_seconds}s). Ctrl+C to stop.")
    while True:
        run_once()
        time.sleep(interval_seconds)


def main() -> int:
    load_dotenv()
    root = Path(_env("PRODUCTS_ROOT", "products"))
    watch = _env("WATCH_PRODUCTS", "false").lower() == "true"
    interval = int(_env("WATCH_INTERVAL_SECONDS", "10"))
    process_products_root(root, watch=watch, interval_seconds=interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

