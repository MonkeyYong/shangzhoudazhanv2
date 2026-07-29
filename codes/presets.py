"""3 档开局：14 子小局 / 22 子大战（默认）/ 34 子决战。

权威来源：v1 codes/商周大战.html (lines 507-541)
- WHITE_HALF：白方单独摆子；黑方由中心对称 (c, r) → (18-c, 18-r) 自动镜像
- 白方武王 (9, 18) = K19，位于黑方王城内
- 黑方武王 (9, 0) = K1，位于白方王城内
"""

from __future__ import annotations

# 内部坐标约定：
# - col 0..18  → A..T（跳过 I）
# - row 0..18  → 1..19（行 1 在棋盘底部 / 白方起始行）

WHITE_HALF: dict[str, list[tuple[str, int, int]]] = {
    "small": [  # 14 子（白 1 王 + 6 兵，黑镜 = 1 王 + 6 兵 = 14）
        ("king", 9, 18),
        ("soldier", 7, 0), ("soldier", 11, 0), ("soldier", 9, 2),
        ("soldier", 6, 4), ("soldier", 12, 4), ("soldier", 9, 6),
    ],
    "battle": [  # 22 子（默认）
        ("king", 9, 18),
        ("soldier", 7, 0), ("soldier", 11, 0), ("soldier", 9, 2),
        ("soldier", 7, 3), ("soldier", 11, 3),
        ("soldier", 5, 5), ("soldier", 9, 5), ("soldier", 13, 5),
        ("soldier", 7, 7), ("soldier", 11, 7),
    ],
    "final": [  # 34 子
        ("king", 9, 18),
        ("soldier", 7, 0), ("soldier", 11, 0),
        ("soldier", 5, 1), ("soldier", 13, 1),
        ("soldier", 9, 2),
        ("soldier", 3, 3), ("soldier", 7, 3), ("soldier", 11, 3), ("soldier", 15, 3),
        ("soldier", 5, 5), ("soldier", 9, 5), ("soldier", 13, 5),
        ("soldier", 3, 7), ("soldier", 7, 7), ("soldier", 11, 7), ("soldier", 15, 7),
    ],
}

PRESET_NAMES = {
    "small": "小局",
    "battle": "大战",
    "final": "决战",
}


def build_layout(key: str) -> list[tuple[str, str, int, int]]:
    """返回完整布局：(side, type, col, row) 列表。

    白方按 WHITE_HALF[key] 摆；黑方按中心对称镜像 (c, r) → (18-c, 18-r)。
    """
    if key not in WHITE_HALF:
        raise ValueError(f"未知 preset: {key!r}（可选: {list(WHITE_HALF)}）")
    out: list[tuple[str, str, int, int]] = []
    for ptype, c, r in WHITE_HALF[key]:
        out.append(("white", ptype, c, r))
        out.append(("black", ptype, 18 - c, 18 - r))
    return out


# 对外暴露：PRESETS 字典（与 v1 命名兼容）
PRESETS = {name: {"name": PRESET_NAMES[name], "layout": build_layout(name)} for name in WHITE_HALF}
