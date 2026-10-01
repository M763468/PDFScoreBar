"""Select projected ink peaks in stable score order within the x domain."""

from __future__ import annotations

import numpy as np


def select_signal_peaks(
    ratios: np.ndarray,
    *,
    effective_min: float,
    domain_x1: int,
    domain_x2: int,
    min_peak_distance: int,
    max_per_band: int,
) -> tuple[int, list[tuple[int, float]]]:
    peaks = np.where(
        (ratios >= effective_min) & (ratios >= np.roll(ratios, 1)) & (ratios >= np.roll(ratios, -1))
    )[0]
    peaks = peaks[(peaks >= domain_x1) & (peaks <= domain_x2)]
    peak_scores = [(int(x), float(ratios[x])) for x in peaks]
    peak_scores.sort(key=lambda item: item[1], reverse=True)
    selected: list[tuple[int, float]] = []
    for x, score in peak_scores:
        if any(abs(x - sx) < min_peak_distance for sx, _ in selected):
            continue
        selected.append((x, score))
        if max_per_band > 0 and len(selected) >= max_per_band:
            break
    return int(peaks.size), selected
