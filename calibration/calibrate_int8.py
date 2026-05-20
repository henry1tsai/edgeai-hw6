#!/usr/bin/env python3
# Copyright (c) 2026 henry1tsai
# Tatung University — I4210 AI實務專題
"""calibration/calibrate_int8.py — Build an INT8-calibrated TensorRT engine.

Run on the Jetson once; commit best_int8.engine to the repo.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

MIN_CALIBRATION_IMAGES: int = 50
CAL_DATA = Path(__file__).parent / "calibration_data"
YAML_TEMPLATE = Path(__file__).parent / "calibration.yaml"
WEIGHTS = Path(__file__).parent.parent / "best.pt"
OUT = Path(__file__).parent.parent / "best_int8.engine"


class Int8Calibrator:
    """Calibrate a YOLO model to INT8 precision using TensorRT."""

    def __init__(
        self,
        weights: Path = WEIGHTS,
        cal_data: Path = CAL_DATA,
        yaml_template: Path = YAML_TEMPLATE,
        out: Path = OUT,
    ) -> None:
        """Initialise paths for calibration.

        Args:
            weights: Path to the YOLO .pt weights file.
            cal_data: Directory containing calibration images.
            yaml_template: Path to the calibration YAML template.
            out: Destination path for the INT8 engine file.
        """
        self.weights = weights
        self.cal_data = cal_data
        self.yaml_template = yaml_template
        self.out = out

    def _write_runtime_yaml(self) -> str:
        """Rewrite the YAML with an absolute path for Ultralytics.

        Returns:
            Path to the temporary YAML file.
        """
        template = yaml.safe_load(self.yaml_template.read_text())
        template["path"] = str(self.cal_data.resolve())
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            yaml.safe_dump(template, tmp)
            return tmp.name

    def run(self) -> None:
        """Export the model as an INT8 TensorRT engine."""
        if (
            not self.cal_data.exists()
            or len(list(self.cal_data.glob("*.jpg"))) < MIN_CALIBRATION_IMAGES
        ):
            raise SystemExit(
                f"Need >={MIN_CALIBRATION_IMAGES} calibration images at {self.cal_data}"
            )

        runtime_yaml = self._write_runtime_yaml()

        from ultralytics import YOLO

        model = YOLO(str(self.weights), task="detect")
        model.export(
            format="engine",
            int8=True,
            data=runtime_yaml,
            imgsz=320,
            batch=1,
            verbose=True,
        )
        src = self.weights.with_suffix(".engine")
        src.rename(self.out)
        print(f"Wrote {self.out}, size = {self.out.stat().st_size / 1e6:.1f} MB")


def main() -> None:
    """Entry point for the INT8 calibration script."""
    Int8Calibrator().run()


if __name__ == "__main__":
    main()
