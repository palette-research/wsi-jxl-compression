"""
Helper functions used in encoding.
"""

import openslide
from typing import Tuple
from utils.classes.Tile import Tile
from skimage.metrics import structural_similarity as ssim
from config import JxlConfig
import numpy as np

import tempfile
import subprocess
import os
from PIL import Image
import time

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

def tile_fname(t: Tile) -> str:
    return f"x_{t.x}_y_{t.y}_w_{t.w}_h_{t.h}.jxl"
# ---------------------- Encode helper --------------------- #
def encode_jxl_bytes_from_rgb(rgb: np.ndarray, distance: float, effort: int = 7) -> bytes:
    """
    Encode an RGB uint8 array to JXL bytes via `cjxl`. Uses a lossless temporary PNG for compatibility.

    Imported from pathology-compression project.
    """
    # Assertion and setup
    assert rgb.dtype == np.uint8 and rgb.ndim == 3 and rgb.shape[2] == 3
    jxl_path = None

    # Writes a temporary PNG from the provided RGB array
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as pngf:
        png_path = pngf.name
        Image.fromarray(rgb, mode="RGB").save(png_path, format="PNG", optimize=False)

    try:
        # Creates a temporary .jxl file
        with tempfile.NamedTemporaryFile(suffix=".jxl", delete=False) as jxlf:
            jxl_path = jxlf.name

        # Constructs the jxl command: https://github.com/libjxl/libjxl?tab=readme-ov-file
        cmd = [
            "cjxl", png_path, jxl_path,
            "--distance", f"{float(distance)}",
            "-e", f"{int(effort)}",
            "--quiet",
        ]

        # Create a subprocess and run the command
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Return JXl byte string s.t. we can do: cr = w*h*3 / len(jxl_bytes)
        with open(jxl_path, "rb") as f:
            return f.read()
    finally:
        # Delete temporary files
        if png_path:
            try: os.remove(png_path)
            except OSError: pass
        if jxl_path and os.path.exists(jxl_path):
            try: os.remove(jxl_path)
            except OSError: pass

# ---------------------- Decode helper --------------------- #
def decode_jxl_bytes_to_rgb(jxl_bytes: bytes) -> np.ndarray:
    """Decode JXL bytes to RGB uint8 via `djxl` -> PNG temp (lossless intermediate)."""
    # Create a temporary .jxl file and write in the provided jxl_bytes
    with tempfile.NamedTemporaryFile(suffix=".jxl", delete=False) as jxlf:
        jxl_path = jxlf.name
        jxlf.write(jxl_bytes)
        jxlf.flush()

    # Create a temporary .png file
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as pngf:
        png_path = pngf.name

    try:
        # Create a command to decode: https://github.com/libjxl/libjxl?tab=readme-ov-file
        cmd = [
            "djxl",
            jxl_path,
            png_path,
            "--quiet"
        ]

        # Run the command
        subprocess.run(cmd,
                       check=True,
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)

        # Reads the decoded PNG and return it as a numpy array h*w*3
        rec = Image.open(png_path).convert("RGB")
        return np.asarray(rec, dtype=np.uint8)
    finally:
        # Remove temporary files
        for p in (jxl_path, png_path):
            if p:
                try: os.remove(p)
                except OSError: pass

# ---------------------- Finding the optimal distance --------------------- #
def search_distance_for_ssim(
        rgb: np.ndarray,
        target: float,
        tol: float,
        cfg: JxlConfig
) -> Tuple[float, bytes, float, float, float]:
    """
    Find the largest JPEG XL `--distance` (i.e., most compression) whose decoded image
    still meets SSIM >= target - tol vs the original `rgb`.
    """
    # ---------------- Validation of inputs ----------------- #
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"Expected RGB (H,W,3), got {rgb.shape}")
    if not (0.0 < target <= 1.0) or tol < 0:
        raise ValueError("Invalid SSIM target/tol")

    # ---------------- Preparation of data ----------------- #
    lo, hi = float(cfg.DIST_MIN), float(cfg.DIST_MAX)

    # Best candidate that meets the SSIM gate, None if not met
    distance: float | None = None
    encoded_bytes: bytes | None = None
    enc_ms: float | None = None
    dec_ms: float | None = None
    similarity: float = 0.0

    for it in range(cfg.MAX_ITERS):
        mid = 0.5 * (lo + hi)

        # Encode at the trial distance
        t0 = time.perf_counter()
        encoded = encode_jxl_bytes_from_rgb(
            rgb,
            distance=mid,
            effort=cfg.EFFORT
        )
        enc_ms = (time.perf_counter() - t0) * 1000.0

        t1 = time.perf_counter()
        # Decode at the trial distance
        decoded = decode_jxl_bytes_to_rgb(encoded)
        dec_ms = (time.perf_counter() - t1) * 1000.0

        # Measure the structural similarity
        s = ssim_rgb(
            rgb,
            decoded
        )

        if s >= (target - tol):
            distance, encoded_bytes, similarity = mid, encoded, s
            lo = mid
        else:
            hi = mid

        if (hi - lo) < cfg.STOP_EPS:
            break

    if encoded_bytes is not None:
        return float(distance), encoded_bytes, float(similarity), float(enc_ms), float(dec_ms)
