"""
Create stitched side-by-side MP4s from the pre-processed left/right camera frames.

Inputs (per dataset):
  assets/pre-processed image folders/<N>/ego_left/rgb/0.jpg ...
  assets/pre-processed image folders/<N>/ego_right/rgb/0.jpg ...

Outputs:
  assets/preprocessed_<N>.mp4

This uses ffmpeg via imageio-ffmpeg so you don't need ffmpeg installed globally.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Literal, Optional

import imageio_ffmpeg


def _ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _require_dir(p: Path) -> None:
    if not p.exists() or not p.is_dir():
        raise FileNotFoundError(f"Missing directory: {p}")


Mode = Literal["stitch", "single"]
Perspective = Literal["left", "right"]


def stitch_dataset(
    repo_root: Path,
    dataset: str,
    *,
    fps: float,
    height: int,
    mode: Mode,
    perspective: Optional[Perspective],
    crf: int,
) -> Path:
    assets = repo_root / "assets"
    base = assets / "pre-processed image folders" / dataset
    left_dir = base / "ego_left" / "rgb"
    right_dir = base / "ego_right" / "rgb"

    _require_dir(left_dir)
    _require_dir(right_dir)

    suffix = f"{height}p_{int(fps)}fps"
    if mode == "single":
        suffix = f"{suffix}_{perspective or 'left'}"
    out_path = assets / f"preprocessed_{dataset}_{suffix}.mp4"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # ffmpeg can read image sequences with %d.jpg even if numbering starts at 0 when -start_number 0 is set.
    left_pattern = str(left_dir / "%d.jpg")
    right_pattern = str(right_dir / "%d.jpg")

    # Target: compressed 480p (height=480) output, 30fps.
    # - scale=-2:<height> preserves aspect ratio and ensures even width for H.264.
    # - stitch mode: scale both to same height then hstack.
    # - single mode: select one channel and scale it.
    if mode == "stitch":
        vf = (
            f"[0:v]scale=-2:{height}[l];"
            f"[1:v]scale=-2:{height}[r];"
            f"[l][r]hstack=inputs=2"
        )
    else:
        use_right = (perspective or "left") == "right"
        idx = 1 if use_right else 0
        vf = f"[{idx}:v]scale=-2:{height}"

    cmd: List[str] = [
        _ffmpeg_exe(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-framerate",
        str(fps),
        "-start_number",
        "0",
        "-i",
        left_pattern,
        "-framerate",
        str(fps),
        "-start_number",
        "0",
        "-i",
        right_pattern,
        "-filter_complex",
        vf,
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        str(crf),
        "-preset",
        "slow",
        str(out_path),
    ]

    subprocess.run(cmd, check=True)
    return out_path


def main(argv: Iterable[str]) -> int:
    parser = argparse.ArgumentParser(description="Stitch ego_left/ego_right frame sequences into side-by-side MP4s.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Path to repo root (default: inferred from this script location).",
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=["25", "50"],
        help="Datasets to process (default: 25 50).",
    )
    parser.add_argument("--fps", type=float, default=30.0, help="Frames per second (default: 30).")
    parser.add_argument("--height", type=int, default=480, help="Output height in pixels (default: 480).")
    parser.add_argument(
        "--mode",
        choices=["stitch", "single"],
        default="single",
        help="stitch = side-by-side; single = one perspective (default: single).",
    )
    parser.add_argument(
        "--perspective",
        choices=["left", "right"],
        default="left",
        help="When --mode single, choose which channel to export (default: left).",
    )
    parser.add_argument("--crf", type=int, default=28, help="H.264 quality (lower=better, default: 28).")
    args = parser.parse_args(list(argv))

    if args.fps <= 0:
        print("--fps must be > 0", file=sys.stderr)
        return 2
    if args.height <= 0:
        print("--height must be > 0", file=sys.stderr)
        return 2
    if not (0 <= args.crf <= 51):
        print("--crf must be between 0 and 51", file=sys.stderr)
        return 2

    for d in args.datasets:
        print(f"Stitching dataset {d} ...")
        out = stitch_dataset(
            args.repo_root,
            d,
            fps=args.fps,
            height=args.height,
            mode=args.mode,
            perspective=args.perspective if args.mode == "single" else None,
            crf=args.crf,
        )
        print(f"  wrote: {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

