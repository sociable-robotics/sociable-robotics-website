# Make paired camera GIFs

This script stitches each frame from the left and right camera streams **side-by-side** and exports a GIF per dataset.

## Install dependency

```bash
py -m pip install -r requirements.txt
```

## Generate GIFs

From the repo root:

```bash
py scripts/make_preprocessed_gifs.py --fps 12
```

Outputs:

- `assets/preprocessed_25.gif`
- `assets/preprocessed_50.gif`

## Tips

- If the GIFs are too large, try scaling frames down:

```bash
py scripts/make_preprocessed_gifs.py --fps 12 --scale 0.5
```

