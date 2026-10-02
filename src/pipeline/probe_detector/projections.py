"""Project ink across staff bands and their optional extension regions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .bands import compute_domain_ratios
from .types import BandProjectionConfig, Box


@dataclass(frozen=True)
class BandProjection:
    scan_base_y1: int
    scan_base_y2: int
    band_y1: int
    band_y2: int
    band_h: int
    ratios: np.ndarray
    ext_ratios: np.ndarray | None
    ext_top_ratios: np.ndarray | None
    ext_bottom_ratios: np.ndarray | None
    ext_y1: int | None
    ext_y2: int | None
    top_h: int
    bottom_h: int
    projected_columns: int


def project_staff_band(
    ink: np.ndarray,
    *,
    y1: int,
    y2: int,
    existing_boxes: Sequence[Box],
    global_height: int,
    kernel: np.ndarray,
    width: int,
    x_domain: tuple[int, int],
    config: BandProjectionConfig,
) -> BandProjection:
    h, w = ink.shape[:2]
    domain_x1, domain_x2 = x_domain
    scan_base_y1 = y1
    scan_base_y2 = y2
    if config.band_source == "horiz_scan":
        if config.band_scan_pad_ratio > 0:
            pad = int(round((y2 - y1 + 1) * config.band_scan_pad_ratio))
        else:
            pad = int(config.band_scan_pad)
        if pad > 0:
            scan_base_y1 = max(0, int(y1) - pad)
            scan_base_y2 = min(h - 1, int(y2) + pad)
    band_center = int(round((y1 + y2) / 2))
    band_h = max(1, y2 - y1 + 1)
    if config.band_source == "row_stats":
        band_y1 = max(0, int(y1))
        band_y2 = min(h - 1, int(y2))
        pad = 0
        if config.band_row_pad_ratio > 0:
            pad = int(round((band_y2 - band_y1 + 1) * config.band_row_pad_ratio))
        elif config.band_row_pad_staff_mult > 0 and config.staff_space > 0:
            pad = int(round(config.staff_space * config.band_row_pad_staff_mult))
        if pad > 0:
            band_y1 = max(0, band_y1 - pad)
            band_y2 = min(h - 1, band_y2 + pad)
    else:
        if config.band_height_mode == "median_box":
            heights = [
                abs(by2 - by1)
                for _, by1, _, by2 in existing_boxes
                if y1 <= (by1 + by2) / 2.0 <= y2 and abs(by2 - by1) > 0
            ]
            median_h = int(np.median(heights)) if heights else global_height
            target_h = (
                max(config.band_height_min, int(round(median_h * config.band_height_scale)))
                if median_h
                else band_h
            )
        else:
            target_h = band_h
        band_y1 = max(0, int(band_center - target_h // 2))
        band_y2 = min(h - 1, int(band_center + target_h // 2))
    band = ink[band_y1 : band_y2 + 1, :]
    band_h = max(1, band_y2 - band_y1 + 1)
    target_h = band_h
    ext_band = None
    ext_ratios = None
    ext_top_ratios = None
    ext_bottom_ratios = None
    ext_y1 = None
    ext_y2 = None
    top_h = 0
    bottom_h = 0
    if config.extend_scale > 1.0:
        ext_h = max(band_h, int(round(target_h * config.extend_scale)))
        ext_y1 = max(0, int(round(band_center - ext_h / 2)))
        ext_y2 = min(h - 1, int(round(band_center + ext_h / 2)))
        ext_band = ink[ext_y1 : ext_y2 + 1, :]
    ratios, projected = compute_domain_ratios(
        band,
        kernel=kernel,
        width=width,
        image_width=w,
        x_domain=(domain_x1, domain_x2),
    )
    if ext_band is not None and ext_y1 is not None and ext_y2 is not None:
        ext_ratios, _ = compute_domain_ratios(
            ext_band,
            kernel=kernel,
            width=width,
            image_width=w,
            x_domain=(domain_x1, domain_x2),
        )
        top_h = max(0, band_y1 - ext_y1)
        bottom_h = max(0, ext_y2 - band_y2)
        if top_h > 0:
            top_band = ink[ext_y1:band_y1, :]
            ext_top_ratios, _ = compute_domain_ratios(
                top_band,
                kernel=kernel,
                width=width,
                image_width=w,
                x_domain=(domain_x1, domain_x2),
            )
        if bottom_h > 0:
            bottom_band = ink[band_y2 + 1 : ext_y2 + 1, :]
            ext_bottom_ratios, _ = compute_domain_ratios(
                bottom_band,
                kernel=kernel,
                width=width,
                image_width=w,
                x_domain=(domain_x1, domain_x2),
            )
    return BandProjection(
        scan_base_y1=scan_base_y1,
        scan_base_y2=scan_base_y2,
        band_y1=band_y1,
        band_y2=band_y2,
        band_h=band_h,
        ratios=ratios,
        ext_ratios=ext_ratios,
        ext_top_ratios=ext_top_ratios,
        ext_bottom_ratios=ext_bottom_ratios,
        ext_y1=ext_y1,
        ext_y2=ext_y2,
        top_h=top_h,
        bottom_h=bottom_h,
        projected_columns=projected,
    )
