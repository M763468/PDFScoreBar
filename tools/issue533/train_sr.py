"""Train a first-party x4 SR model from random initialization on synthetic notation (Issue #533).

Provenance rules enforced here: the network is the vendored Apache-2.0 RRDBNet with random
initialization (no pretrained weights are loaded), and every training/validation pair comes
from ``synth_score.make_pair`` (procedural, first-party). No Real-ESRGAN weight or output,
score PDF, evaluation image or ground truth is read.

Example:
  python tools/issue533/train_sr.py --out <dir> --num-feat 32 --num-block 6 --num-grow 16 \
      --iters 6000 --seed 533
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F
from torch.utils.data import DataLoader, IterableDataset, get_worker_info

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import synth_score  # noqa: E402

from src.third_party.realesrgan_sr import RRDBNet  # noqa: E402

VAL_SEED_BASE = 900_000_000  # disjoint from training seeds (< 900M)


def _crops(hr: np.ndarray, lr: np.ndarray, rng: np.random.Generator, n: int, lr_patch: int):
    s = synth_score.SCALE
    out = []
    tries = 0
    while len(out) < n and tries < n * 8:
        tries += 1
        y = int(rng.integers(0, lr.shape[0] - lr_patch + 1))
        x = int(rng.integers(0, lr.shape[1] - lr_patch + 1))
        h = hr[y * s : (y + lr_patch) * s, x * s : (x + lr_patch) * s]
        ink = float((h < 128).mean())
        if ink < 0.01 and rng.random() < 0.85:
            continue
        out.append((lr[y : y + lr_patch, x : x + lr_patch], h))
    return out


class SynthPairs(IterableDataset):
    def __init__(self, seed: int, lr_patch: int, crops_per_tile: int):
        self.seed, self.lr_patch, self.crops = seed, lr_patch, crops_per_tile

    def __iter__(self):
        info = get_worker_info()
        wid, nw = (info.id, info.num_workers) if info else (0, 1)
        k = 0
        while True:
            tile_seed = self.seed * 1_000_003 + k * nw + wid
            k += 1
            hr, lr = synth_score.make_pair(tile_seed % VAL_SEED_BASE)
            rng = np.random.default_rng(tile_seed + 7)
            for lr_c, hr_c in _crops(hr, lr, rng, self.crops, self.lr_patch):
                yield (
                    torch.from_numpy(lr_c.astype(np.float32) / 255.0)[None].expand(3, -1, -1),
                    torch.from_numpy(hr_c.astype(np.float32) / 255.0)[None].expand(3, -1, -1),
                )


def val_set(n: int, lr_patch: int):
    pairs = []
    for i in range(n):
        hr, lr = synth_score.make_pair(VAL_SEED_BASE + i)
        rng = np.random.default_rng(VAL_SEED_BASE + i)
        pairs += _crops(hr, lr, rng, 1, lr_patch)
    lr = torch.stack(
        [torch.from_numpy(a.astype(np.float32) / 255.0)[None].expand(3, -1, -1) for a, _ in pairs]
    )
    hr = torch.stack(
        [torch.from_numpy(b.astype(np.float32) / 255.0)[None].expand(3, -1, -1) for _, b in pairs]
    )
    return lr, hr


@torch.no_grad()
def evaluate(model, lr, hr, device):
    model.eval()
    psnr, mae, binerr = [], [], []
    for i in range(0, len(lr), 8):
        out = model(lr[i : i + 8].to(device)).float().clamp(0, 1)
        t = hr[i : i + 8].to(device)
        mse = F.mse_loss(out, t, reduction="none").mean(dim=(1, 2, 3))
        psnr += (10 * torch.log10(1 / mse.clamp_min(1e-10))).tolist()
        mae += (out - t).abs().mean(dim=(1, 2, 3)).tolist()
        binerr += ((out < 0.5) != (t < 0.5)).float().mean(dim=(1, 2, 3)).tolist()
    model.train()
    return {
        "psnr": float(np.mean(psnr)),
        "mae": float(np.mean(mae)),
        "binary_error": float(np.mean(binerr)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--num-feat", type=int, default=32)
    ap.add_argument("--num-block", type=int, default=6)
    ap.add_argument("--num-grow", type=int, default=16)
    ap.add_argument("--iters", type=int, default=6000)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr-patch", type=int, default=64)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--seed", type=int, default=533)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--val", type=int, default=64)
    ap.add_argument("--eval-every", type=int, default=1000)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = torch.device("cuda")
    model = RRDBNet(
        num_in_ch=3,
        num_out_ch=3,
        scale=4,
        num_feat=args.num_feat,
        num_block=args.num_block,
        num_grow_ch=args.num_grow,
    ).to(device)
    params = sum(p.numel() for p in model.parameters())
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.0, betas=(0.9, 0.99))
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt,
        lambda it: (
            min(1.0, (it + 1) / 200)
            * 0.5
            * (1 + math.cos(math.pi * min(it, args.iters) / args.iters))
        ),
    )
    loader = DataLoader(
        SynthPairs(args.seed, args.lr_patch, 4),
        batch_size=args.batch,
        num_workers=args.workers,
        persistent_workers=True,
        prefetch_factor=4,
    )
    vlr, vhr = val_set(args.val, args.lr_patch)
    meta = dict(
        vars(args),
        out=str(args.out),
        params=params,
        torch=torch.__version__,
        device=torch.cuda.get_device_name(),
        init="random (torch default + BasicSR kaiming*0.1 in RDB)",
        data="tools/issue533/synth_score.py procedural pairs only",
        synth_sha256=hashlib.sha256(
            (Path(__file__).parent / "synth_score.py").read_bytes()
        ).hexdigest(),
        train_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    (args.out / "meta.json").write_text(json.dumps(meta, indent=1))
    log = open(args.out / "train_log.jsonl", "w")
    rec = {"iter": 0, **evaluate(model, vlr, vhr, device)}
    log.write(json.dumps(rec) + "\n")
    log.flush()
    print(rec, flush=True)
    t0 = time.time()
    it = 0
    running = 0.0
    for lr_b, hr_b in loader:
        lr_b, hr_b = lr_b.to(device, non_blocking=True), hr_b.to(device, non_blocking=True)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            out = model(lr_b)
        loss = F.l1_loss(out.float(), hr_b)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        sched.step()
        it += 1
        running += loss.item()
        if it % args.eval_every == 0 or it == args.iters:
            rec = {
                "iter": it,
                "train_l1": running / args.eval_every,
                "sec": round(time.time() - t0, 1),
                **evaluate(model, vlr, vhr, device),
            }
            running = 0.0
            log.write(json.dumps(rec) + "\n")
            log.flush()
            print(rec, flush=True)
            torch.save({"params": model.state_dict()}, args.out / "model.pth")
        if it >= args.iters:
            break
    torch.save({"params": model.state_dict()}, args.out / "model.pth")
    (args.out / "model.sha256").write_text(
        hashlib.sha256((args.out / "model.pth").read_bytes()).hexdigest() + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
