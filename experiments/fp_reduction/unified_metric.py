
# unified_metric.py
# Wrapper to use homr's official evaluation logic (padding, margins, greedy matching).
# Ensures consistency with baseline results (e.g. TP=152).

import sys
import os

# Ensure we can import from src/
# In container, workspace root is /workspace
if os.path.exists('/workspace/src'):
    sys.path.insert(0, '/workspace/src')
else:
    # Fallback if running relative to repo root
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

try:
    from common.barline_evaluation import greedy_barline_match
except ImportError as e:
    print(f"Error importing homr evaluation logic: {e}")
    print("Ensure you are running inside the homr environment/container.")
    sys.exit(1)

def evaluate_detections(predictions, ground_truth):
    """
    Evaluate predictions against ground truth using homr's official greedy matcher.
    
    Args:
        predictions: List of [x1, y1, x2, y2]
        ground_truth: List of [x1, y1, x2, y2]
        
    Returns:
        dict: {TP, FP, FN, Precision, Recall, F1}
    """
    # Convert to list of tuples if needed, though list of lists might work if typed loosely.
    # greedy_barline_match expects iterables of boxes.
    preds = [tuple(p) for p in predictions]
    gts = [tuple(g) for g in ground_truth]
    
    result = greedy_barline_match(preds, gts, iou_threshold=0.5)
    
    tp = len(result.matches)
    fp = len(result.false_positive_indices)
    fn = len(result.false_negative_indices)
    
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    
    return {
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "Precision": prec,
        "Recall": rec,
        "F1": f1
    }
