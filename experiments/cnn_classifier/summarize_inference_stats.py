
import argparse
import json
from pathlib import Path
from tqdm import tqdm

def summarize(json_root, name):
    files = list(Path(json_root).glob("*_scored.json"))
    stats = []
    for f in files:
        with open(f, 'r') as fp:
            data = json.load(fp)
        
        total = len(data)
        barlines = sum(1 for x in data if x['label'] == 'barline')
        fps = total - barlines
        
        run_id = f.stem.replace("_scored", "")
        stats.append({
            "run_id": run_id,
            "total": total,
            "barline": barlines,
            "fp": fps,
            "ratio": barlines / total if total > 0 else 0
        })
    
    if not stats:
        print(f"[{name}] No data found.")
        return

    total_candidates = sum(s['total'] for s in stats)
    total_barlines = sum(s['barline'] for s in stats)
    total_fps = sum(s['fp'] for s in stats)
    mean_total = total_candidates / len(stats)
    mean_barline = total_barlines / len(stats)
    mean_fp = total_fps / len(stats)
    mean_ratio = float(total_barlines) / total_candidates if total_candidates > 0 else 0

    print(f"--- {name} Summary ---")
    print(f"Mean Total Candidates: {mean_total:.1f}")
    print(f"Mean Accepted (Barline): {mean_barline:.1f}")
    print(f"Mean Rejected (FP): {mean_fp:.1f}")
    print(f"Overall Acceptance Ratio: {mean_ratio:.2%}")
    print("-" * 20)
    # Top 5 busiest pages (most candidates)
    print("Top 5 Dense Pages:")
    
    # Sort by total descending
    stats.sort(key=lambda x: x['total'], reverse=True)
    
    print(f"{'Run ID':<40} | {'Total':<8} | {'Barline':<8} | {'FP':<8}")
    print("-" * 70)
    for s in stats[:5]:
        print(f"{s['run_id']:<40} | {s['total']:<8} | {s['barline']:<8} | {s['fp']:<8}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", help="List of inputs in format NAME:PATH")
    args = parser.parse_args()
    
    for item in args.inputs:
        name, path = item.split(":", 1)
        summarize(path, name)
        print("\n")

if __name__ == "__main__":
    main()
