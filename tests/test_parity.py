"""Phase 5 附：Python ↔ JS 引擎 Parity 测试。

策略：
1. 用 Python 引擎自对弈生成一段棋谱（保存为 JSON）
2. 同时计算 Python 端的 position_hash 序列
3. 调用 Node.js (subprocess) 运行 parity_runner.js 加载同一 JSON
4. 收集 JS 端的 position_hash 序列
5. 逐手断言：Python hash == JS hash

前置：Node.js 16+ 必须可用
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from codes.board import Side
from codes.ai import AI_LEVELS, ai_choose
from codes.replay import Record
from codes.rules import apply_move, end_turn, position_hash


# ===== 前置检查 =====


def _node_available() -> bool:
    return shutil.which("node") is not None


pytestmark = pytest.mark.skipif(
    not _node_available(),
    reason="需要 Node.js 16+ 才能运行 parity 测试",
)


# ===== 工具 =====


REPO_ROOT = Path(__file__).resolve().parent.parent
PARITY_RUNNER = REPO_ROOT / "web" / "test" / "parity_runner.js"


def _python_hashes(record: Record) -> list[str]:
    """Python 引擎逐步回放，返回 position_hash 序列。"""
    state = record.replay_index(0)
    hashes = [position_hash(state)]
    for i in range(len(record.moves)):
        state = record.replay_index(i + 1)
        hashes.append(position_hash(state))
    return hashes


def _js_hashes(record: Record) -> list[str]:
    """调用 Node.js parity_runner.js 加载棋谱，返回 JS 端 hash 序列。"""
    # 写到临时文件
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(record.to_dict(), f, ensure_ascii=False)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["node", str(PARITY_RUNNER), tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"parity_runner.js 失败 (exit={result.returncode}):\n"
                f"stderr: {result.stderr}"
            )
        return result.stdout.strip().split("\n")
    finally:
        os.unlink(tmp_path)


def _generate_record(num_moves: int = 12, level: str = "rookie") -> Record:
    """Python 引擎自对弈生成 num_moves 步棋谱。"""
    from codes.board import State

    state = State.from_preset("battle")
    record = Record(preset="battle", label=f"parity-{num_moves}")

    for _ in range(num_moves):
        if state.game_over is not None:
            break
        level_obj = AI_LEVELS[level]
        choice = ai_choose(state, state.turn, level_obj)
        if choice is None:
            break
        # 记录此步
        from codes.board import coord_to_str

        record.add_move(
            from_coord=coord_to_str(choice.move.from_col, choice.move.from_row),
            to_coord=coord_to_str(choice.move.to_col, choice.move.to_row),
            capture=choice.move.capture,
            clone=choice.clone,
        )
        # 应用到 state
        new_state, _ = apply_move(state, choice.move, clone_decision=choice.clone)
        new_state, _ = end_turn(new_state)
        state = new_state

    return record


# ===== 测试 =====


def test_parity_10_moves_battle():
    """10 步 battle 自对弈：Python 与 JS 引擎逐手 hash 一致。"""
    record = _generate_record(num_moves=10, level="rookie")

    py_hashes = _python_hashes(record)
    js_hashes = _js_hashes(record)

    assert len(py_hashes) == len(js_hashes), (
        f"hash 数量不等: py={len(py_hashes)} js={len(js_hashes)}"
    )
    assert py_hashes == js_hashes, (
        f"hash 不匹配！\n"
        f"py: {py_hashes[:3]}...\n"
        f"js: {js_hashes[:3]}... "
        f"第一个不匹配: step {next(i for i, (p, j) in enumerate(zip(py_hashes, js_hashes)) if p != j)}"
    )


def test_parity_initial_state_hash():
    """初始局面 hash 一致（不依赖棋谱）。"""
    record = Record(preset="battle")  # 空棋谱
    py_hashes = _python_hashes(record)
    js_hashes = _js_hashes(record)
    assert py_hashes == js_hashes
    assert len(py_hashes) == 1  # 仅初始


def test_parity_with_ai_legal_moves():
    """构造的合法棋谱（仅白兵移动）→ 双方 hash 一致。"""
    record = Record(
        preset="battle",
        label="manual-minimal",
        moves=[
            {"from": "H1", "to": "H3", "capture": False, "clone": False},
            {"from": "H19", "to": "H17", "capture": False, "clone": False},
        ],
    )
    py_hashes = _python_hashes(record)
    js_hashes = _js_hashes(record)
    assert py_hashes == js_hashes
    assert len(py_hashes) == 3  # 初始 + 2 步


def test_parity_after_50_moves():
    """50 步深度回放仍能保持 hash 一致。"""
    record = _generate_record(num_moves=50, level="rookie")
    py_hashes = _python_hashes(record)
    js_hashes = _js_hashes(record)
    assert py_hashes == js_hashes


def test_parity_final_state_matches():
    """Python 与 JS 回放终局应状态等价（看 apply_move 后的最终局面）。"""
    record = _generate_record(num_moves=20, level="rookie")
    py_hashes = _python_hashes(record)
    js_hashes = _js_hashes(record)
    # 终局 hash 一致
    assert py_hashes[-1] == js_hashes[-1]


def test_parity_v1_export_format_chess_record():
    """v1 导出格式的 JSON 棋谱能被 Python 与 JS 共同解析。"""
    v1_style = {
        "preset": "battle",
        "label": "v1-export-test",
        "moves": [
            {"from": "H1", "to": "H3", "capture": False, "clone": False},
            {"from": "H19", "to": "H17", "capture": False, "clone": False},
            {"from": "H3", "to": "H4", "capture": False, "clone": False},
        ],
    }
    record = Record.from_dict(v1_style)
    py_hashes = _python_hashes(record)
    js_hashes = _js_hashes(record)
    assert py_hashes == js_hashes
    assert len(py_hashes) == 4  # 初始 + 3 步
