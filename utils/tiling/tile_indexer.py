"""
Selects tiles from the mask area of the slide.

@Author: Didrik Wiig-Andersen
@Created: Nov 1, 2025
"""
from __future__ import annotations

import logging
from typing import List
import numpy as np
import openslide

from utils.classes.Mask import Mask
from utils.classes.Tile import Tile
from utils.mask.mask_helpers import get_slide_dimensions
from config import IndexerConfig

log = logging.getLogger(__name__)

def build_tile_index(
    slide_path: str,
    mask: Mask,
    cfg: IndexerConfig,
) -> List[Tile]:
    """
    Build a level-0 tile index using a low-res tissue mask.

    :param slide_path: Path to slide.
    :param mask: Mask of tissue.
    :param cfg: Configuration object.
    :return: Returns a list of the selected Tile objects.
    """
    # ---- validate inputs
    if cfg.TILE_SIZE <= 0 or cfg.STRIDE <= 0:
        raise ValueError("TILE_SIZE and STRIDE must be positive integers.")
    if not (0.0 <= cfg.MIN_TISSUE_FRAC <= 1.0):
        raise ValueError("MIN_TISSUE_FRAC must be within [0.0, 1.0].")
    if cfg.STRIDE > cfg.TILE_SIZE:
        log.warning(
            "STRIDE (%d) > TILE_SIZE (%d). This creates gaps between tiles.",
            cfg.STRIDE, cfg.TILE_SIZE
        )

    slide = openslide.OpenSlide(slide_path)
    try:
        W0, H0 = get_slide_dimensions(slide, 0)
        x0, y0, x1, y1 = mask.bbox_level0
        down = float(mask.downsample)

        # clamp bbox to slide bounds
        x0 = max(0, min(x0, W0)); x1 = max(0, min(x1, W0))
        y0 = max(0, min(y0, H0)); y1 = max(0, min(y1, H0))
        if x1 <= x0 or y1 <= y0:
            log.warning("Empty bbox after clamping; no tiles will be produced.")
            return []

        M = mask.mask.astype(np.uint8, copy=False)  # 0/1 for fast mean
        Mh, Mw = M.shape

        tiles: List[Tile] = []
        tid = 0
        total = 0
        kept = 0

        ts = cfg.TILE_SIZE
        st = cfg.STRIDE
        d  = down

        # iterate over bbox only
        for y in range(y0, y1, st):
            # ensure the tile stays inside bbox (and slide) – clamp height
            th = min(ts, y1 - y, H0 - y)
            if th <= 0:
                break
            for x in range(x0, x1, st):
                # clamp width to bbox (and slide)
                tw = min(ts, x1 - x, W0 - x)
                if tw <= 0:
                    break
                total += 1

                # map level-0 tile -> mask coords (conservative bounds)
                mx0 = int(x / d);           my0 = int(y / d)
                mx1 = int(np.ceil((x + tw) / d))
                my1 = int(np.ceil((y + th) / d))

                # clamp to mask array
                if mx0 < 0: mx0 = 0
                if my0 < 0: my0 = 0
                if mx1 > Mw: mx1 = Mw
                if my1 > Mh: my1 = Mh
                if mx0 >= mx1 or my0 >= my1:
                    continue

                # coverage from mask window
                cov = float(M[my0:my1, mx0:mx1].mean())
                if cov >= cfg.MIN_TISSUE_FRAC:
                    t = Tile(
                        id=tid,
                        x=x,
                        y=y,
                        w=tw,
                        h=th,
                        coverage=cov
                    )
                    tiles.append(t)
                    tid += 1
                    kept += 1

        pct = 100.0 * kept / max(1, total)
        log.info(
            "Tile index | kept=%d / total=%d (%.1f%%) | tile=%d | stride=%d | min_cov=%.2f | bbox=%dx%d",
            kept, total, pct, cfg.TILE_SIZE, cfg.STRIDE, cfg.MIN_TISSUE_FRAC, (x1 - x0), (y1 - y0)
        )

        # optional: quick coverage quantiles (debug visibility)
        if kept:
            covs = np.fromiter((t.coverage for t in tiles), dtype=float, count=kept)
            q = np.quantile(covs, [0.1, 0.25, 0.5, 0.75, 0.9]).round(3)
            log.debug("Tile coverage quantiles p10..p90 = %s", q.tolist())

        return tiles
    finally:
        slide.close()
