"""
Prepare demo video clips for the FireGuard scenario simulator.

Downscales each clip so its longest side is at most --max-side pixels (decoding
4K video on a laptop CPU is too slow for real-time playback) and writes
``media/clips.json`` describing the clips.

Usage (from the backend folder, with the venv active):

    python tools/prepare_media.py --fire "C:/path/bonfire.mp4" --label "Outdoor bonfire" --id bonfire
    python tools/prepare_media.py --normal "C:/path/highway.mp4" --label "Highway (no fire)" --id highway

Options:
    --fire / --normal   source clip and its kind (exactly one)
    --id                short id used in the dashboard (letters, digits, _ or -)
    --label             human readable name
    --smoke-factor      how smoky the fire is (0-2, default 1.0); drives the simulated MQ-2 sensor
    --max-side          longest side in pixels (default 960)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import cv2

BACKEND_DIR = Path(__file__).resolve().parent.parent
MEDIA_DIR = BACKEND_DIR / "media"
MANIFEST = MEDIA_DIR / "clips.json"


def transcode(src: Path, dst: Path, max_side: int) -> dict:
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise SystemExit(f"Cannot open {src}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = min(1.0, max_side / max(w, h))
    out_w, out_h = int(w * scale) // 2 * 2, int(h * scale) // 2 * 2
    writer = cv2.VideoWriter(str(dst), cv2.VideoWriter_fourcc(*"mp4v"), fps, (out_w, out_h))
    frames = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if scale < 1.0:
            frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)
        writer.write(frame)
        frames += 1
    cap.release()
    writer.release()
    return {"width": out_w, "height": out_h, "fps": round(fps, 2), "frames": frames, "seconds": round(frames / fps, 1)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    kind = ap.add_mutually_exclusive_group(required=True)
    kind.add_argument("--fire", type=Path)
    kind.add_argument("--normal", type=Path)
    ap.add_argument("--id", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--smoke-factor", type=float, default=1.0)
    ap.add_argument("--max-side", type=int, default=960)
    args = ap.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", args.id):
        sys.exit("--id may only contain letters, digits, '_' and '-'")
    src = args.fire or args.normal
    MEDIA_DIR.mkdir(exist_ok=True)
    dst = MEDIA_DIR / f"{args.id}.mp4"
    info = transcode(src, dst, args.max_side)

    clips = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else []
    clips = [c for c in clips if c["id"] != args.id]
    clips.append({
        "id": args.id,
        "label": args.label,
        "file": dst.name,
        "kind": "fire" if args.fire else "normal",
        "smoke_factor": max(0.0, min(2.0, args.smoke_factor)),
        **info,
    })
    MANIFEST.write_text(json.dumps(clips, indent=2), encoding="utf-8")
    print(f"Wrote {dst.relative_to(BACKEND_DIR)} {info} and updated {MANIFEST.relative_to(BACKEND_DIR)}")


if __name__ == "__main__":
    main()
