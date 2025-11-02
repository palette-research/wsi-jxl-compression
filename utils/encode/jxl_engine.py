"""
Logic for encoding a tile using the JXL encoding algorithm.
"""
import openslide

from config import EncoderConfig, JxlConfig
from utils.classes.Tile import Tile

from typing import List
import shutil

from utils.encode.jxl_helper import (
    search_distance_for_ssim,
    read_tile_rgb,
    raw_bytes
)

def jxl_encode_and_store(
        slide_path: str,
        tiles: List[Tile],
        cfg_e: EncoderConfig,
        cfg_jxl: JxlConfig

):
    for b in (cfg_jxl.CJXL_BIN, cfg_jxl.DJXL_BIN):
        if shutil.which(b) is None:
            raise FileNotFoundError(f"Required binary not found in PATH: {b}")


    slide = openslide.OpenSlide(slide_path)
    try:

        # Defining a worker
        def worker(t: Tile):

            # Checking if the tile has already been treated
            # @TODO

            rgb = read_tile_rgb(slide, t)
            rawb = raw_bytes(t.w, t.h)

            # Searching for the distance that assures SSIM >= visually lossless
            d, b, d = search_distance_for_ssim(
                rgb,
                cfg_e.SSIM_TARGET,
                cfg_e.SSIM_TOL,
                cfg_jxl
            )













    finally:
        slide.close()



