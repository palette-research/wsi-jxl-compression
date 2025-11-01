"""
Mask class.
"""

from dataclasses import dataclass
import numpy as np

@dataclass (frozen=True)
class Mask:
    level: int
    mask: np.ndarray
    downsample: float
    bbox_level0: tuple[int, int, int, int]
    coverage: float


