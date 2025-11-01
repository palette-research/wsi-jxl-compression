"""
Applies a mask to the slide to separate the tissue from the background. The first step of the iteration.

@Author: Didrik Wiig-Andersen
@Created: Fri Oct 31, 2025
"""

# --------- Packages -------------
from utils.mask.mask_helpers import get_slide_dimensions
from utils.classes.Mask import Mask
from config import MaskingConfig

import logging
import numpy as np
import openslide
from skimage.color import rgb2hsv
from skimage.util import img_as_float
from skimage.filters import threshold_otsu
from skimage.morphology import remove_small_objects, binary_closing, binary_opening, disk

# -------------- Logging ------------- #
log = logging.getLogger(__name__)

# --------- Functions -------------
def make_tissue_mask(slide_path: str, cfg: MaskingConfig) -> Mask:
    """
    Compute a low-res tissue mask at an auto-selected pyramid level.

    :param slide_path: the path to the slide.
    :param cfg: the configuration of the slide.
    :return: Mask object containing
      - mask_level (int)
      - mask (bool ndarray at mask_level)
      - downsample (float; level-0 pixels per mask pixel)
      - bbox_level0 (x0,y0,x1,y1) in level-0 coordinates
      - coverage (float in [0,1]) fraction of mask pixels that are tissue (at mask_level)
    """
    slide = openslide.OpenSlide(slide_path)
    try:
        # --- level selection to limit rendering cost ---
        W0, H0 = get_slide_dimensions(slide, 0)
        ratio = max(W0, H0) / float(cfg.MAX_MASK_DIM)
        mask_level = slide.get_best_level_for_downsample(ratio if ratio > 1 else 1.0)
        w, h = slide.level_dimensions[mask_level]
        log.info("mask_level=%d size=%dx%d", mask_level, w, h)

        # --- read thumbnail at mask_level ---
        rgb = slide.read_region((0, 0), mask_level, (w, h)).convert("RGB")
        img = np.asarray(rgb)

        # --- HSV thresholding ---
        hsv = rgb2hsv(img_as_float(img))
        S, V = hsv[..., 1], hsv[..., 2]
        try:
            s_thr = threshold_otsu(S)
        except ValueError:
            s_thr = 0.0  # constant image fallback
        sat_mask = S > max(s_thr, cfg.SAT_FLOOR)
        val_mask = V < cfg.VAL_CEILING
        near_white = (
            (img[..., 0] > cfg.WHITE_RGB)
            & (img[..., 1] > cfg.WHITE_RGB)
            & (img[..., 2] > cfg.WHITE_RGB)
        )
        base = sat_mask & val_mask & (~near_white)

        # --- morphology (scale-aware) ---
        long_edge = max(w, h)
        rad_close = max(
            cfg.MORPH_MIN_RADIUS,
            min(cfg.MORPH_MAX_RADIUS, int(round(long_edge / cfg.MORPH_CLOSE_DIV))),
        )
        rad_open = max(
            cfg.MORPH_MIN_RADIUS,
            min(cfg.MORPH_MAX_RADIUS, int(round(long_edge / cfg.MORPH_OPEN_DIV))),
        )
        m = binary_closing(base, disk(rad_close))
        m = binary_opening(m, disk(rad_open))
        m = remove_small_objects(m, min_size=cfg.MIN_OBJECT_PX)
        m = m.astype(bool, copy=False)

        # --- compute bbox in mask coords ---
        ys, xs = np.where(m)
        down = float(slide.level_downsamples[mask_level])

        if xs.size == 0:
            # no tissue -> empty bbox
            return Mask(mask_level, m, down, (0, 0, 0, 0), 0.0)

        x0m, x1m = xs.min(), xs.max()
        y0m, y1m = ys.min(), ys.max()

        # coordinate padding only (fast) — no global binary_dilation
        exp = max(1, int(np.ceil(cfg.DILATE_PX_LEVEL0 / down)))
        x0m = max(0, x0m - exp)
        y0m = max(0, y0m - exp)
        x1m = min(w - 1, x1m + exp)
        y1m = min(h - 1, y1m + exp)

        # --- map bbox to level-0 and clamp to bounds ---
        x0 = int(np.floor(x0m * down))
        y0 = int(np.floor(y0m * down))
        x1 = int(np.ceil((x1m + 1) * down))
        y1 = int(np.ceil((y1m + 1) * down))

        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(W0, x1)
        y1 = min(H0, y1)

        coverage = float(m.mean())
        mask_obj = Mask(mask_level, m, down, (x0, y0, x1, y1), coverage)

        log.info(
            "Mask created | level=%d | down=%.2f | shape=%dx%d | coverage=%.3f | bbox=(%d,%d,%d,%d)",
            mask_obj.level,
            mask_obj.downsample,
            mask_obj.mask.shape[1],
            mask_obj.mask.shape[0],
            mask_obj.coverage,
            *mask_obj.bbox_level0,
        )
        return mask_obj
    finally:
        slide.close()
