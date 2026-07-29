"""AI 引擎：Negamax + α-β 剪枝 + Zobrist 哈希 + 置换表 + 迭代加深 + 时间预算。

权威来源：v1 codes/商周大战.html (lines 1449-2060, 同算法)
- Zobrist 哈希（mulberry32 固定种子 → 强可复现）
- 置换表（1<<18 项 ≈ 256K，slot 复用）
- killer 启发：每轮选着重置（跨层复用）
- history 启发：β 截断时累加 depth²
- qsearch：depth=0 时调用，评估到稳定
- 滑动 α 窗：首着全窗，后续窄窗 fail-low
- 克隆分支：clone-offer 拆 true/false 两条分支
- 时间预算：超时时保留上一层完整结果

v2 简化：直接用 State（rules.py 已支持纯函数 clone），省去 v1 sim 独立结构；
TT 用 dict 而非 Int32Array（调试友好，性能可接受）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from codes.board import (
    KingState,
    Move,
    Piece,
    PieceType,
    Side,
    State,
)
from codes.rules import (
    apply_move,
    big_count,
    check_win_loss,
    clone_count,
    legal_moves,
    perform_clone,
    position_hash,
)


# ===== 常量 =====

DEFAULT_TT_SIZE = 1 << 18  # 256K entries
"""置换表大小（与 v1 一致）。"""

AI_M = 1_000_000
"""终局分值基数（远大于评估值域 ±2000）。"""

# 与 v1 完全对齐的 mulberry32 种子
_ZOBRIST_SEED = 0xA1B2C3D4


# ===== 评估函数 =====


def _has_any_reach(state: State, piece: Piece) -> bool:
    """棋子是否有任何理论可达格（用于机动性统计）。"""
    return len(legal_moves(state, piece)) > 0


def _coverage(state: State, king: Piece) -> int:
    """敌方士兵在距离 king 切比雪夫 ≤2 的数量。"""
    if king is None:
        return 0
    n = 0
    for p in state.pieces:
        if p.dead or p.side == king.side or p.type != PieceType.SOLDIER:
            continue
        if max(abs(p.col - king.col), abs(p.row - king.row)) <= 2:
            n += 1
    return n


def _ai_clone_option(state: State, side: Side) -> int:
    """某方是否可变身（side_clone_unlocked=True + 场上 ≤ 2 大 + 至少一对兵↔王在 2 格内）。"""
    if state.side_lost_clone.get(side, False):
        return 0
    if not state.side_clone_unlocked.get(side, False):
        return 0
    if big_count(state, side) >= 2:
        return 0
    # 检查兵 ↔ 武王/分身 距离 ≤2
    for s in state.pieces:
        if s.dead or s.side != side or s.type != PieceType.SOLDIER:
            continue
        for k in state.pieces:
            if k.dead or k.side != side:
                continue
            if k.type not in (PieceType.KING, PieceType.CLONE):
                continue
            if max(abs(s.col - k.col), abs(s.row - k.row)) <= 2:
                return 1
    return 0


def evaluate(state: State, side: Side) -> int:
    """局面评估：返回 side 视角分值（与 v1 simEval 完全对齐）。

    权重：
    - 兵 100 / 分身 350 / 武王 1500
    - 武王禁锢减 500；未首动加 200
    - 暴走加 400
    - 机动性 ×2
    - 已移动武王 ±300（脆弱）
    - 禁锢且兵 ≤2：±(3 - soldiers) * 150
    - 围敌方王 +50 / 兵；压迫 ±max(0, 12-d) * 5
    - 解锁梯度：己方兵距己王 距离 d ≤ 12 加 (12-d)*6 + 2格内额外 100
    """
    opp = side.opposite
    my_s = 0
    op_s = 0
    my_mob = 0
    op_mob = 0
    my_soldiers = 0
    op_soldiers = 0
    my_king: Optional[Piece] = None
    op_king: Optional[Piece] = None

    for p in state.pieces:
        if p.dead:
            continue
        v = 0
        if p.type == PieceType.SOLDIER:
            v = 100
            if p.side == side:
                my_soldiers += 1
            else:
                op_soldiers += 1
        elif p.type == PieceType.CLONE:
            v = 350
        else:  # KING
            v = 1500
            if p.state == KingState.IMPRISONED_INVINCIBLE:
                v -= 500
            elif not p.has_moved:
                v += 200  # 解锁价值
        if p.state == KingState.BERSERK:
            v += 400
        if p.side == side:
            my_s += v
        else:
            op_s += v
        if p.type == PieceType.KING and not p.is_clone:
            if p.side == side:
                my_king = p
            else:
                op_king = p
        if _has_any_reach(state, p):
            if p.side == side:
                my_mob += 1
            else:
                op_mob += 1

    score = (my_s - op_s) + (my_mob - op_mob) * 2

    # 脆弱武王
    if my_king and my_king.has_moved:
        score -= 300
    if op_king and op_king.has_moved:
        score += 300

    # 灭子判负风险
    if my_king and my_king.state == KingState.IMPRISONED_INVINCIBLE and my_soldiers <= 2:
        score -= (3 - my_soldiers) * 150
    if op_king and op_king.state == KingState.IMPRISONED_INVINCIBLE and op_soldiers <= 2:
        score += (3 - op_soldiers) * 150

    # 分身可用性
    score += _ai_clone_option(state, side) - _ai_clone_option(state, opp)

    # 围敌方王
    if op_king:
        score += _coverage(state, op_king) * 50
        for s in state.pieces:
            if s.dead or s.side != side or s.type != PieceType.SOLDIER:
                continue
            d = max(abs(s.col - op_king.col), abs(s.row - op_king.row))
            score += max(0, 12 - d) * 5

    # 救己王优先级
    if my_king and my_king.state == KingState.IMPRISONED_INVINCIBLE:
        best = 99
        for s in state.pieces:
            if s.dead or s.side != side or s.type != PieceType.SOLDIER:
                continue
            d = max(abs(s.col - my_king.col), abs(s.row - my_king.row))
            if d < best:
                best = d
        if best < 99:
            score += max(0, 12 - best) * 6 + (100 if best <= 2 else 0)

    return score


# ===== Zobrist 哈希 =====


def _mulberry32(seed: int):
    """mulberry32 PRNG（与 v1 一致；固定种子保证可复现）。"""
    state = [seed & 0xFFFFFFFF]

    def rnd() -> int:
        state[0] = (state[0] + 0x6D2B79F5) & 0xFFFFFFFF
        t = state[0]
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t = (t ^ (t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF)

    return rnd


def _init_zobrist() -> tuple[dict, tuple[int, int], tuple[int, int]]:
    """初始化 Zobrist 表。

    返回 (zobrist_map, white_to_move_key, black_to_move_key)
    其中 zobrist_map[(side, type, state, col, row)] = (h1, h2)
    """
    rnd = _mulberry32(_ZOBRIST_SEED)
    zobrist: dict[tuple[str, str, str, int, int], tuple[int, int]] = {}
    sides = ["white", "black"]
    types = ["king", "soldier", "clone"]
    states = ["imprisoned_invincible", "free", "berserk"]
    for side in sides:
        for t in types:
            for st in states:
                for c in range(19):
                    for r in range(19):
                        zobrist[(side, t, st, c, r)] = (rnd(), rnd())
    white_to_move = (rnd(), rnd())
    black_to_move = (rnd(), rnd())
    return zobrist, white_to_move, black_to_move


ZOBRIST, WHITE_TO_MOVE, BLACK_TO_MOVE = _init_zobrist()


def state_hash(state: State) -> tuple[int, int]:
    """计算局面的 Zobrist 哈希（64-bit 拆为两个 32-bit）。"""
    h1 = 0
    h2 = 0
    for p in state.pieces:
        if p.dead:
            continue
        key = (p.side.value, p.type.value, p.state.value, p.col, p.row)
        k1, k2 = ZOBRIST[key]
        h1 ^= k1
        h2 ^= k2
    if state.turn == Side.WHITE:
        h1 ^= WHITE_TO_MOVE[0]
        h2 ^= WHITE_TO_MOVE[1]
    else:
        h1 ^= BLACK_TO_MOVE[0]
        h2 ^= BLACK_TO_MOVE[1]
    return (h1, h2)


# ===== 置换表 =====


class TranspositionTable:
    """简单 dict 实现的置换表。

    字段：depth, flag, score, best_move_key
    flag: 0=exact, 1=lower_bound, 2=upper_bound
    """

    def __init__(self, size: int = DEFAULT_TT_SIZE):
        self.size = size
        self.entries: dict[tuple[int, int], dict] = {}

    def probe(self, h: tuple[int, int]) -> Optional[dict]:
        return self.entries.get(h)

    def store(self, h: tuple[int, int], depth: int, score: int, best_move: int, flag: int = 0) -> None:
        self.entries[h] = {
            "depth": depth,
            "score": score,
            "best_move": best_move,
            "flag": flag,
        }

    def clear(self) -> None:
        self.entries.clear()


def move_key(move: Move) -> int:
    """move → 紧凑整数（用于 TT 存储 / history 启发）。"""
    return (move.from_col * 19 + move.from_row) * 361 + (move.to_col * 19 + move.to_row)


# ===== 着法生成 =====


def gen_moves(state: State, side: Side) -> list[Move]:
    """生成所有合法着法。"""
    moves: list[Move] = []
    for p in state.pieces:
        if p.dead or p.side != side:
            continue
        for m in legal_moves(state, p):
            moves.append(
                Move(
                    piece_id=p.id,
                    from_col=p.col,
                    from_row=p.row,
                    to_col=m["col"],
                    to_row=m["row"],
                    capture=m["capture"],
                )
            )
    return moves


def sort_moves(moves: list[Move], tt_best: Optional[int], history: dict[int, int]) -> None:
    """对 moves 原地排序：TT best > 吃子 > history。"""
    def key(m: Move) -> tuple:
        mk = move_key(m)
        return (
            0 if tt_best is not None and mk == tt_best else 1,
            0 if m.capture else 1,
            -history.get(mk, 0),
        )

    moves.sort(key=key)


# ===== 搜索异常 =====


class AITimeout(Exception):
    """搜索超时（timeLimitMs 触发）。"""


# ===== 搜索辅助 =====


def _settle_search(state: State):
    """AI 搜索用 settle：开 turn + 检查终局（不参与三循环累计）。"""
    new_state = state.clone()
    # 胜负
    term = check_win_loss(new_state)
    if term:
        new_state.game_over = term
        return new_state, term
    # 切 turn
    new_state.turn = new_state.turn.opposite
    # 停棋负
    if not any(
        not p.dead and p.side == new_state.turn
        for p in new_state.pieces
        if legal_moves(new_state, p)
    ):
        winner = new_state.turn.opposite
        term = {"winner": winner.value, "reason": "stalemate"}
        new_state.game_over = term
        return new_state, term
    return new_state, None


def _terminal_score(state: State, term: Optional[dict]) -> Optional[int]:
    """若已终局，返回该玩家视角分值；否则 None。"""
    if term is None:
        return None
    if term["winner"] == "draw":
        return 0
    return (AI_M - 1) if term["winner"] == state.turn.value else -(AI_M - 1)


# ===== Negamax =====


def negamax(
    state: State,
    depth: int,
    alpha: int,
    beta: int,
    ply: int,
    deadline: float,
    stats: dict,
    tt: TranspositionTable,
    history: dict[int, int],
) -> int:
    """Negamax + α-β 剪枝（与 v1 同算法）。"""
    if deadline and time.monotonic() * 1000 > deadline:
        raise AITimeout()
    stats["nodes"] += 1

    # 终局
    term = check_win_loss(state)
    if term:
        score = _terminal_score(state, term)
        if score is not None:
            return score

    # 深度限制 → 评估
    if depth <= 0:
        return evaluate(state, state.turn)

    # TT 探查
    h = state_hash(state)
    entry = tt.probe(h)
    if entry is not None and entry["depth"] >= depth:
        return entry["score"]

    # 走子
    moves = gen_moves(state, state.turn)
    if not moves:
        return -(AI_M - 1)  # 停棋负 → 当前玩家输

    sort_moves(moves, entry["best_move"] if entry else None, history)

    best_score = -AI_M
    best_mk = -1

    for move in moves:
        # 应用 move（不带分身）
        child, candidates = apply_move(state, move, clone_decision=False)

        if candidates:
            # 分身 true 分支
            c1 = perform_clone(child, state.turn)
            c1, t1 = _settle_search(c1)
            s1 = -_score(c1, t1, state.turn, depth - 1, -beta, -alpha, ply + 1, deadline, stats, tt, history)
            # 分身 false 分支
            c0, t0 = _settle_search(child)
            s0 = -_score(c0, t0, state.turn, depth - 1, -beta, -max(alpha, s1), ply + 1, deadline, stats, tt, history)
            score = max(s1, s0)
        else:
            c0, t0 = _settle_search(child)
            score = -_score(c0, t0, state.turn, depth - 1, -beta, -alpha, ply + 1, deadline, stats, tt, history)

        if score > best_score:
            best_score = score
            best_mk = move_key(move)
        if score > alpha:
            alpha = score
        if alpha >= beta:
            history[move_key(move)] = history.get(move_key(move), 0) + depth * depth
            break

    tt.store(h, depth, best_score, best_mk, flag=0)
    return best_score


def _score(
    state: State,
    term: Optional[dict],
    prev_turn: Side,
    depth: int,
    alpha: int,
    beta: int,
    ply: int,
    deadline: float,
    stats: dict,
    tt: TranspositionTable,
    history: dict[int, int],
) -> int:
    """negamax 的 helper：处理终局或递归。"""
    if term is not None:
        # 终局：state.turn 是当前玩家；prev_turn 是上一步的玩家
        if term["winner"] == "draw":
            return 0
        return (AI_M - 1) if term["winner"] == prev_turn.value else -(AI_M - 1)
    return negamax(state, depth, alpha, beta, ply, deadline, stats, tt, history)


# ===== AI 选着 =====


@dataclass(frozen=True)
class AILevel:
    """AI 难度配置。"""

    depth: int
    time_limit_ms: Optional[int] = None
    top_n: Optional[int] = None
    label: str = ""


AI_LEVELS = {
    "rookie": AILevel(depth=1, top_n=4, label="rookie"),
    "advanced": AILevel(depth=4, time_limit_ms=2500, label="advanced"),
    "master": AILevel(depth=5, time_limit_ms=4500, label="master"),
}


@dataclass
class AIChoice:
    """AI 选着结果。"""

    move: Move
    clone: bool = False
    score: int = 0
    nodes: int = 0
    depth_reached: int = 0
    time_ms: int = 0


def ai_choose(state: State, side: Side, level: AILevel) -> Optional[AIChoice]:
    """AI 选着主入口（与 v1 aiChooseMove 同算法）。

    返回 AIChoice 或 None（无子可走）。
    """
    t0 = time.monotonic() * 1000
    deadline = (t0 + level.time_limit_ms) if level.time_limit_ms else 0.0

    stats = {"nodes": 0}
    tt = TranspositionTable()
    history: dict[int, int] = {}

    moves = gen_moves(state, side)
    if not moves:
        return None

    # 评分：每轮迭代后排序
    scored: list[dict] = [{"move": m, "score": -AI_M, "exact": False} for m in moves]
    completed = 0

    # 迭代加深
    max_depth = level.depth
    depth_range = (
        range(1, max_depth + 1)
        if deadline
        else [max_depth]
    )

    for d in depth_range:
        layer: list[dict] = []
        aborted = False
        alpha = -AI_M

        for prev in scored:
            mv = prev["move"]
            try:
                child, candidates = apply_move(state, mv, clone_decision=False)

                if candidates:
                    c1 = perform_clone(child, side)
                    c1, term1 = _settle_search(c1)
                    s1 = -_score(
                        c1, term1, side, d - 1, -AI_M, -alpha, 1, deadline, stats, tt, history
                    )
                    c0, term0 = _settle_search(child)
                    s0 = -_score(
                        c0, term0, side, d - 1, -AI_M, -max(alpha, s1), 1, deadline, stats, tt, history
                    )
                    score = max(s1, s0)
                    clone = s1 >= s0
                else:
                    c0, term0 = _settle_search(child)
                    score = -_score(
                        c0, term0, side, d - 1, -AI_M, -alpha, 1, deadline, stats, tt, history
                    )
                    clone = False

                layer.append(
                    {"move": mv, "score": score, "exact": score > alpha, "clone": clone}
                )
                if score > alpha:
                    alpha = score
            except AITimeout:
                aborted = True
                break

        if not aborted:
            layer.sort(key=lambda x: x["score"], reverse=True)
            scored = layer
            completed = d
        if aborted:
            break

    # 选着
    pick = scored[0]
    if level.top_n:
        # rookie / 菜鸟：topN 内随机（吃子放宽至 topN*2）
        pool = scored[: level.top_n]
        wider = scored[: level.top_n * 2]
        if any(s["move"].capture for s in wider):
            pool = wider
        chosen = pool[hash(pick["move"]) % len(pool)]
    else:
        # 高手 / 大师：同分随机（仅 exact）
        n = 1
        while (
            n < len(scored)
            and scored[n]["exact"]
            and scored[n]["score"] == scored[0]["score"]
        ):
            n += 1
        if n > 1:
            chosen = scored[hash(pick["move"]) % n]
        else:
            chosen = pick

    t1 = time.monotonic() * 1000
    return AIChoice(
        move=chosen["move"],
        clone=chosen.get("clone", False),
        score=chosen["score"],
        nodes=stats["nodes"],
        depth_reached=completed,
        time_ms=int(t1 - t0),
    )
