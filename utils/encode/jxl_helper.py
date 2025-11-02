"""
Helper functions used in encoding.
"""

import openslide
from typing import Tuple
from utils.classes.Tile import Tile
from skimage.metrics import structural_similarity as ssim
from config import JxlConfig
import numpy as np

# ---------------------- General Helpers --------------------- #

def raw_bytes(w: int, h: int, channels: int = 3, bytes_per_channel: int = 1) -> int:
    """3 bytes/pixel for 8-bit RGB."""
    return int(w) * int(h) * int(channels) * int(bytes_per_channel)

def read_tile_rgb(slide: openslide.OpenSlide, t: Tile) -> np.ndarray:
    """OpenSlide returns RGBA; convert to RGB, uint8"""
    region = slide.read_region((t.x, t.y), 0, (t.w, t.h)).convert("RGB")
    arr = np.asarray(region, dtype=np.uint8)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"Unexpected tile shape: {arr.shape}")
    return arr

def ssim_rgb(ref: np.ndarray, test: np.ndarray) -> float:
    return float(ssim(ref, test, channel_axis=2, data_range=255))


# ---------------------- Finding the optimal distance --------------------- #
def search_distance_for_ssim(
        rgb: np.ndarray,
        target: float,
        tol: float,
        cfg: JxlConfig

) -> Tuple[float, float, float]:
    """
    Find the largest JPEG XL `--distance` (i.e., most compression) whose decoded image
    still meets SSIM >= target - tol vs the original `rgb`.
    """

    # ---------------- Validation of inputs ----------------- #
    # @TODO

    lo, hi = float(cfg.DIST_MIN), float(cfg.DIST_MAX)

    # Best candidate that meets the SSIM gate, None if not met
    best_d: float | None = None
    best_blob: bytes | None = None
    best_s: float = 0.0