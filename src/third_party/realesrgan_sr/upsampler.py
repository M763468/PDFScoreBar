# Copyright (c) 2021, Xintao Wang
# SPDX-License-Identifier: BSD-3-Clause
#
# Derived from Real-ESRGAN commit a4abfb2979a7bbff3f69f58f58ae324608821e27:
#   realesrgan/utils.py (class RealESRGANer)
# License: BSD 3-Clause, see LICENSE-Real-ESRGAN.txt in this directory.
#
# Modifications by PDFScoreBar contributors (Issue #533):
# - removed the ``basicsr.utils.download_util`` import and URL downloading;
#   ``model_path`` must be a local, already verified weight file;
# - removed deep network interpolation (``dni``), ``gpu_id`` and the
#   PrefetchReader/IOConsumer helpers, which PDFScoreBar does not use;
# - a tile inference RuntimeError now propagates instead of being printed and
#   followed by a NameError or a stale tile (failure path only);
# - kept pre/tile/post-processing and ``enhance`` numerically unchanged,
#   including the "Tile i/n" progress print that callers already filter.
"""Tiled Real-ESRGAN inference helper without the BasicSR/Real-ESRGAN packages."""

from __future__ import annotations

import math

import cv2
import numpy as np
import torch
from torch.nn import functional as F


class RealESRGANer:
    """Upsample images with a Real-ESRGAN network.

    Args:
        scale (int): Upsampling scale factor used in the network (usually 2 or 4).
        model_path (str): Local path to the pretrained weights.
        model (nn.Module): The defined network.
        tile (int): Tile size; 0 disables tiling.
        tile_pad (int): Pad size for each tile to remove border artifacts.
        pre_pad (int): Reflect pre-padding of the input image.
        half (bool): Use half precision during inference.
        device: Torch device; defaults to CUDA when available.
    """

    def __init__(
        self,
        scale,
        model_path,
        model=None,
        tile=0,
        tile_pad=10,
        pre_pad=10,
        half=False,
        device=None,
    ):
        self.scale = scale
        self.tile_size = tile
        self.tile_pad = tile_pad
        self.pre_pad = pre_pad
        self.mod_scale = None
        self.half = half

        self.device = (
            torch.device("cuda" if torch.cuda.is_available() else "cpu")
            if device is None
            else device
        )

        model_path = str(model_path)
        if model_path.startswith(("https://", "http://")):
            raise ValueError(
                "RealESRGANer requires a local, verified weight file; URL download was removed"
            )
        loadnet = torch.load(model_path, map_location=torch.device("cpu"))

        # prefer to use params_ema
        if "params_ema" in loadnet:
            keyname = "params_ema"
        else:
            keyname = "params"
        model.load_state_dict(loadnet[keyname], strict=True)

        model.eval()
        self.model = model.to(self.device)
        if self.half:
            self.model = self.model.half()

    def pre_process(self, img):
        """Pre-process, such as pre-pad and mod pad, so that the images can be divisible."""
        img = torch.from_numpy(np.transpose(img, (2, 0, 1))).float()
        self.img = img.unsqueeze(0).to(self.device)
        if self.half:
            self.img = self.img.half()

        # pre_pad
        if self.pre_pad != 0:
            self.img = F.pad(self.img, (0, self.pre_pad, 0, self.pre_pad), "reflect")
        # mod pad for divisible borders
        if self.scale == 2:
            self.mod_scale = 2
        elif self.scale == 1:
            self.mod_scale = 4
        if self.mod_scale is not None:
            self.mod_pad_h, self.mod_pad_w = 0, 0
            _, _, h, w = self.img.size()
            if h % self.mod_scale != 0:
                self.mod_pad_h = self.mod_scale - h % self.mod_scale
            if w % self.mod_scale != 0:
                self.mod_pad_w = self.mod_scale - w % self.mod_scale
            self.img = F.pad(self.img, (0, self.mod_pad_w, 0, self.mod_pad_h), "reflect")

    def process(self):
        # model inference
        self.output = self.model(self.img)

    def tile_process(self):
        """Crop the input into tiles, process each tile and merge the results.

        Modified from: https://github.com/ata4/esrgan-launcher
        """
        batch, channel, height, width = self.img.shape
        output_height = height * self.scale
        output_width = width * self.scale
        output_shape = (batch, channel, output_height, output_width)

        # start with black image
        self.output = self.img.new_zeros(output_shape)
        tiles_x = math.ceil(width / self.tile_size)
        tiles_y = math.ceil(height / self.tile_size)

        # loop over all tiles
        for y in range(tiles_y):
            for x in range(tiles_x):
                # extract tile from input image
                ofs_x = x * self.tile_size
                ofs_y = y * self.tile_size
                # input tile area on total image
                input_start_x = ofs_x
                input_end_x = min(ofs_x + self.tile_size, width)
                input_start_y = ofs_y
                input_end_y = min(ofs_y + self.tile_size, height)

                # input tile area on total image with padding
                input_start_x_pad = max(input_start_x - self.tile_pad, 0)
                input_end_x_pad = min(input_end_x + self.tile_pad, width)
                input_start_y_pad = max(input_start_y - self.tile_pad, 0)
                input_end_y_pad = min(input_end_y + self.tile_pad, height)

                # input tile dimensions
                input_tile_width = input_end_x - input_start_x
                input_tile_height = input_end_y - input_start_y
                tile_idx = y * tiles_x + x + 1
                input_tile = self.img[
                    :, :, input_start_y_pad:input_end_y_pad, input_start_x_pad:input_end_x_pad
                ]

                # upscale tile
                with torch.no_grad():
                    output_tile = self.model(input_tile)
                print(f"\tTile {tile_idx}/{tiles_x * tiles_y}")

                # output tile area on total image
                output_start_x = input_start_x * self.scale
                output_end_x = input_end_x * self.scale
                output_start_y = input_start_y * self.scale
                output_end_y = input_end_y * self.scale

                # output tile area without padding
                output_start_x_tile = (input_start_x - input_start_x_pad) * self.scale
                output_end_x_tile = output_start_x_tile + input_tile_width * self.scale
                output_start_y_tile = (input_start_y - input_start_y_pad) * self.scale
                output_end_y_tile = output_start_y_tile + input_tile_height * self.scale

                # put tile into output image
                self.output[:, :, output_start_y:output_end_y, output_start_x:output_end_x] = (
                    output_tile[
                        :,
                        :,
                        output_start_y_tile:output_end_y_tile,
                        output_start_x_tile:output_end_x_tile,
                    ]
                )

    def post_process(self):
        # remove extra pad
        if self.mod_scale is not None:
            _, _, h, w = self.output.size()
            self.output = self.output[
                :, :, 0 : h - self.mod_pad_h * self.scale, 0 : w - self.mod_pad_w * self.scale
            ]
        # remove prepad
        if self.pre_pad != 0:
            _, _, h, w = self.output.size()
            self.output = self.output[
                :, :, 0 : h - self.pre_pad * self.scale, 0 : w - self.pre_pad * self.scale
            ]
        return self.output

    @torch.no_grad()
    def enhance(self, img, outscale=None, alpha_upsampler="realesrgan"):
        h_input, w_input = img.shape[0:2]
        # img: numpy
        img = img.astype(np.float32)
        if np.max(img) > 256:  # 16-bit image
            max_range = 65535
            print("\tInput is a 16-bit image")
        else:
            max_range = 255
        img = img / max_range
        if len(img.shape) == 2:  # gray image
            img_mode = "L"
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        elif img.shape[2] == 4:  # RGBA image with alpha channel
            img_mode = "RGBA"
            alpha = img[:, :, 3]
            img = img[:, :, 0:3]
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            if alpha_upsampler == "realesrgan":
                alpha = cv2.cvtColor(alpha, cv2.COLOR_GRAY2RGB)
        else:
            img_mode = "RGB"
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # ------------------- process image (without the alpha channel) ------------------- #
        self.pre_process(img)
        if self.tile_size > 0:
            self.tile_process()
        else:
            self.process()
        output_img = self.post_process()
        output_img = output_img.data.squeeze().float().cpu().clamp_(0, 1).numpy()
        output_img = np.transpose(output_img[[2, 1, 0], :, :], (1, 2, 0))
        if img_mode == "L":
            output_img = cv2.cvtColor(output_img, cv2.COLOR_BGR2GRAY)

        # ------------------- process the alpha channel if necessary ------------------- #
        if img_mode == "RGBA":
            if alpha_upsampler == "realesrgan":
                self.pre_process(alpha)
                if self.tile_size > 0:
                    self.tile_process()
                else:
                    self.process()
                output_alpha = self.post_process()
                output_alpha = output_alpha.data.squeeze().float().cpu().clamp_(0, 1).numpy()
                output_alpha = np.transpose(output_alpha[[2, 1, 0], :, :], (1, 2, 0))
                output_alpha = cv2.cvtColor(output_alpha, cv2.COLOR_BGR2GRAY)
            else:  # use the cv2 resize for alpha channel
                h, w = alpha.shape[0:2]
                output_alpha = cv2.resize(
                    alpha, (w * self.scale, h * self.scale), interpolation=cv2.INTER_LINEAR
                )

            # merge the alpha channel
            output_img = cv2.cvtColor(output_img, cv2.COLOR_BGR2BGRA)
            output_img[:, :, 3] = output_alpha

        # ------------------------------ return ------------------------------ #
        if max_range == 65535:  # 16-bit image
            output = (output_img * 65535.0).round().astype(np.uint16)
        else:
            output = (output_img * 255.0).round().astype(np.uint8)

        if outscale is not None and outscale != float(self.scale):
            output = cv2.resize(
                output,
                (
                    int(w_input * outscale),
                    int(h_input * outscale),
                ),
                interpolation=cv2.INTER_LANCZOS4,
            )

        return output, img_mode
