"""Phase 1 数据层测试。

验证：
- 3 档开局的子数正确（14 / 22 / 34）
- 黑白对称（白方任一子 (c, r) 在黑方都有镜像 (18-c, 18-r)）
- State.to_dict / from_dict 往返一致
- State.clone() 是独立副本
- 坐标互转正确
- 王城判定正确
"""

from __future__ import annotations

import pytest

from codes.board import (
    BLACK_PALACE,
    COL_LETTERS,
    SIZE,
    WHITE_PALACE,
    KingState,
    Move,
    Piece,
    PieceType,
    Side,
    State,
    coord_to_str,
    in_palace,
    str_to_coord,
)
from codes.presets import PRESETS, build_layout


# ===== Constants =====


def test_size():
    assert SIZE == 19


def test_col_letters_skips_i():
    assert len(COL_LETTERS) == 19
    assert "I" not in COL_LETTERS
    assert COL_LETTERS[0] == "A"
    assert COL_LETTERS[-1] == "T"


def test_white_palace_bounds():
    c0, c1, r0, r1 = WHITE_PALACE
    assert (c0, c1) == (7, 11)  # H..M
    assert (r0, r1) == (0, 3)  # 行 1..4


def test_black_palace_bounds():
    c0, c1, r0, r1 = BLACK_PALACE
    assert (c0, c1) == (7, 11)
    assert (r0, r1) == (15, 18)


# ===== Presets =====


@pytest.mark.parametrize("key,expected_count", [("small", 14), ("battle", 22), ("final", 34)])
def test_preset_piece_count(key, expected_count):
    layout = build_layout(key)
    assert len(layout) == expected_count


def test_preset_piece_count_matches_state():
    for key, expected in [("small", 14), ("battle", 22), ("final", 34)]:
        state = State.from_preset(key)
        assert len(state.pieces) == expected


def test_preset_keys():
    assert set(PRESETS.keys()) == {"small", "battle", "final"}


def test_preset_has_two_kings():
    for key in PRESETS:
        state = State.from_preset(key)
        kings = [p for p in state.pieces if p.type == PieceType.KING]
        assert len(kings) == 2
        assert {k.side for k in kings} == {Side.WHITE, Side.BLACK}


def test_preset_mirror_symmetry():
    """白方任一子 (c, r) 在黑方都有镜像 (18-c, 18-r)，类型相同。"""
    for key in PRESETS:
        layout = build_layout(key)
        whites = {(c, r): t for side, t, c, r in layout if side == "white"}
        blacks = {(c, r): t for side, t, c, r in layout if side == "black"}
        assert len(whites) == len(blacks), f"{key}: 白黑数量不等"
        for (c, r), t in whites.items():
            assert (18 - c, 18 - r) in blacks, f"{key}: 白 ({c},{r}) 缺黑镜像"
            assert blacks[(18 - c, 18 - r)] == t, f"{key}: 镜像类型不一致"


def test_kings_in_opposite_palaces():
    """白武王在黑方王城，黑武王在白方王城。"""
    state = State.from_preset("battle")
    w_king = next(p for p in state.pieces if p.side == Side.WHITE and p.type == PieceType.KING)
    b_king = next(p for p in state.pieces if p.side == Side.BLACK and p.type == PieceType.KING)
    assert in_palace(Side.BLACK, w_king.col, w_king.row), "白武王应在黑方王城"
    assert in_palace(Side.WHITE, b_king.col, b_king.row), "黑武王应在白方王城"


def test_kings_start_imprisoned():
    state = State.from_preset("battle")
    for p in state.pieces:
        if p.type == PieceType.KING:
            assert p.state == KingState.IMPRISONED_INVINCIBLE
        else:
            assert p.state == KingState.FREE


def test_initial_state():
    state = State.from_preset("battle")
    assert state.turn == Side.WHITE
    assert state.step_count == 0
    assert state.game_over is None
    assert not state.side_lost_clone[Side.WHITE]
    assert not state.side_lost_clone[Side.BLACK]
    assert not state.side_clone_unlocked[Side.WHITE]
    assert not state.side_clone_unlocked[Side.BLACK]


def test_piece_ids_unique_and_sequential():
    state = State.from_preset("battle")
    ids = [p.id for p in state.pieces]
    assert ids == sorted(ids)
    assert ids == list(range(1, len(state.pieces) + 1))


# ===== Coord helpers =====


@pytest.mark.parametrize(
    "col,row,expected",
    [(0, 0, "A1"), (9, 9, "K10"), (18, 18, "T19"), (7, 0, "H1"), (11, 18, "M19")],
)
def test_coord_to_str(col, row, expected):
    assert coord_to_str(col, row) == expected


@pytest.mark.parametrize(
    "s,expected",
    [("A1", (0, 0)), ("K10", (9, 9)), ("T19", (18, 18)), ("h1", (7, 0)), ("M19", (11, 18))],
)
def test_str_to_coord(s, expected):
    assert str_to_coord(s) == expected


def test_coord_roundtrip():
    for c in range(SIZE):
        for r in range(SIZE):
            assert str_to_coord(coord_to_str(c, r)) == (c, r)


# ===== in_palace =====


def test_in_palace_white_corners():
    assert in_palace(Side.WHITE, 7, 0)  # H1
    assert in_palace(Side.WHITE, 11, 3)  # M4
    assert not in_palace(Side.WHITE, 6, 0)  # G1 越界
    assert not in_palace(Side.WHITE, 7, 4)  # H5 越界


def test_in_palace_black_corners():
    assert in_palace(Side.BLACK, 7, 15)  # H16
    assert in_palace(Side.BLACK, 11, 18)  # M19
    assert not in_palace(Side.BLACK, 7, 14)  # H15 越界


def test_in_palace_inside_outside():
    assert not in_palace(Side.WHITE, 0, 0)  # A1 远离王城
    assert not in_palace(Side.BLACK, 18, 18)  # T19 远离王城


# ===== State clone / serialization =====


def test_state_clone_is_independent():
    state = State.from_preset("battle")
    cloned = state.clone()
    assert cloned is not state
    assert cloned.pieces is not state.pieces  # list 副本
    assert cloned.pieces[0] is state.pieces[0]  # Piece 不可变，共享 OK
    assert cloned.side_lost_clone is not state.side_lost_clone
    assert cloned.side_clone_unlocked is not state.side_clone_unlocked


def test_state_clone_mutation_isolation():
    state = State.from_preset("battle")
    cloned = state.clone()
    cloned.pieces[0] = cloned.pieces[0].at(0, 0)
    cloned.side_lost_clone[Side.WHITE] = True
    assert state.pieces[0].col != 0 or state.pieces[0].row != 0  # 原 state 未受影响
    assert state.side_lost_clone[Side.WHITE] is False


def test_state_dict_roundtrip():
    state = State.from_preset("battle")
    state.step_count = 5
    state.side_clone_unlocked[Side.WHITE] = True
    d = state.to_dict()
    restored = State.from_dict(d)
    assert restored.turn == state.turn
    assert restored.step_count == 5
    assert restored.side_clone_unlocked[Side.WHITE] is True
    assert len(restored.pieces) == len(state.pieces)
    for got, want in zip(restored.pieces, state.pieces):
        assert got == want


def test_state_dict_roundtrip_full():
    """完整字段往返（含武王状态、has_moved、克隆字段）。"""
    state = State(
        pieces=[
            Piece(
                id=1,
                side=Side.WHITE,
                type=PieceType.KING,
                col=9,
                row=18,
                state=KingState.BERSERK,
                has_moved=True,
                actively_unlocked=True,
            ),
            Piece(
                id=2,
                side=Side.WHITE,
                type=PieceType.CLONE,
                col=9,
                row=15,
                is_clone=True,
            ),
            Piece(id=3, side=Side.BLACK, type=PieceType.SOLDIER, col=5, row=5, dead=True),
        ],
        turn=Side.BLACK,
        step_count=42,
        side_lost_clone={Side.WHITE: True, Side.BLACK: False},
        side_clone_unlocked={Side.WHITE: True, Side.BLACK: False},
        game_over={"winner": "black", "reason": "test"},
    )
    restored = State.from_dict(state.to_dict())
    assert restored.pieces == state.pieces
    assert restored.side_lost_clone == state.side_lost_clone
    assert restored.side_clone_unlocked == state.side_clone_unlocked
    assert restored.game_over == state.game_over


# ===== Move / Piece dataclass sanity =====


def test_move_frozen():
    move = Move(piece_id=1, from_col=0, from_row=0, to_col=1, to_row=1)
    with pytest.raises(Exception):  # FrozenInstanceError
        move.to_col = 2  # type: ignore[misc]


def test_piece_frozen():
    piece = Piece(id=1, side=Side.WHITE, type=PieceType.SOLDIER, col=0, row=0)
    with pytest.raises(Exception):
        piece.col = 5  # type: ignore[misc]


def test_piece_at_returns_new():
    piece = Piece(id=1, side=Side.WHITE, type=PieceType.SOLDIER, col=0, row=0)
    moved = piece.at(5, 5)
    assert moved.col == 5
    assert moved.row == 5
    assert piece.col == 0  # 原 piece 未变


def test_piece_mark_moved():
    piece = Piece(id=1, side=Side.WHITE, type=PieceType.KING, col=9, row=18)
    moved = piece.mark_moved()
    assert moved.has_moved is True
    assert piece.has_moved is False


def test_piece_mark_dead():
    piece = Piece(id=1, side=Side.WHITE, type=PieceType.SOLDIER, col=0, row=0)
    dead = piece.mark_dead()
    assert dead.dead is True
    assert piece.dead is False


# ===== Side / PieceType basics =====


def test_side_opposite():
    assert Side.WHITE.opposite is Side.BLACK
    assert Side.BLACK.opposite is Side.WHITE


def test_side_str_serialization():
    assert Side.WHITE.value == "white"
    assert Side("white") is Side.WHITE
    assert Side("black") is Side.BLACK


def test_piece_type_str_serialization():
    assert PieceType("king") is PieceType.KING
    assert PieceType("soldier") is PieceType.SOLDIER
    assert PieceType("clone") is PieceType.CLONE
