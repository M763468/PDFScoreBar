#!/usr/bin/env python3
"""Train one Issue #296 architecture with the existing classifier loop.

This wrapper keeps the existing augmentation/sampler/optimizer/training contract
and changes only the model factory. Delete before PR preparation.
"""
from __future__ import annotations

import experiments.cnn_classifier.train as trainer

from tools.issue296.architecture_model_factory import build_model


trainer.get_model = build_model


if __name__ == "__main__":
    args = trainer.get_args()
    trainer.train(args)
