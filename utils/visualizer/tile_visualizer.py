"""
Visualizer to see which tiles are being selected from the mask applied to the slide.

@Author: Didrik Wiig-Andersen
@Created: Nov 1, 2025
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import openslide
from config import VisualizerConfig
from utils.classes.Mask import Mask
from utils.classes.Tile import Tile
from utils.mask.mask_helpers import get_slide_dimensions

def save_tile_overlay(
    slide_path: str,
    mask: Mask,
    tiles: List[Tile],
    cfg: VisualizerConfig
) -> None:
    """
    Visualize the selected tiles.

    :param slide_path: the path to the slide.
    :param mask: the mask.
    :param tiles: the selected tiles.
    :param cfg: configuration object.
    :return: None
    """
    out = Path(cfg.OUT_PATH)
    out.parent.mkdir(parents=True, exist_ok=True)
    slide = openslide.OpenSlide(slide_path)
    try:
        w, h = get_slide_dimensions(slide, mask.level)
        thumb = slide.read_region((0, 0), mask.level, (w, h)).convert("RGB")
        arr = np.asarray(thumb).copy()
        down = float(mask.downsample)
        im = Image.fromarray(arr)
        draw = ImageDraw.Draw(im)

        # ---------- Drawing the BBox --------------- #
        x0, y0, x1, y1 = mask.bbox_level0
        bx0 = int(np.floor(x0 / down))
        by0 = int(np.floor(y0 / down))
        bx1 = int(np.ceil(x1 / down))
        by1 = int(np.ceil(y1 / down))
        draw.rectangle([bx0, by0, bx1, by1], outline=cfg.BBOX_COLOR, width=cfg.BBOX_WIDTH)

        # ----------- Drawing the tiles ------------ #
        for i, t in enumerate(tiles):
            tx0 = int(np.floor(t.x / down))
            ty0 = int(np.floor(t.y / down))
            tx1 = int(np.ceil((t.x + t.w) / down))
            ty1 = int(np.ceil((t.y + t.h) / down))
            draw.rectangle([tx0, ty0, tx1, ty1], outline=cfg.TILE_COLOR, width=cfg.TILE_WIDTH)

        im.save(out)
    finally:
        slide.close()
