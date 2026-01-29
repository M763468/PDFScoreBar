import json


def main():
    json_path = "logs/experiments/verify_divisi_page004_v2.json"
    with open(json_path) as f:
        data = json.load(f)

    page = data["pages"][0]

    # Flatten staves to reconstruct the input list for the builder
    all_staves = []
    for sys_idx, system in enumerate(page["systems"]):
        for staff in system["staves"]:
            # We need to re-attach barlines to staves.
            # In the output JSON, measures have barlines, but staves don't explicitly list them in the simple visualizer format usually.
            # Wait, the add_measure_numbers.py output (score_to_dict) puts barlines inside staves?
            # checking add_measure_numbers.py... no, it puts staves (bbox) and measures (number, bbox).
            # It does NOT output barlines per staff in the staves list in score_to_dict.
            # However, the input barlines are available in the JSON? No.
            # But we can infer barline positions from measures (start_bar/end_bar logic is lost in JSON output which only has measure bbox).
            # Actually measure bbox x1/x2 are effectively barlines.
            all_staves.append(
                {
                    "sys_group": sys_idx,
                    "bbox": staff["bbox"],
                    "measures": system[
                        "measures"
                    ],  # These belong to snake-wise flow but roughly align strictly vertical for systems
                }
            )

    # Sort by Y
    all_staves.sort(key=lambda s: s["bbox"][1])

    # Re-calculate parameters
    heights = [s["bbox"][3] - s["bbox"][1] for s in all_staves]
    avg_height = sum(heights) / len(heights)
    DIVISI_DIST_RATIO = 1.5
    dist_threshold = avg_height * DIVISI_DIST_RATIO

    print(f"Avg Height: {avg_height:.2f}")
    print(f"Dist Threshold: {dist_threshold:.2f}")

    print("\n--- Pairwise Analysis ---")
    for i in range(len(all_staves) - 1):
        s1 = all_staves[i]
        s2 = all_staves[i + 1]

        y1_bot = s1["bbox"][3]
        y2_top = s2["bbox"][1]
        gap = y2_top - y1_bot

        # Collect 'barlines' from measures for alignment check
        # Approximation: Measure x1 and x2 are potential barlines.
        # Note: system["measures"] are shared for the system, but we need to know which ones align.
        # In the implemented builder, we used explicit Barline objects assigned to staves.
        # Since I can't easily reconstruct that exact assignment from the output JSON alone without re-running,
        # I'll output the GAP information which is likely the primary culprit.

        grouped = s1["sys_group"] == s2["sys_group"]

        status = " [GROUPED]" if grouped else " [SEPARATE]"
        gap_judge = "PASS" if gap <= dist_threshold else "FAIL"

        print(
            f"Staff {i + 1} -> {i + 2}: Gap={gap} (Thresh={dist_threshold:.2f}) -> DistCheck={gap_judge}{status}"
        )

        if grouped:
            print(f"    (Grouped in System {s1['sys_group']})")


if __name__ == "__main__":
    main()
