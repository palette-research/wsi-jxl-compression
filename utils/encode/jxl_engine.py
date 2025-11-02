"""
Logic for encoding tiles to JXL and writing them + a manifest to disk.
"""

import csv
import logging
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import openslide

from config import EncoderConfig, JxlConfig
from utils.classes.Tile import Tile
from utils.encode.jxl_helper import (
    read_tile_rgb,
    raw_bytes,
    tile_fname,
    search_distance_for_ssim,  # returns (distance, encoded_bytes, ssim, enc_ms, dec_ms)
)

log = logging.getLogger(__name__)

def jxl_encode_and_store(
    slide_path: str,
    tiles: List[Tile],
    cfg_e: EncoderConfig,
    cfg_jxl: JxlConfig,
) -> None:
    """
    Encode tiles and stream-write to a timestamped folder + manifest.csv (thread-safe, atomic).
    Assumes `search_distance_for_ssim` returns the chosen artifact bytes + timings.

    :param slide_path:
    :param tiles:
    :param cfg_e:
    :param cfg_jxl:
    :return:
    """

    # ----------------- Preflight: ensure binaries in PATH ----------------- #
    # NOTE: helpers call 'cjxl'/'djxl' directly; ensure those names exist.
    for b in ("cjxl", "djxl"):
        if shutil.which(b) is None:
            raise FileNotFoundError(f"Required binary not found in PATH: {b}")

    # ----------------- Output layout ------------------------------------- #
    # Expect cfg_e to provide OUT_DIR; we create a timestamped run folder.
    out_root = Path(cfg_e.OUT_DIR)
    out_root.mkdir(parents=True, exist_ok=True)
    run_dir = out_root / datetime.now().strftime("%Y%m%dT%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    # Lifecycle marker in the *run_dir* (not the root)
    (run_dir / ".INPROGRESS").write_text("encoding\n")

    # Manifest rows (append from worker threads under a lock)
    rows: List[Dict] = []
    rows_lock = threading.Lock()

    # OpenSlide handle
    slide = openslide.OpenSlide(slide_path)
    read_lock = threading.Lock()


    try:
        def worker(t: Tile) -> Optional[str]:
            """
            Worker that:
              - reads the RGB tile
              - searches JXL distance to meet SSIM gate (returns final bytes)
              - atomically writes .jxl
              - records metrics row for manifest
            """
            dst = run_dir / tile_fname(t)
            if dst.exists():
                return "skipped"

            log.info("Tile %d START  @ (%d,%d) %dx%d", t.id, t.x, t.y, t.w, t.h)

            # Read tile (guard OpenSlide access)
            with read_lock:
                rgb = read_tile_rgb(slide, t)
            rawb = raw_bytes(t.w, t.h)

            # Search distance (single chosen artifact; timings for chosen candidate only)
            dist, blob, ssim_val, enc_ms, dec_ms = search_distance_for_ssim(
                rgb=rgb,
                target=cfg_e.SSIM_TARGET,
                tol=cfg_e.SSIM_TOL,
                cfg=cfg_jxl,
            )

            # Compression ratio
            enc_len = len(blob)
            cr = rawb / max(1, enc_len)

            # Atomic write
            tmp = dst.with_suffix(dst.suffix + ".tmp")
            with open(tmp, "wb") as f:
                f.write(blob)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, dst)

            log.info("Tile %d DONE   dist=%.3f ssim=%.4f cr=%.2f enc_ms=%.1f dec_ms=%.1f out=%s",
                     t.id, dist, ssim_val, cr, enc_ms, dec_ms, dst.name)

            # Manifest row
            row = {
                "tile_id": t.id,
                "x": t.x, "y": t.y, "w": t.w, "h": t.h,
                "distance_encoded": float(dist),
                "ssim": float(ssim_val),
                "raw_bytes": int(rawb),
                "enc_bytes": int(enc_len),
                "cr": float(cr),
                "enc_ms": float(enc_ms),  # encode time of chosen artifact only
                "dec_ms": float(dec_ms),  # decode time of chosen artifact only
                "relpath": str(dst.relative_to(run_dir)),
            }
            with rows_lock:
                rows.append(row)
            return "written"

        # ----------------- Parallel execution ----------------------------- #
        written = skipped = errors = 0
        with ThreadPoolExecutor(max_workers=cfg_e.WORKERS) as ex:
            futs = {ex.submit(worker, t): t.id for t in tiles}
            for fut in as_completed(futs):
                tid = futs[fut]
                try:
                    status = fut.result()
                    if status == "written":
                        written += 1
                    else:
                        skipped += 1
                except Exception as e:
                    errors += 1
                    log.exception("Tile %d failed: %s", tid, e)

        # ----------------- Write manifest once ---------------------------- #
        if rows:
            manifest = run_dir / "manifest.csv"
            with open(manifest, "w", newline="") as f:
                fieldnames = list(rows[0].keys())
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(rows)

        # ----------------- Status flag & summary -------------------------- #
        p = run_dir / ".INPROGRESS"
        if p.exists():
            p.rename(run_dir / ".DONE")

        log.info(
            "JXL encode+store | written=%d skipped=%d errors=%d | out=%s",
            written, skipped, errors, str(run_dir),
        )

    finally:
        slide.close()
