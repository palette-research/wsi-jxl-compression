"""
Logic for encoding tiles to JXL and writing them + a manifest to disk.
"""
import threading
import time
from asyncio import as_completed
from concurrent.futures.thread import ThreadPoolExecutor

import openslide

from config import EncoderConfig, JxlConfig
from utils.classes.Tile import Tile

from typing import List, Optional
import shutil
from pathlib import Path

from utils.encode.jxl_helper import (
    encode_jxl_bytes_from_rgb,
    search_distance_for_ssim,
    read_tile_rgb,
    raw_bytes, decode_jxl_bytes_to_rgb,
    tile_fname
)
from typing import Dict
import logging
log = logging.getLogger(__name__)

def jxl_encode_and_store(
        slide_path: str,
        tiles: List[Tile],
        cfg_e: EncoderConfig,
        cfg_jxl: JxlConfig

):
    """
    Encode tiles and stream-write to a folder + manifest.csv (thread-safe, atomic).

    :param slide_path:
    :param tiles:
    :param cfg_e:
    :param cfg_jxl:
    :return:
    """

    # --------------- Ensure all required packages are available -------------- #
    for b in (cfg_jxl.CJXL_BIN, cfg_jxl.DJXL_BIN):
        if shutil.which(b) is None:
            raise FileNotFoundError(f"Required binary not found in PATH: {b}")

    # ---------------------- Setup ------------------------ #

    # Making the directory to store the encoded tiles
    bundle = Path(cfg_e.OUT_DIR)
    t = time.time()
    tiles_dir = bundle / f"{t}"
    bundle.mkdir(parents=True, exist_ok=True)
    tiles_dir.mkdir(parents=True, exist_ok=True)

    (bundle / ".INPROGRESS").write_text("encoding\n")

    # Variables for the manifest
    rows: List[Dict] = []
    rows_lock = threading.Lock()

    # ---------------------- Main ------------------------ #

    slide = openslide.OpenSlide(slide_path)
    try:

        # Defining a worker
        def worker(t: Tile) -> Optional[str]

            # Creating destination
            dst = tiles_dir / tile_fname(t)

            # Checking if the tile has already been treated
            if dst.exists():
                return f"[{time.time()}][JXL] Skipped: {t.id}"

            # Read
            rgb = read_tile_rgb(slide, t)
            rawb = raw_bytes(t.w, t.h)

            # TODO We do all the encode and decode logic in search_distance_for_ssim




















            # Retrieving statistics
            enc_len = len(encoded_bytes)
            cr = rawb / max(1, enc_len)

            # Writing the tile to memory
            # TODO

            # For testing, remove for prod
            print(f"")

            # Encoding all tiles
            skipped = 0
            errors = 0

            with ThreadPoolExecutor(cfg_e.WORKERS) as ex:
                futs = {
                    ex.submit(worker, t): t.id for t in tiles
                }
                for fut in as_completed(futs):
                    try:
                        r = fut.result()
                        if r is None:
                            skipped += 1
                        else:
                            # TODO Write to file
                    except Exception as e:
                        errors += 1
                        log.exception("Tile %d failed: %s", futs[fut], e)

            log.info("JXL encode+store | skipped=%d | errors=%d", skipped, errors)
    finally:
        slide.close()



