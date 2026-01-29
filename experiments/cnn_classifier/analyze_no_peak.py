import csv

import numpy as np


def analyze_no_peak(csv_path):
    data = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(float(row["ink_ratio"]))

    ratios = np.array(data)
    min_ratio = 0.5

    # Find local maxima >= min_ratio
    # This replicates (ratios >= min_ratio) & (ratios >= roll(1)) & (ratios >= roll(-1))
    candidates = []

    # Naive local max
    for i in range(1, len(ratios) - 1):
        if ratios[i] >= min_ratio:
            if ratios[i] >= ratios[i - 1] and ratios[i] >= ratios[i + 1]:
                candidates.append(i)

    # Also check edges if needed, but usually 0

    print(f"Found {len(candidates)} candidates with ink >= {min_ratio} (No Peak Check).")
    return candidates


def main():
    csv_path = "logs/cnn_validation_eval2_user/debug_band0.csv"
    candidates = analyze_no_peak(csv_path)

    # Format for CLI
    x_cols = ",".join(map(str, candidates))
    print(f"X_COLS={x_cols}")


if __name__ == "__main__":
    main()
