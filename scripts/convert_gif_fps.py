"""
Resample a GIF to a target FPS by *skipping frames* (time-based sampling).

This is designed for cases like converting a 30fps GIF down to 12fps.
It uses each frame's stored duration (in ms) to build a timeline, then
selects the frame that covers each sampling time.

Example:
  py scripts/convert_gif_fps.py --input assets\\my_30fps.gif --dst-fps 12
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List, Tuple

from PIL import Image, ImageSequence


def _durations_ms(im: Image.Image) -> List[int]:
    """
    Returns per-frame durations in ms (best-effort).
    If a duration is missing/invalid, defaults to 33ms (~30fps).
    """
    durs: List[int] = []
    for frame in ImageSequence.Iterator(im):
        # Pillow stores GIF frame duration in frame.info["duration"] (ms)
        dur = frame.info.get("duration", im.info.get("duration", 33))
        try:
            dur_int = int(dur)
        except Exception:
            dur_int = 33
        if dur_int <= 0:
            dur_int = 33
        durs.append(dur_int)
    return durs


def _extract_frames_rgba(im: Image.Image) -> List[Image.Image]:
    # Convert to RGBA so we preserve transparency if present.
    return [frame.convert("RGBA") for frame in ImageSequence.Iterator(im)]


def _sample_indices_by_time(durations_ms: List[int], *, dst_fps: float) -> List[int]:
    """
    Sample indices by time using the frame-duration timeline.
    For each sample time t = k*(1/dst_fps), pick the frame covering t.
    """
    if dst_fps <= 0:
        raise ValueError("dst_fps must be > 0")

    total_ms = sum(durations_ms)
    if total_ms <= 0:
        return [0]

    step_ms = 1000.0 / dst_fps

    # Build cumulative end-times for quick selection.
    ends: List[int] = []
    acc = 0
    for d in durations_ms:
        acc += d
        ends.append(acc)

    out: List[int] = []
    t = 0.0
    i = 0
    n = len(durations_ms)
    while t < total_ms and i < n:
        # Advance i until frame i covers time t (i.e., ends[i] > t)
        while i < n and ends[i] <= t:
            i += 1
        if i >= n:
            break
        out.append(i)
        t += step_ms

    if not out:
        out = [0]

    # Deduplicate consecutive duplicates (can happen if dst_fps > effective src fps)
    dedup: List[int] = [out[0]]
    for idx in out[1:]:
        if idx != dedup[-1]:
            dedup.append(idx)
    return dedup


def convert_gif_fps(input_path: Path, output_path: Path, *, dst_fps: float) -> Tuple[int, int]:
    with Image.open(input_path) as im:
        frames = _extract_frames_rgba(im)
        durs = _durations_ms(im)

    if len(frames) != len(durs):
        # Extremely defensive; should not happen.
        n = min(len(frames), len(durs))
        frames = frames[:n]
        durs = durs[:n]

    indices = _sample_indices_by_time(durs, dst_fps=dst_fps)
    out_frames = [frames[i] for i in indices]

    # Set constant duration for output to match dst fps.
    out_duration_ms = max(1, int(round(1000.0 / dst_fps)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    first, rest = out_frames[0], out_frames[1:]
    first.save(
        output_path,
        save_all=True,
        append_images=rest,
        loop=0,
        duration=out_duration_ms,
        optimize=True,
        disposal=2,
    )
    return (len(frames), len(out_frames))


def main(argv: Iterable[str]) -> int:
    p = argparse.ArgumentParser(description="Convert a GIF to a lower FPS by skipping frames.")
    p.add_argument("--input", type=Path, required=True, help="Input GIF path.")
    p.add_argument("--dst-fps", type=float, default=12.0, help="Target FPS (default: 12).")
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output GIF path (default: <input>_<dst-fps>fps.gif next to input).",
    )
    args = p.parse_args(list(argv))

    if args.dst_fps <= 0:
        raise SystemExit("--dst-fps must be > 0")

    if args.output is None:
        out = args.input.with_name(f"{args.input.stem}_{int(args.dst_fps)}fps{args.input.suffix}")
    else:
        out = args.output

    src_n, dst_n = convert_gif_fps(args.input, out, dst_fps=args.dst_fps)
    print(f"Wrote: {out} (frames {src_n} -> {dst_n}, {args.dst_fps} fps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__('sys').argv[1:]))

