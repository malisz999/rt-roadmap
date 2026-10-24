"""Colouring: palette, adjacency and DSATUR (pure)."""

from rt.color.adjacency import lane_indices, neighbours
from rt.color.dsatur import assign_colors, assign_keys
from rt.color.palette import PALETTE, custom_color, palette_ref
from rt.color.types import ColorRef

__all__ = [
    "PALETTE",
    "ColorRef",
    "assign_colors",
    "assign_keys",
    "custom_color",
    "lane_indices",
    "neighbours",
    "palette_ref",
]
