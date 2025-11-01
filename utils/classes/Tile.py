"""
Class used to store information about a tile.
"""

from dataclasses import dataclass
from typing import Dict

@dataclass(frozen=True)
class Tile:
    id: int
    x: int
    y: int
    w: int
    h: int
    coverage: float

    def as_dict(self) -> Dict[str, int]:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "coverage": self.coverage
        }
