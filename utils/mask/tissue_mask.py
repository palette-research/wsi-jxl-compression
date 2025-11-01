"""

"""

# --------- Packages -------------
from utils.mask.mask_helpers import (
    get_slide_dimensions
)

from utils.classes.Tile import Tile

import openslide

# --------- Functions -------------
def make_tissue_mask(
  slide_path: str
) -> Tile:
    """

    :param slide_path:
    :return:
    """

    # --------- Setup -------------
    slide = openslide.OpenSlide(slide_path) # opening the slide
    W0, H0 = get_slide_dimensions(slide, 0) # retrieving the slide dimensions

    print(f"Width: {W0}, Height: {H0}")



