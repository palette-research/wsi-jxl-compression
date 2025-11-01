"""
Helper functions for the mask directory.
"""

# --------- Packages -------------
import openslide

# --------- Functions -------------
def get_slide_dimensions(slide: openslide.OpenSlide, level: int = 0):
    """
    Returns the dimensions of the slide.

    :param slide:
    :param level:
    :return: W, H
    """
    return slide.level_dimensions[level]