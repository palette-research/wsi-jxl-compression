"""
Visualizer to see which tiles are being selected from the mask applied to the slide.
"""

# --------- Packages -------------
from utils.classes.Mask import Mask
from utils.classes.Tile import Tile

from pathlib import Path
from typing import List, Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import openslide
# --------- Main -------------
def save_tile_overlay(
        slide_path: str,
        mask: Mask,
        tiles: List[Tile],
        out_path: str,
        draw_bbox: bool = True,
        draw_mask_edge: bool = True,
        color_by_coverage: bool = True,
        draw_ids_every: Optional[int] = None,
) -> None:
    """

    :param slide_path:
    :param mask:
    :param tiles:
    :param out_path:
    :param draw_bbox:
    :param draw_mask_edge:
    :param color_by_coverage:
    :param draw_ids_every:
    :return:
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    osr = openslide.OpenSlide(slide_path)
    try:
        w, h = osr.level_dimensions[mask.level]
        thumb = osr.read_region((0, 0), mask.level, (w, h)).convert("RGB")
        arr = np.asarray(thumb).copy()
        down = float(mask.downsample)

        # 1) Mask edge (red)
        if draw_mask_edge:
            try:
                from skimage.morphology import binary_erosion, disk
                edges = mask.mask ^ binary_erosion(mask.mask, disk(1))
            except Exception:
                # fallback: simple XOR with shifted array (cheap, coarser)
                e = np.zeros_like(mask.mask, dtype=bool)
                e[1:, :] |= mask.mask[1:, :] ^ mask.mask[:-1, :]
                e[:, 1:] |= mask.mask[:, 1:] ^ mask.mask[:, :-1]
                edges = e
            arr[edges, 0] = 255
            arr[edges, 1] = 0
            arr[edges, 2] = 0

        im = Image.fromarray(arr)
        draw = ImageDraw.Draw(im)

        # 2) BBox (green)
        if draw_bbox:
            x0, y0, x1, y1 = mask.bbox_level0
            bx0 = int(x0 / down);
            by0 = int(y0 / down)
            bx1 = int(x1 / down);
            by1 = int(y1 / down)
            draw.rectangle([bx0, by0, bx1, by1], outline=(0, 255, 0), width=8)

        # 3) Tiles
        for i, t in enumerate(tiles):
            tx0 = int(t.x / down);
            ty0 = int(t.y / down)
            tx1 = int((t.x + t.w) / down);
            ty1 = int((t.y + t.h) / down)

            if color_by_coverage and hasattr(t, "coverage"):
                # map coverage [0..1] → color from yellow (low) to green (high)
                cov = float(getattr(t, "coverage", 0.0))
                g = int(round(128 + 127 * max(0.0, min(1.0, cov))))  # 128..255
                r = int(round(255 - 200 * max(0.0, min(1.0, cov))))  # 55..255
                color = (r, g, 0)
            else:
                color = (0, 255, 0)

            draw.rectangle([tx0, ty0, tx1, ty1], outline=color, width=5)

            if draw_ids_every and (i % draw_ids_every == 0):
                draw.text((tx0 + 2, ty0 + 2), str(i), fill=(255, 255, 255))

        # 4) Legend
        legend = (
            f"level={mask.level} down={down:.2f}  tiles={len(tiles)}  "
            f"mask={mask.mask.shape[1]}x{mask.mask.shape[0]}  cov={mask.coverage:.3f}"
        )
        draw.rectangle([5, 5, 5 + 8 * len(legend), 28], fill=(0, 0, 0))
        draw.text((8, 8), legend, fill=(255, 255, 255))

        im.save(out)
    finally:
        osr.close()
