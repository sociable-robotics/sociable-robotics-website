"""
Build side-by-side GIFs from paired left/right image sequences.

Default input layout (as in this repo):
  assets/
    pre-processed image folders/
      25/
        ego_left/rgb/0.jpg ...
        ego_right/rgb/0.jpg ...
      50/
        ego_left/rgb/0.jpg ...
        ego_right/rgb/0.jpg ...

Outputs (by default):
  assets/preprocessed_25.gif
  assets/preprocessed_50.gif
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

from PIL import Image


@dataclass(frozen=True)
class SequencePaths:
    left_dir: Path
    right_dir: Path
    out_gif: Path


def _numeric_stem(p: Path) -> int:
    # Expected stems like "0", "1", "198"
    return int(p.stem)


def _list_frames(directory: Path) -> List[Path]:
    if not directory.exists():
        raise FileNotFoundError(f"Missing directory: {directory}")

    frames = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}]
    if not frames:
        raise FileNotFoundError(f"No frames found in: {directory}")

    try:
        frames.sort(key=_numeric_stem)
    except ValueError as e:
        raise ValueError(
            f"Frame filenames must be numeric (e.g. 0.jpg, 1.jpg). " f"Found non-numeric in: {directory}"
        ) from e
    return frames


def _validate_pairs(left_frames: List[Path], right_frames: List[Path], strict: bool) -> List[Tuple[Path, Path]]:
    left_map = {p.stem: p for p in left_frames}
    right_map = {p.stem: p for p in right_frames}

    common = sorted(set(left_map.keys()) & set(right_map.keys()), key=lambda s: int(s))
    missing_left = sorted(set(right_map.keys()) - set(left_map.keys()), key=lambda s: int(s))
    missing_right = sorted(set(left_map.keys()) - set(right_map.keys()), key=lambda s: int(s))

    if strict and (missing_left or missing_right):
        msg = ["Left/right frames do not match."]
        if missing_left:
            msg.append(f"Missing in left: {missing_left[:20]}{'...' if len(missing_left) > 20 else ''}")
        if missing_right:
            msg.append(f"Missing in right: {missing_right[:20]}{'...' if len(missing_right) > 20 else ''}")
        raise ValueError(" ".join(msg))

    pairs: List[Tuple[Path, Path]] = [(left_map[k], right_map[k]) for k in common]
    if not pairs:
        raise ValueError("No matching left/right frames to build GIF.")
    return pairs


def _resize_to_match_height(img: Image.Image, target_h: int) -> Image.Image:
    if img.height == target_h:
        return img
    new_w = max(1, round(img.width * (target_h / img.height)))
    return img.resize((new_w, target_h), Image.Resampling.LANCZOS)


def _maybe_scale(img: Image.Image, scale: float) -> Image.Image:
    if scale == 1.0:
        return img
    new_w = max(1, round(img.width * scale))
    new_h = max(1, round(img.height * scale))
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def _stitch_lr(left: Image.Image, right: Image.Image, *, scale: float) -> Image.Image:
    left = left.convert("RGB")
    right = right.convert("RGB")

    left = _maybe_scale(left, scale)
    right = _maybe_scale(right, scale)

    # Make heights match (common for dual-cam streams, but we keep it robust).
    target_h = min(left.height, right.height)
    left = _resize_to_match_height(left, target_h)
    right = _resize_to_match_height(right, target_h)

    out = Image.new("RGB", (left.width + right.width, target_h))
    out.paste(left, (0, 0))
    out.paste(right, (left.width, 0))
    return out


def build_gif(
    left_dir: Path,
    right_dir: Path,
    out_gif: Path,
    *,
    fps: float,
    scale: float,
    strict: bool,
) -> None:
    left_frames = _list_frames(left_dir)
    right_frames = _list_frames(right_dir)
    pairs = _validate_pairs(left_frames, right_frames, strict=strict)

    duration_ms = max(1, int(round(1000.0 / fps)))

    stitched_frames: List[Image.Image] = []
    for left_path, right_path in pairs:
        with Image.open(left_path) as l_img, Image.open(right_path) as r_img:
            stitched = _stitch_lr(l_img, r_img, scale=scale)
            stitched_frames.append(stitched)

    out_gif.parent.mkdir(parents=True, exist_ok=True)
    first, rest = stitched_frames[0], stitched_frames[1:]
    first.save(
        out_gif,
        save_all=True,
        append_images=rest,
        loop=0,
        duration=duration_ms,
        optimize=True,
        disposal=2,
    )


def _guess_sequence_paths(repo_root: Path) -> List[SequencePaths]:
    assets = repo_root / "assets"
    base = assets / "pre-processed image folders"
    sequences: List[SequencePaths] = []

    # Prefer the repo's current naming (ego_left/ego_right/rgb), but also tolerate left/right.
    for name in ("25", "50"):
        root = base / name
        left = root / "ego_left" / "rgb"
        right = root / "ego_right" / "rgb"
        if not (left.exists() and right.exists()):
            left = root / "left"
            right = root / "right"

        out = assets / f"preprocessed_{name}.gif"
        sequences.append(SequencePaths(left_dir=left, right_dir=right, out_gif=out))
    return sequences


def main(argv: Iterable[str]) -> int:
    parser = argparse.ArgumentParser(description="Create side-by-side left/right GIFs from frame folders.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Path to repo root (default: inferred from this script location).",
    )
    parser.add_argument("--fps", type=float, default=12.0, help="Frames per second for the GIF (default: 12).")
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Uniform scale factor applied to frames before stitching (default: 1.0).",
    )
    parser.add_argument(
        "--no-strict",
        action="store_true",
        help="If set, build GIF using only the intersection of left/right frame indices.",
    )
    args = parser.parse_args(list(argv))

    if args.fps <= 0:
        print("--fps must be > 0", file=sys.stderr)
        return 2
    if args.scale <= 0:
        print("--scale must be > 0", file=sys.stderr)
        return 2

    sequences = _guess_sequence_paths(args.repo_root)
    strict = not args.no_strict

    for seq in sequences:
        print(f"Building {seq.out_gif} from:")
        print(f"  left:  {seq.left_dir}")
        print(f"  right: {seq.right_dir}")
        build_gif(seq.left_dir, seq.right_dir, seq.out_gif, fps=args.fps, scale=args.scale, strict=strict)
        print("  done")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

