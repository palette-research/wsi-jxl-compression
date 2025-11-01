"""

"""

# --------- Packages -------------
from utils.mask.mask_helpers import (
    get_slide_dimensions
)
from utils.classes.Tile import Tile
from config import MaskingConfig

import numpy as np
from PIL import Image
import openslide
from skimage.color import rgb2hsv
from skimage.filters import threshold_otsu
from skimage.morphology import remove_small_objects, binary_closing, binary_opening, disk
from skimage.measure import label, regionprops

# --------- Functions -------------
def make_tissue_mask(
  slide_path: str,
  cfg: MaskingConfig
):
    """

    :param cfg:
    :param slide_path:
    :return:
    """

    # --------- Setup -------------
    slide = openslide.OpenSlide(slide_path) # opening the slide
    W0, H0 = get_slide_dimensions(slide, 0) # retrieving the slide dimensions

    # Select the level, to limit rendering cost upon mask selection
    ratio = max(W0, H0) / float(cfg.MAX_MASK_DIM)
    mask_level = slide.get_best_level_for_downsample(ratio if ratio > 1 else 1.0) # selects pyramidal level

    # Get the size at the chosen level
    w, h = slide.level_dimensions[mask_level]

    # Read the entire image at that level
    rgb = slide.read_region((0, 0), mask_level, (w, h)).convert("RGB")
    img = np.asarray(rgb)

    print(f"mask_level: {mask_level}")
    print(f"w: {w}, h: {h}")

    # --------- HSV thresholding -------------

    # Convert colors from the RGB color space to the HSV color space
    hsv = rgb2hsv(img)
    H, S, V = hsv[...,0], hsv[...,1], hsv[...,2]
    s_thr = threshold_otsu(S)
    sat_mask = S > max(s_thr, 0.08)
    val_mask = V < 0.98
    near_white = (img[...,0] > 245) & (img[...,1] > 245) & (img[...,2] > 245)
    base = sat_mask & val_mask & (~near_white)

    # --------- Morphology to clean -------------
    m = binary_closing(base, disk(3))
    m = binary_opening(m, disk(2))
    m = remove_small_objects(m, min_size=cfg.MIN_OBJECT_PX)

    # ------- Filter on the largest connected areas --------- #
    # @TODO

    # ----- Compute bbox in mask coords, then expand and map to level-0 -----
    ys, xs = np.where(m)
    if len(xs) == 0:
        # fallback: no tissue found -> empty bbox
        down = slide.level_downsamples[mask_level]
        return mask_level, m, down, (0, 0, 0, 0)

    x0m, x1m = xs.min(), xs.max()
    y0m, y1m = ys.min(), ys.max()
    # expand bbox by ~dilate_px_level0 when mapped to level-0
    down = slide.level_downsamples[mask_level]
    # handle float downsample
    exp = max(1, int(np.ceil(cfg.DILATE_PX_LEVEL0 / down)))
    x0m = max(0, x0m - exp)
    y0m = max(0, y0m - exp)
    x1m = min(w - 1, x1m + exp)
    y1m = min(h - 1, y1m + exp)

    # map to level-0 pixel coordinates
    x0 = int(np.floor(x0m * down))
    y0 = int(np.floor(y0m * down))
    x1 = int(np.ceil((x1m + 1) * down))
    y1 = int(np.ceil((y1m + 1) * down))
    return mask_level, m, down, (x0, y0, x1, y1)
