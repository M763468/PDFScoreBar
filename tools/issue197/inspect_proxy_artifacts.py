from __future__ import annotations

import json
import lzma
from pathlib import Path
from typing import Any, BinaryIO

import cv2
import numpy as np
from numpy.lib import format as npy_format

TARGETS = {
    "page_021": "Shostakovich-Sym5-Va_page_013",
    "page_022": "Shostakovich-Sym5-Va_page_014",
    "page_045": "Va_Prokofiev_Symphony1_page_004",
}

BASE_STAGE_E = Path(
    "logs/issue120_e2e_recovery/stage_e_hybrid_output/stage_e_full_pipeline/baseline/batch"
)
BASE_DEBUG = Path(
    "logs/full_pipeline_runs/dense_full_pipeline/hybrid_output/dense_full_pipeline/baseline/batch"
)
OUT = Path("logs/issue197_system_grouping/proxy_artifact_channel_summary.json")
XZ_MAGIC = b"\xfd7zXZ\x00"


def scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def safe_array_stats(arr: np.ndarray) -> dict[str, Any]:
    if arr.size == 0:
        return {
            "shape": list(arr.shape),
            "dtype": str(arr.dtype),
            "size": 0,
            "min": None,
            "max": None,
            "nonzero": 0,
            "nonzero_ratio": 0.0,
        }

    return {
        "shape": list(arr.shape),
        "dtype": str(arr.dtype),
        "size": int(arr.size),
        "min": scalar(np.nanmin(arr)),
        "max": scalar(np.nanmax(arr)),
        "nonzero": int(np.count_nonzero(arr)),
        "nonzero_ratio": float(np.count_nonzero(arr) / max(1, arr.size)),
    }


def image_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}

    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        return {"exists": True, "load_error": True}

    summary = {"exists": True, **safe_array_stats(img)}
    if img.ndim == 3:
        summary["channels"] = [safe_array_stats(img[..., i]) for i in range(img.shape[-1])]
    return summary


def is_xz_file(path: Path) -> bool:
    with path.open("rb") as f:
        return f.read(len(XZ_MAGIC)) == XZ_MAGIC


def read_npy_header_from_stream(f: BinaryIO) -> dict[str, Any]:
    version = npy_format.read_magic(f)
    if version == (1, 0):
        shape, fortran_order, dtype = npy_format.read_array_header_1_0(f)
    elif version == (2, 0):
        shape, fortran_order, dtype = npy_format.read_array_header_2_0(f)
    elif version == (3, 0):
        shape, fortran_order, dtype = npy_format.read_array_header_2_0(f)
    else:
        raise ValueError(f"Unsupported npy version: {version}")

    return {
        "version": list(version),
        "shape": list(shape),
        "fortran_order": bool(fortran_order),
        "dtype": str(dtype),
        "has_object": bool(dtype.hasobject),
    }


def read_npy_header(path: Path) -> dict[str, Any]:
    compressed_xz = is_xz_file(path)
    if compressed_xz:
        with lzma.open(path, "rb") as f:
            header = read_npy_header_from_stream(f)
    else:
        with path.open("rb") as f:
            header = read_npy_header_from_stream(f)
    header["compressed_xz"] = compressed_xz
    return header


def load_numeric_npy(path: Path, compressed_xz: bool) -> np.ndarray:
    if compressed_xz:
        with lzma.open(path, "rb") as f:
            return np.load(f, allow_pickle=False)
    return np.load(path, allow_pickle=False)


def npy_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}

    try:
        header = read_npy_header(path)
    except Exception as exc:
        return {"exists": True, "header_error": f"{type(exc).__name__}: {exc}"}

    summary: dict[str, Any] = {"exists": True, "header": header}

    if header.get("has_object"):
        summary["data_loaded"] = False
        summary["reason"] = "object dtype npy; skip loading pickled payload in this helper"
        return summary

    try:
        arr = load_numeric_npy(path, compressed_xz=bool(header.get("compressed_xz")))
    except Exception as exc:
        summary["load_error"] = f"{type(exc).__name__}: {exc}"
        return summary

    summary.update(safe_array_stats(arr))

    channels: list[dict[str, Any]] = []
    if arr.ndim == 2:
        channels.append({"axis": "2d", "index": 0, **safe_array_stats(arr)})
    elif arr.ndim == 3:
        if arr.shape[-1] <= 64:
            for i in range(arr.shape[-1]):
                channels.append({"axis": "last", "index": i, **safe_array_stats(arr[..., i])})
        if arr.shape[0] <= 64:
            for i in range(arr.shape[0]):
                channels.append({"axis": "first", "index": i, **safe_array_stats(arr[i, ...])})
    summary["channels"] = channels
    return summary


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out: dict[str, Any] = {}

    for page_id, source in TARGETS.items():
        stage_dir = BASE_STAGE_E / source
        debug_dir = BASE_DEBUG / source

        out[page_id] = {
            "source": source,
            "stage_e": {
                "proxy_npy": str(stage_dir / f"{source}_proxy.npy"),
                "proxy_npy_summary": npy_summary(stage_dir / f"{source}_proxy.npy"),
                "proxy_png": str(stage_dir / f"{source}_proxy.png"),
                "proxy_png_summary": image_summary(stage_dir / f"{source}_proxy.png"),
                "staff_mask": str(stage_dir / f"{source}_staff_mask.png"),
                "staff_mask_summary": image_summary(stage_dir / f"{source}_staff_mask.png"),
            },
            "debug_reference": {
                "symbols_png": str(debug_dir / f"{source}_proxy_debug_4_symbols.png"),
                "symbols_png_summary": image_summary(debug_dir / f"{source}_proxy_debug_4_symbols.png"),
                "brace_dot_png": str(debug_dir / f"{source}_proxy_debug_16_brace_dot.png"),
                "brace_dot_png_summary": image_summary(debug_dir / f"{source}_proxy_debug_16_brace_dot.png"),
                "bar_line_img_png": str(debug_dir / f"{source}_proxy_debug_8_bar_line_img.png"),
                "bar_line_img_png_summary": image_summary(debug_dir / f"{source}_proxy_debug_8_bar_line_img.png"),
            },
        }

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
