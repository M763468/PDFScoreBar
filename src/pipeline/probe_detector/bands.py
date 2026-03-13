"""Band preparation and divisi helpers for probe detection."""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import numpy as np

from .types import BandSelectionConfig, Box, DivisiRescueConfig


def cluster_by_y_distance(y_centers: np.ndarray, max_distance: float, min_cluster_size: int):
    sorted_indices = np.argsort(y_centers)
    sorted_y = y_centers[sorted_indices]
    clusters: List[List[int]] = []
    current_cluster = [int(sorted_indices[0])]
    for i in range(1, len(sorted_y)):
        if sorted_y[i] - sorted_y[i - 1] <= max_distance:
            current_cluster.append(int(sorted_indices[i]))
        else:
            clusters.append(current_cluster)
            current_cluster = [int(sorted_indices[i])]
    clusters.append(current_cluster)

    valid_clusters: Dict[int, List[int]] = {}
    noise: List[int] = []
    cluster_id = 0
    for cluster in clusters:
        if len(cluster) >= min_cluster_size:
            valid_clusters[cluster_id] = cluster
            cluster_id += 1
        else:
            noise.extend(cluster)
    return valid_clusters, noise


def build_row_stats(
    preds: Sequence[Box],
    cluster_max_dist: float | None = None,
    min_row_count: int = 3,
) -> List[Dict[str, float]]:
    if not preds:
        return []

    # Calculate median bbox height to use as physical reference
    heights = [abs(box[3] - box[1]) for box in preds if abs(box[3] - box[1]) > 0]
    median_h = float(np.median(heights)) if heights else 100.0

    # Default to 0.5 * median bbox height if not provided
    if cluster_max_dist is None:
        cluster_max_dist = median_h * 0.5

    y_centers = np.array([(box[1] + box[3]) / 2 for box in preds])
    rows, _ = cluster_by_y_distance(y_centers, cluster_max_dist, min_row_count)
    stats: List[Dict[str, float]] = []
    for indices in rows.values():
        if len(indices) < min_row_count:
            continue
        tops = [preds[i][1] for i in indices]
        bottoms = [preds[i][3] for i in indices]
        centers = [y_centers[i] for i in indices]
        stats.append(
            {
                "center": float(np.median(centers)),
                "top": float(np.median(tops)),
                "bottom": float(np.median(bottoms)),
            }
        )
    return stats


def staff_bands_from_mask(
    mask: np.ndarray,
    gap_tolerance: int = 1,
    min_height: int = 1,
) -> List[Tuple[int, int]]:
    rows = np.where(mask.sum(axis=1) > 0)[0]
    if rows.size == 0:
        return []

    # First pass: keep the original row-segment extraction behavior.
    segments: List[Tuple[int, int]] = []
    start = int(rows[0])
    prev = int(rows[0])
    for y in rows[1:]:
        if int(y) - prev <= gap_tolerance:
            prev = int(y)
            continue
        if prev - start + 1 >= min_height:
            segments.append((start, prev))
        start = int(y)
        prev = int(y)
    if prev - start + 1 >= min_height:
        segments.append((start, prev))

    if len(segments) <= 1:
        return segments

    h, w = mask.shape[:2]

    # Second pass: if the mask looks line-like (thin staff-line segments), merge
    # adjacent segments into full staff-region bands. This prevents severe
    # fragmentation when `staff_mask` is actually a line mask (e.g. debug_3_staff).
    heights = np.array([y2 - y1 + 1 for y1, y2 in segments], dtype=np.float32)
    gaps = np.array(
        [segments[i + 1][0] - segments[i][1] - 1 for i in range(len(segments) - 1)],
        dtype=np.float32,
    )
    positive_gaps = gaps[gaps > 0]
    if positive_gaps.size == 0:
        return segments

    med_h = float(np.median(heights))
    med_gap = float(np.median(positive_gaps))

    # Region masks already form thick bands. We only apply the merge heuristic
    # when the mask looks like a stack of many thin/medium line segments
    # (typical for debug_3_staff outputs), not pre-merged staff regions.
    #
    # Use a staff-step proxy from the mask itself (median row gap) instead of
    # fixed pixel thresholds so the heuristic scales with resolution.
    staff_step_proxy = max(1.0, med_gap)
    line_like = (
        len(segments) >= 5 and med_h <= (3.0 * staff_step_proxy) and med_gap <= (0.05 * float(h))
    )
    if not line_like:
        return segments

    merge_gap = max(gap_tolerance + 1, int(round(med_gap * 1.8)))
    # Segment metadata is used to drop non-staff horizontal fragments after merging.
    seg_meta = []
    for y1, y2 in segments:
        band = mask[y1 : y2 + 1, :]
        xs = np.where(band.sum(axis=0) > 0)[0]
        if xs.size == 0:
            x1 = x2 = 0
            width = 0
        else:
            x1 = int(xs.min())
            x2 = int(xs.max())
            width = int(x2 - x1 + 1)
        seg_meta.append({"y1": y1, "y2": y2, "x1": x1, "x2": x2, "w": width})

    merged: List[Tuple[int, int]] = []
    current_group = [seg_meta[0]]
    for next_seg in seg_meta[1:]:
        gap = next_seg["y1"] - current_group[-1]["y2"] - 1
        if gap <= merge_gap:
            current_group.append(next_seg)
            continue

        _append_if_staff_like(current_group, merged, min_height=min_height, image_w=w)
        current_group = [next_seg]

    _append_if_staff_like(current_group, merged, min_height=min_height, image_w=w)
    return merged


def _append_if_staff_like(
    group: List[dict[str, int]],
    out: List[Tuple[int, int]],
    *,
    min_height: int,
    image_w: int,
) -> None:
    if not group:
        return
    # Require multiple horizontally long lines to avoid treating random
    # non-staff horizontal fragments as staff bands.
    line_count = len(group)
    long_line_thresh = int(round(image_w * 0.30))
    long_line_count = sum(1 for seg in group if seg["w"] >= long_line_thresh)
    # Relaxed criteria: 3+ total segments and 2+ long segments to allow for divisi/fragments
    if line_count < 3 or long_line_count < 2:
        return

    y1 = int(group[0]["y1"])
    y2 = int(group[-1]["y2"])
    if y2 - y1 + 1 >= min_height:
        out.append((y1, y2))


def scan_staff_band_from_ink(
    ink: np.ndarray,
    x_center: int,
    y1: int,
    y2: int,
    scan_width: int,
    line_ratio: float,
    min_lines: int,
    gap_tolerance: int = 1,
) -> Tuple[int, int] | None:
    """Estimate staff band by horizontal scan around x_center within [y1, y2]."""
    h, w = ink.shape[:2]
    x1 = max(0, int(x_center - scan_width // 2))
    x2 = min(w - 1, int(x_center + scan_width // 2))
    if x2 <= x1 or y2 <= y1:
        return None
    strip = ink[y1 : y2 + 1, x1 : x2 + 1]
    if strip.size == 0:
        return None
    row_ratio = strip.sum(axis=1) / float(strip.shape[1])
    rows = np.where(row_ratio >= line_ratio)[0]
    if rows.size == 0:
        return None
    groups = []
    start = int(rows[0])
    prev = int(rows[0])
    for r in rows[1:]:
        if int(r) - prev <= gap_tolerance:
            prev = int(r)
            continue
        groups.append((start, prev))
        start = int(r)
        prev = int(r)
    groups.append((start, prev))
    if len(groups) < min_lines:
        return None
    best = None
    for i in range(0, len(groups) - min_lines + 1):
        j = i + min_lines - 1
        span = groups[j][1] - groups[i][0]
        mean_ratio = float(row_ratio[groups[i][0] : groups[j][1] + 1].mean())
        if best is None or span < best[0] or (span == best[0] and mean_ratio > best[1]):
            best = (span, mean_ratio, i, j)
    if best is None:
        return None
    _, _, i, j = best
    top = y1 + groups[i][0]
    bottom = y1 + groups[j][1]
    if bottom < top:
        return None
    return (int(top), int(bottom))


def resolve_bands(
    *,
    staff_mask: np.ndarray,
    existing_boxes: Sequence[Box],
    row_stats: Sequence[Dict[str, float]] | None,
    config: BandSelectionConfig,
) -> List[Tuple[int, int]]:
    if config.band_source in ("existing_boxes", "horiz_scan", "row_stats"):
        if config.band_source == "row_stats" and row_stats is not None:
            return [
                (int(stat["top"]), int(stat["bottom"]))
                for stat in row_stats
                if stat["bottom"] >= stat["top"]
            ]
        row_stats_local = build_row_stats(
            existing_boxes, config.band_cluster_max_dist, config.band_min_row_count
        )
        return [
            (int(stat["top"]), int(stat["bottom"]))
            for stat in row_stats_local
            if stat["bottom"] >= stat["top"]
        ]
    return staff_bands_from_mask(staff_mask)


def build_divisi_map(
    *,
    ink: np.ndarray,
    bands: Sequence[Tuple[int, int]],
    existing_boxes: Sequence[Box],
    kernel: np.ndarray,
    width: int,
    image_h: int,
    global_height: int,
    config: DivisiRescueConfig,
) -> Dict[int, Dict[str, bool]]:
    divisi_map: Dict[int, Dict[str, bool]] = {}
    if not config.enabled or len(bands) <= 1:
        return divisi_map

    adj_groups = []
    b_heights = [y2 - y1 + 1 for y1, y2 in bands]
    avg_h = float(np.mean(b_heights)) if b_heights else float(global_height)
    dist_thresh = avg_h * config.dist_ratio

    current_group = [0]
    for i in range(1, len(bands)):
        prev_y2 = bands[i - 1][1]
        curr_y1 = bands[i][0]
        dist = curr_y1 - prev_y2
        if dist < dist_thresh:
            current_group.append(i)
        else:
            if len(current_group) > 1:
                adj_groups.append(current_group)
            current_group = [i]
    if len(current_group) > 1:
        adj_groups.append(current_group)

    band_xs: Dict[int, List[float]] = {i: [] for i in range(len(bands))}
    for bx1, by1, bx2, by2 in existing_boxes:
        cy = (by1 + by2) / 2.0
        cx = (bx1 + bx2) / 2.0
        best_bi = -1
        best_dy = float("inf")
        for i, (by1_b, by2_b) in enumerate(bands):
            if by1_b <= cy <= by2_b:
                band_xs[i].append(cx)
                best_bi = -1
                break
            dy = min(abs(cy - by1_b), abs(cy - by2_b))
            if dy < best_dy:
                best_dy = dy
                best_bi = i
        if best_bi != -1:
            band_xs[best_bi].append(cx)

    for i, (y1, y2) in enumerate(bands):
        band_center = int(round((y1 + y2) / 2))
        band_h = max(1, y2 - y1 + 1)
        target_h = band_h
        if config.band_source == "row_stats":
            band_y1, band_y2 = y1, y2
        else:
            if config.band_height_mode == "median_box":
                target_h = band_h
            band_y1 = max(0, int(band_center - target_h // 2))
            band_y2 = min(image_h - 1, int(band_center + target_h // 2))

        band_img = ink[band_y1 : band_y2 + 1, :]
        if band_img.size == 0:
            continue

        col_sums = band_img.sum(axis=0)
        stripe_sums = np.convolve(col_sums, kernel, mode="same")
        ratios = stripe_sums / float(max(1, band_y2 - band_y1 + 1) * width)

        divisi_min_ratio = config.min_ratio
        if ratios.size < 3:
            continue
        peak_indices = np.where(
            (ratios >= divisi_min_ratio)
            & (ratios >= np.roll(ratios, 1))
            & (ratios >= np.roll(ratios, -1))
        )[0]
        for px in peak_indices:
            band_xs[i].append(float(px))

    for grp in adj_groups:
        for k in range(len(grp) - 1):
            idx_a = grp[k]
            idx_b = grp[k + 1]
            xs_a = sorted(band_xs[idx_a])
            xs_b = sorted(band_xs[idx_b])
            match_count = 0
            for xa in xs_a:
                for xb in xs_b:
                    if abs(xa - xb) <= config.align_tol:
                        match_count += 1
                        break
            if match_count >= config.align_min_count:
                if idx_a not in divisi_map:
                    divisi_map[idx_a] = {"has_top": False, "has_bottom": False}
                if idx_b not in divisi_map:
                    divisi_map[idx_b] = {"has_top": False, "has_bottom": False}
                divisi_map[idx_a]["has_bottom"] = True
                divisi_map[idx_b]["has_top"] = True

    return divisi_map
