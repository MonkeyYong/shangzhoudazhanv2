"""棋谱 record + JSON 序列化（兼容 v1 导出格式）。

权威格式来源：v1 codes/商周大战.html (exportRecord 函数)
格式：
{
  "preset": "battle",
  "label": "对局",
  "moves": [
    {"from": "H1", "to": "H3", "capture": false, "clone": false},
    ...
  ]
}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from codes.board import (
    KingState,
    Move,
    Piece,
    PieceType,
    Side,
    State,
    coord_to_str,
    str_to_coord,
)
from codes.presets import build_layout
from codes.rules import (
    apply_move,
    clone_offer_check,
    end_turn,
    piece_at,
    position_hash,
)


@dataclass
class Record:
    """对局记录。"""

    preset: str = "battle"
    label: str = ""
    moves: list[dict] = field(default_factory=list)
    """每步：{"from": "H1", "to": "H3", "capture": bool, "clone": bool}"""

    @classmethod
    def from_dict(cls, d: dict) -> "Record":
        if not isinstance(d, dict):
            raise ValueError(f"棋谱必须是 dict，实际: {type(d)}")
        return cls(
            preset=d.get("preset", "battle"),
            label=d.get("label", ""),
            moves=list(d.get("moves", [])),
        )

    def to_dict(self) -> dict:
        return {
            "preset": self.preset,
            "label": self.label,
            "moves": list(self.moves),
        }

    def save_json(self, path: str, indent: int = 2) -> None:
        """保存到 JSON 文件。"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=indent)

    @classmethod
    def load_json(cls, path: str) -> "Record":
        """从 JSON 文件加载。"""
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def add_move(self, from_coord: str, to_coord: str, capture: bool = False, clone: bool = False) -> None:
        """追加一步。"""
        self.moves.append(
            {
                "from": from_coord,
                "to": to_coord,
                "capture": capture,
                "clone": clone,
            }
        )

    # ===== 回放 =====

    def replay_index(self, n: int) -> State:
        """重放到第 n 步（n=0 返回初始局面；n=len(moves) 返回终局）。

        应用每步时检测 clone_offer；若该步的 clone 字段为 True，则执行分身。
        棋谱克隆信息缺失（moves[].clone=false）则跳过克隆。
        """
        if n < 0 or n > len(self.moves):
            raise ValueError(f"n 超出范围: {n}（棋谱共 {len(self.moves)} 步）")

        # 初始局面
        try:
            state = State.from_preset(self.preset)
        except ValueError:
            raise ValueError(f"未知 preset: {self.preset!r}")

        for i in range(n):
            step = self.moves[i]
            state = _apply_step(state, step)
        return state

    def replay_all(self) -> State:
        """重放全部步数。"""
        return self.replay_index(len(self.moves))

    # ===== 校验 =====

    def validate(self) -> list[str]:
        """返回所有错误信息列表（空列表 = 合法）。

        校验项：
        - preset 合法
        - moves 列表结构合法
        - 每步坐标合法
        - 每步能成功应用（state 合法）
        """
        errors: list[str] = []

        # 1. preset 合法
        try:
            build_layout(self.preset)
        except (ValueError, KeyError):
            errors.append(f"未知 preset: {self.preset!r}")
            return errors  # 没有合法局面，后续校验无意义

        # 2. moves 结构
        if not isinstance(self.moves, list):
            errors.append(f"moves 必须是 list，实际: {type(self.moves)}")
            return errors

        for i, step in enumerate(self.moves):
            if not isinstance(step, dict):
                errors.append(f"move[{i}] 不是 dict: {step!r}")
                continue
            for k in ("from", "to"):
                if k not in step:
                    errors.append(f"move[{i}] 缺字段 {k!r}")
            if "capture" not in step:
                errors.append(f"move[{i}] 缺字段 'capture'")
            if "clone" not in step:
                errors.append(f"move[{i}] 缺字段 'clone'")

        # 3. 逐步回放（捕获运行时错误）
        try:
            state = State.from_preset(self.preset)
        except Exception as e:
            errors.append(f"初始局面失败: {e}")
            return errors

        for i, step in enumerate(self.moves):
            try:
                state = _apply_step(state, step, validate=True)
            except Exception as e:
                errors.append(f"move[{i}] {step}: {e}")
                break
        return errors


# ===== 内部辅助 =====


def _apply_step(state: State, step: dict, validate: bool = False) -> State:
    """应用单步棋谱到 state。

    - 解析 from/to 坐标
    - 查找对应棋子
    - apply_move（按 step["clone"] 决定是否触发分身）
    - end_turn 切换回合 + 终局判定
    """
    from_str = step["from"]
    to_str = step["to"]
    clone_decision = step.get("clone", False)

    fc, fr = str_to_coord(from_str)
    tc, tr = str_to_coord(to_str)

    piece = piece_at(state, fc, fr)
    if piece is None:
        if validate:
            raise ValueError(f"无子位于 {from_str}")
        raise ValueError(f"无子位于 {from_str}")

    move = Move(
        piece_id=piece.id,
        from_col=fc,
        from_row=fr,
        to_col=tc,
        to_row=tr,
        capture=step.get("capture", False),
    )

    new_state, candidates = apply_move(state, move, clone_decision=clone_decision)
    new_state, _term = end_turn(new_state, position_count=None)
    return new_state


# ===== 工具：notation 显示 =====


def move_to_notation(move: Move) -> str:
    """Move → 显示用字符串（如 H1→H3、H1→H3x）。"""
    s = f"{coord_to_str(move.from_col, move.from_row)}→{coord_to_str(move.to_col, move.to_row)}"
    if move.capture:
        s += "x"
    if move.clone:
        s += "★"
    return s


def record_to_text(record: Record) -> str:
    """Record → 人类可读文本（用于控制台输出）。"""
    lines = [f"=== {record.label or record.preset} ==="]
    for i, m in enumerate(record.moves, 1):
        notation = f"{m['from']}→{m['to']}"
        if m.get("capture"):
            notation += "x"
        if m.get("clone"):
            notation += "★"
        lines.append(f"{i:3}. {notation}")
    return "\n".join(lines)
