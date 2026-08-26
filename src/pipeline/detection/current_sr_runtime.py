"""Optimized Real-ESRGAN runtime for verified current-x4 detector support.

This path is deliberately narrower than ``src.common.preprocessing.apply_advanced_sr``:
it serves the accepted dense-route RealESRGAN_x4plus contract only.  The model
and weights remain unchanged, while two execution details are optimized:

* RRDBNet convolution runs in channels-last memory format on CUDA;
* accepted tile cores are rounded to uint8 on CUDA and copied directly into a
  CPU output image instead of building a full x4 FP16 CUDA output tensor.

The runtime object owns only model-lifetime state so one dedicated SR process can
reuse it across pages and then exit before HOMR/OMR workers start.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

DEFAULT_TILE_SIZE = 400
IMAGE_SIZE_THRESHOLD_FOR_TILING = 1000
PROJECT_ROOT = Path(__file__).resolve().parents[3]
WEIGHTS = PROJECT_ROOT / "external" / "realesrgan" / "weights" / "RealESRGAN_x4plus.pth"
COMPILE_MODES = frozenset(
    {
        "default",
        "reduce-overhead",
        "max-autotune-no-cudagraphs",
        "max-autotune",
    }
)


def normalize_compile_mode(value: object) -> str | None:
    """Normalize the opt-in torch.compile mode used by the verified dense route."""
    if value is None:
        return None
    mode = str(value).strip()
    if not mode or mode.lower() in {"off", "none", "false"}:
        return None
    if mode not in COMPILE_MODES:
        allowed = ", ".join(sorted(COMPILE_MODES))
        raise ValueError(f"Unsupported current x4 SR compile mode {mode!r}; expected one of: {allowed}")
    return mode


class CurrentX4SRRuntime:
    """Reusable RealESRGAN_x4plus CUDA runtime for the verified dense route."""

    def __init__(
        self,
        *,
        tile: int | None = -1,
        tile_pad: int = 10,
        fp32: bool = False,
        channels_last: bool = True,
        compile_mode: str | None = None,
    ) -> None:
        # Keep heavy imports inside the runtime constructor.  Importing the worker
        # or its request helpers must stay lightweight for orchestration/tests.
        import torch
        from basicsr.archs.rrdbnet_arch import RRDBNet
        from realesrgan import RealESRGANer

        if not torch.cuda.is_available():
            raise RuntimeError("Verified current x4 SR runtime requires CUDA")
        if not WEIGHTS.is_file():
            raise FileNotFoundError(WEIGHTS)

        self.torch = torch
        self.tile = tile
        self.tile_pad = int(tile_pad)
        self.fp32 = bool(fp32)
        self.channels_last = bool(channels_last)
        self.compile_mode = normalize_compile_mode(compile_mode)
        self.scale = 4
        self.device = torch.device("cuda")

        model = RRDBNet(
            num_in_ch=3,
            num_out_ch=3,
            num_feat=64,
            num_block=23,
            num_grow_ch=32,
            scale=4,
        )
        upsampler = RealESRGANer(
            scale=4,
            model_path=str(WEIGHTS),
            model=model,
            tile=DEFAULT_TILE_SIZE,
            tile_pad=self.tile_pad,
            pre_pad=0,
            half=not self.fp32,
            device=self.device,
        )
        self.model = upsampler.model
        if self.channels_last:
            self.model = self.model.to(memory_format=torch.channels_last)
        if self.compile_mode is not None:
            self.model = torch.compile(self.model, mode=self.compile_mode)

    def _effective_tile(self, image_bgr: np.ndarray) -> int:
        configured = self.tile
        if configured is None or int(configured) == -1:
            if max(image_bgr.shape[:2]) <= IMAGE_SIZE_THRESHOLD_FOR_TILING:
                return max(image_bgr.shape[:2])
            return DEFAULT_TILE_SIZE
        value = int(configured)
        if value <= 0:
            return max(image_bgr.shape[:2])
        return value

    def enhance(self, image_bgr: np.ndarray) -> np.ndarray:
        """Return the x4 BGR uint8 image using tile-local CUDA output staging."""
        torch = self.torch
        if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
            image_bgr = cv2.cvtColor(image_bgr, cv2.COLOR_GRAY2BGR)

        image = image_bgr.astype(np.float32)
        image /= 255.0
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        tensor = torch.from_numpy(np.transpose(image, (2, 0, 1))).float().unsqueeze(0)
        tensor = tensor.to(self.device)
        if not self.fp32:
            tensor = tensor.half()
        if self.channels_last:
            tensor = tensor.contiguous(memory_format=torch.channels_last)

        _, _, height, width = tensor.shape
        output = np.empty((height * self.scale, width * self.scale, 3), dtype=np.uint8)
        tile = self._effective_tile(image_bgr)
        tiles_x = math.ceil(width / tile)
        tiles_y = math.ceil(height / tile)

        with torch.inference_mode():
            for y in range(tiles_y):
                for x in range(tiles_x):
                    input_start_x = x * tile
                    input_end_x = min(input_start_x + tile, width)
                    input_start_y = y * tile
                    input_end_y = min(input_start_y + tile, height)
                    input_start_x_pad = max(input_start_x - self.tile_pad, 0)
                    input_end_x_pad = min(input_end_x + self.tile_pad, width)
                    input_start_y_pad = max(input_start_y - self.tile_pad, 0)
                    input_end_y_pad = min(input_end_y + self.tile_pad, height)
                    input_tile_width = input_end_x - input_start_x
                    input_tile_height = input_end_y - input_start_y

                    input_tile = tensor[
                        :,
                        :,
                        input_start_y_pad:input_end_y_pad,
                        input_start_x_pad:input_end_x_pad,
                    ]
                    if self.channels_last:
                        input_tile = input_tile.contiguous(memory_format=torch.channels_last)

                    output_tile = self.model(input_tile)

                    output_start_x = input_start_x * self.scale
                    output_end_x = input_end_x * self.scale
                    output_start_y = input_start_y * self.scale
                    output_end_y = input_end_y * self.scale
                    output_start_x_tile = (input_start_x - input_start_x_pad) * self.scale
                    output_start_y_tile = (input_start_y - input_start_y_pad) * self.scale
                    output_end_x_tile = output_start_x_tile + input_tile_width * self.scale
                    output_end_y_tile = output_start_y_tile + input_tile_height * self.scale
                    core = output_tile[
                        :,
                        :,
                        output_start_y_tile:output_end_y_tile,
                        output_start_x_tile:output_end_x_tile,
                    ]

                    # Match pinned Real-ESRGAN's float32/clamp/*255/round/uint8
                    # conversion, but perform it before D2H and only for the core
                    # that survives tile-padding removal.
                    core_u8 = core.float()
                    core_u8.clamp_(0, 1).mul_(255.0).round_()
                    core_u8 = core_u8.to(torch.uint8)
                    core_u8 = core_u8[0, [2, 1, 0], :, :].permute(1, 2, 0).contiguous()
                    output[output_start_y:output_end_y, output_start_x:output_end_x] = (
                        core_u8.cpu().numpy()
                    )

                    del output_tile, core, core_u8, input_tile

        del tensor
        return output

    def metadata(self) -> dict[str, Any]:
        torch = self.torch
        return {
            "runtime": "current_x4_channels_last_gpu_uint8_cpu_stitch",
            "model": "RealESRGAN_x4plus",
            "scale": 4,
            "tile": self.tile,
            "tile_pad": self.tile_pad,
            "fp32": self.fp32,
            "channels_last": self.channels_last,
            "compile_mode": self.compile_mode,
            "output_mode": "gpu_uint8_cpu_stitch",
            "device": torch.cuda.get_device_name(torch.cuda.current_device()),
            "torch_version": torch.__version__,
            "torch_cuda_version": torch.version.cuda,
            "cudnn_version": torch.backends.cudnn.version(),
        }
