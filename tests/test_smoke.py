"""Lab 12 smoke tests for CPU-only basic checks without GPU.

Run on GitHub free x86 runner; no CUDA torch, no TensorRT, no camera.
"""

# 標準庫
from pathlib import Path

# 第三方套件
import pytest


def test_best_pt_exists():
    """Check that fine-tuned best.pt exists and has reasonable size."""
    p = Path(__file__).parent.parent / "best.pt"
    assert p.exists(), f"{p} 缺失 — 是否忘了 commit best.pt？"
    assert p.stat().st_size > 1_000_000, "best.pt 檔案過小 (<1 MB)，可能有問題"


def test_requirements_pinned():
    """Check that dependencies in requirements.txt are version-pinned."""
    req = (Path(__file__).parent.parent / "requirements.txt").read_text()
    for line in req.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 允許 -e/-r/-c/-- 等特殊指令
        if line.startswith(("-e", "-r", "-c", "--")):
            continue
        assert any(op in line for op in ["==", "~=", ">="]), (
            f"requirements.txt 中有未固定版本的依賴: {line!r}"
        )


def test_dockerfile_uses_arm64_base():
    """Check that Dockerfile.ci uses a Jetson-compatible ARM64 base image."""
    df = (Path(__file__).parent.parent / "Dockerfile.ci").read_text()
    # dustynv 與 l4t-base 映像皆為 aarch64 專用
    assert any(base in df for base in ["dustynv/", "l4t-", "nvcr.io/nvidia/l4t"]), (
        "Dockerfile.ci 必須 FROM Jetson ARM64 基底 (dustynv/* 或 l4t-*)"
    )


@pytest.mark.parametrize("name", ["src/inference_node.py", "best.pt", "requirements.txt"])
def test_required_files(name):
    """Check that files required by Docker COPY exist."""
    path = Path(__file__).parent.parent / name
    assert path.exists(), f"{name} 缺失"
