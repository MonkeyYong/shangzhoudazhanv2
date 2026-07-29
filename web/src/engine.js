// engine.js - JavaScript 镜像 Python 引擎（v2 商周大战）
//
// 设计目标（docs/v2-architecture.md）：
// - 同名函数（snake_case 风格，与 Python 对齐）
// - 同输入输出（State 对象结构对齐）
// - 同算法（Negamax + α-β + Zobrist + 置换表）
// - 浏览器运行时 + 可被 Node.js 直接加载测试
//
// 用法：
//   import { applyMove, aiChoose, ... } from './engine.js';
//   <script type="module">
//     import * as engine from './src/engine.js';
//     window.engine = engine;
//   </script>

// ===== 常量 =====
export const SIZE = 19;
export const COL_LETTERS = "ABCDEFGHJKLMNOPQRST"; // 跳过 I
export const COLS = COL_LETTERS;
export const WHITE_PALACE = [7, 11, 0, 3];   // H-M / 1-4
export const BLACK_PALACE = [7, 11, 15, 18]; // H-M / 16-19

// ===== 枚举（用对象 + 字符串值） =====
export const SIDE = { WHITE: "white", BLACK: "black" };
export const PIECE_TYPE = { KING: "king", SOLDIER: "soldier", CLONE: "clone" };
export const KING_STATE = {
  IMPRISONED_INVINCIBLE: "imprisoned_invincible",
  FREE: "free",
  BERSERK: "berserk",
};

const DIRS_8 = [
  [0, 1], [0, -1], [1, 0], [-1, 0],
  [1, 1], [1, -1], [-1, 1], [-1, -1],
];

const MAX_STEP_NORMAL = 2;
const MAX_STEP_BERSERK = 18;

// ===== 坐标 =====
export function inPalace(side, col, row) {
  const [c0, c1, r0, r1] = side === SIDE.WHITE ? WHITE_PALACE : BLACK_PALACE;
  return col >= c0 && col <= c1 && row >= r0 && row <= r1;
}

export function coordToStr(col, row) {
  return COL_LETTERS[col] + (row + 1);
}

export function strToCoord(s) {
  s = s.trim().toUpperCase();
  if (s.length < 2) throw new Error(`坐标格式错误: ${s}`);
  const col = COL_LETTERS.indexOf(s[0]);
  const row = parseInt(s.slice(1), 10) - 1;
  return [col, row];
}

// ===== 状态构造 =====
function makePiece(id, side, type, col, row, extras = {}) {
  return {
    id,
    side,
    type,
    col,
    row,
    state: extras.state ?? KING_STATE.FREE,
    is_clone: extras.is_clone ?? false,
    has_moved: extras.has_moved ?? false,
    actively_unlocked: extras.actively_unlocked ?? false,
    dead: extras.dead ?? false,
  };
}

export function stateClone(state) {
  return {
    pieces: state.pieces.map(p => ({ ...p })),
    turn: state.turn,
    side_lost_clone: { ...state.side_lost_clone },
    side_clone_unlocked: { ...state.side_clone_unlocked },
    step_count: state.step_count,
    game_over: state.game_over ? { ...state.game_over } : null,
  };
}

// ===== 预设 =====
const WHITE_HALF = {
  small: [
    ["king", 9, 18],
    ["soldier", 7, 0], ["soldier", 11, 0], ["soldier", 9, 2],
    ["soldier", 6, 4], ["soldier", 12, 4], ["soldier", 9, 6],
  ],
  battle: [
    ["king", 9, 18],
    ["soldier", 7, 0], ["soldier", 11, 0], ["soldier", 9, 2],
    ["soldier", 7, 3], ["soldier", 11, 3],
    ["soldier", 5, 5], ["soldier", 9, 5], ["soldier", 13, 5],
    ["soldier", 7, 7], ["soldier", 11, 7],
  ],
  final: [
    ["king", 9, 18],
    ["soldier", 7, 0], ["soldier", 11, 0],
    ["soldier", 5, 1], ["soldier", 13, 1],
    ["soldier", 9, 2],
    ["soldier", 3, 3], ["soldier", 7, 3], ["soldier", 11, 3], ["soldier", 15, 3],
    ["soldier", 5, 5], ["soldier", 9, 5], ["soldier", 13, 5],
    ["soldier", 3, 7], ["soldier", 7, 7], ["soldier", 11, 7], ["soldier", 15, 7],
  ],
};

export const PRESETS = {
  small: { name: "小局", layout: buildLayout("small") },
  battle: { name: "大战", layout: buildLayout("battle") },
  final: { name: "决战", layout: buildLayout("final") },
};

export function buildLayout(key) {
  const half = WHITE_HALF[key];
  if (!half) throw new Error(`未知 preset: ${key}`);
  const out = [];
  for (const [type, c, r] of half) {
    out.push(["white", type, c, r]);
    out.push(["black", type, 18 - c, 18 - r]);
  }
  return out;
}

export function stateFromPreset(name) {
  const layout = buildLayout(name);
  let nextId = 1;
  const pieces = [];
  for (const [side, type, col, row] of layout) {
    pieces.push(makePiece(
      nextId++,
      side,
      type,
      col,
      row,
      { state: type === PIECE_TYPE.KING ? KING_STATE.IMPRISONED_INVINCIBLE : KING_STATE.FREE },
    ));
  }
  return {
    pieces,
    turn: SIDE.WHITE,
    side_lost_clone: { white: false, black: false },
    side_clone_unlocked: { white: false, black: false },
    step_count: 0,
    game_over: null,
  };
}

// ===== 基础查询 =====
export function pieceAt(state, col, row) {
  for (const p of state.pieces) {
    if (p.dead) continue;
    if (p.col === col && p.row === row) return p;
  }
  return null;
}

export function kingOf(state, side) {
  for (const p of state.pieces) {
    if (p.dead) continue;
    if (p.side === side && p.type === PIECE_TYPE.KING && !p.is_clone) return p;
  }
  return null;
}

export function bigCount(state, side) {
  let n = 0;
  for (const p of state.pieces) {
    if (!p.dead && p.side === side && (p.type === PIECE_TYPE.KING || p.type === PIECE_TYPE.CLONE)) n++;
  }
  return n;
}

export function cloneCount(state, side) {
  let n = 0;
  for (const p of state.pieces) {
    if (!p.dead && p.side === side && p.type === PIECE_TYPE.CLONE) n++;
  }
  return n;
}

export function soldiersOf(state, side) {
  let n = 0;
  for (const p of state.pieces) {
    if (!p.dead && p.side === side && p.type === PIECE_TYPE.SOLDIER) n++;
  }
  return n;
}

// ===== 移动范围 =====
function _maxStep(piece) {
  return piece.state === KING_STATE.BERSERK ? MAX_STEP_BERSERK : MAX_STEP_NORMAL;
}

export function reachableCells(state, piece) {
  if (piece.state === KING_STATE.IMPRISONED_INVINCIBLE) return [];
  const moves = [];
  const maxStep = _maxStep(piece);
  for (const [dc, dr] of DIRS_8) {
    for (let s = 1; s <= maxStep; s++) {
      const nc = piece.col + dc * s;
      const nr = piece.row + dr * s;
      if (nc < 0 || nc >= SIZE || nr < 0 || nr >= SIZE) break;
      const occ = pieceAt(state, nc, nr);
      if (!occ) {
        moves.push({ col: nc, row: nr, capture: false });
      } else if (occ.side !== piece.side) {
        moves.push({ col: nc, row: nr, capture: true });
        break;
      } else {
        continue; // 己方可穿过
      }
    }
  }
  return moves;
}

export function legalMoves(state, piece) {
  return reachableCells(state, piece).filter(m => {
    if (!m.capture) return true;
    const t = pieceAt(state, m.col, m.row);
    return !(t && t.type === PIECE_TYPE.KING && !t.has_moved);
  });
}

export function theoreticalRange(state, king) {
  if (king.type !== PIECE_TYPE.KING && king.type !== PIECE_TYPE.CLONE) return new Set();
  const maxStep = _maxStep(king);
  const cells = new Set();
  for (const [dc, dr] of DIRS_8) {
    for (let s = 1; s <= maxStep; s++) {
      const nc = king.col + dc * s;
      const nr = king.row + dr * s;
      if (nc < 0 || nc >= SIZE || nr < 0 || nr >= SIZE) break;
      cells.add(nc + "," + nr);
    }
  }
  return cells;
}

// ===== 武王状态 =====
export function isImprisoned(state, king) {
  if (king.type !== PIECE_TYPE.KING || king.is_clone) return false;
  let n = 0;
  for (const p of state.pieces) {
    if (p.dead || p.side === king.side) continue;
    if (p.state === KING_STATE.IMPRISONED_INVINCIBLE) continue;
    for (const m of reachableCells(state, p)) {
      if (m.col === king.col && m.row === king.row) { n++; break; }
    }
    if (n >= 2) return true;
  }
  return false;
}

export function recomputeKingStates(state) {
  const newState = stateClone(state);
  for (let i = 0; i < newState.pieces.length; i++) {
    const p = newState.pieces[i];
    if (p.dead || p.type !== PIECE_TYPE.KING || p.is_clone) continue;
    if (p.state === KING_STATE.BERSERK) continue;
    if (p.has_moved || p.actively_unlocked) {
      p.state = KING_STATE.FREE;
    } else if (isImprisoned(state, p)) {
      p.state = KING_STATE.IMPRISONED_INVINCIBLE;
    } else {
      p.state = KING_STATE.FREE;
    }
  }
  return newState;
}

export function activeUnlockCheck(state, moved) {
  const newState = stateClone(state);
  for (let i = 0; i < newState.pieces.length; i++) {
    const k = newState.pieces[i];
    if (k.dead || k.side !== moved.side) continue;
    if (k.type !== PIECE_TYPE.KING || k.is_clone) continue;
    if (k.state !== KING_STATE.IMPRISONED_INVINCIBLE) continue;
    if (theoreticalRange(state, k).has(moved.col + "," + moved.row)) {
      k.state = KING_STATE.FREE;
      k.actively_unlocked = true;
    }
  }
  return newState;
}

export function berserkCheck(state, moved) {
  const newState = stateClone(state);
  const idx = newState.pieces.findIndex(p => p.id === moved.id);
  if (idx < 0) return newState;
  const movedU = newState.pieces[idx];
  if (movedU.type !== PIECE_TYPE.KING && movedU.type !== PIECE_TYPE.CLONE) return newState;
  if (movedU.state === KING_STATE.BERSERK) return newState;
  if (!inPalace(movedU.side, movedU.col, movedU.row)) return newState;

  newState.pieces[idx] = {
    ...movedU,
    state: KING_STATE.BERSERK,
    has_moved: movedU.type === PIECE_TYPE.KING ? true : movedU.has_moved,
  };
  newState.side_lost_clone[movedU.side] = true;

  for (let i = 0; i < newState.pieces.length; i++) {
    const k = newState.pieces[i];
    if (k.dead || k.side === movedU.side) continue;
    if (k.type !== PIECE_TYPE.KING || k.is_clone) continue;
    newState.pieces[i] = { ...k, state: KING_STATE.FREE, has_moved: true, actively_unlocked: true };
  }
  return newState;
}

// ===== 分身 =====
function inAnyFriendlyBigRange(state, soldier) {
  for (const k of state.pieces) {
    if (k.dead || k.side !== soldier.side) continue;
    if (k.type !== PIECE_TYPE.KING && k.type !== PIECE_TYPE.CLONE) continue;
    if (theoreticalRange(state, k).has(soldier.col + "," + soldier.row)) return true;
  }
  return false;
}

export function cloneOfferCheck(state, moved) {
  const newState = stateClone(state);
  const candidates = [];
  if (newState.side_lost_clone[moved.side]) return [newState, candidates];
  if (!newState.side_clone_unlocked[moved.side]) return [newState, candidates];
  if (bigCount(state, moved.side) >= 2) return [newState, candidates];

  if (moved.type === PIECE_TYPE.SOLDIER) {
    if (inAnyFriendlyBigRange(state, moved)) candidates.push(moved);
  } else if (moved.type === PIECE_TYPE.KING || moved.type === PIECE_TYPE.CLONE) {
    const range = theoreticalRange(state, moved);
    for (const s of state.pieces) {
      if (s.dead || s.side !== moved.side || s.type !== PIECE_TYPE.SOLDIER) continue;
      if (range.has(s.col + "," + s.row)) candidates.push(s);
    }
  }
  return [newState, candidates];
}

export function performClone(state, side) {
  const newState = stateClone(state);
  const candidates = newState.pieces.filter(p => !p.dead && p.side === side && p.type === PIECE_TYPE.SOLDIER);
  if (candidates.length === 0) return newState;
  if (bigCount(newState, side) >= 2) return newState;
  const s = candidates[0];
  const idx = newState.pieces.findIndex(p => p.id === s.id);
  newState.pieces[idx] = {
    ...s,
    type: PIECE_TYPE.CLONE,
    is_clone: true,
    state: KING_STATE.FREE,
    has_moved: false,
    actively_unlocked: false,
  };
  let next = berserkCheck(newState, newState.pieces[idx]);
  return recomputeKingStates(next);
}

// ===== 胜负 / 停棋 / 平局 =====
export function sideUnlocked(state, side) {
  for (const p of state.pieces) {
    if (p.dead || p.side !== side) continue;
    if (p.type === PIECE_TYPE.CLONE) return true;
    if (p.type === PIECE_TYPE.KING && p.state !== KING_STATE.IMPRISONED_INVINCIBLE) return true;
  }
  return false;
}

export function checkWinLoss(state) {
  const wBig = bigCount(state, SIDE.WHITE);
  const bBig = bigCount(state, SIDE.BLACK);
  if (wBig === 0 && sideUnlocked(state, SIDE.BLACK)) return { winner: SIDE.BLACK, reason: "black_kings_all_captured" };
  if (bBig === 0 && sideUnlocked(state, SIDE.WHITE)) return { winner: SIDE.WHITE, reason: "white_kings_all_captured" };
  const wKing = kingOf(state, SIDE.WHITE);
  const bKing = kingOf(state, SIDE.BLACK);
  if (wKing && wKing.state === KING_STATE.IMPRISONED_INVINCIBLE && soldiersOf(state, SIDE.WHITE) === 0) {
    return { winner: SIDE.BLACK, reason: "white_king_imprisoned_no_soldiers" };
  }
  if (bKing && bKing.state === KING_STATE.IMPRISONED_INVINCIBLE && soldiersOf(state, SIDE.BLACK) === 0) {
    return { winner: SIDE.WHITE, reason: "black_king_imprisoned_no_soldiers" };
  }
  return null;
}

export function hasAnyMove(state, side) {
  for (const p of state.pieces) {
    if (p.dead || p.side !== side) continue;
    if (legalMoves(state, p).length > 0) return true;
  }
  return false;
}

export function positionHash(state) {
  const arr = state.pieces
    .filter(p => !p.dead)
    .map(p => `${p.side[0]}${p.type[0]}${p.col},${p.row},${p.state[0]}${p.has_moved ? 1 : 0}${p.actively_unlocked ? 1 : 0}`)
    .sort()
    .join("|");
  return state.turn + "|" + arr + "|" +
    (state.side_lost_clone.white ? 1 : 0) +
    (state.side_lost_clone.black ? 1 : 0) +
    (state.side_clone_unlocked.white ? 1 : 0) +
    (state.side_clone_unlocked.black ? 1 : 0);
}

// ===== 行动执行 =====
function findPieceById(state, id) {
  return state.pieces.find(p => p.id === id);
}

export function applyMove(state, move, cloneDecision = false) {
  const newState = stateClone(state);
  const piece = findPieceById(newState, move.piece_id);
  if (!piece) throw new Error(`找不到 piece_id=${move.piece_id}`);

  // 吃子
  if (move.capture) {
    const target = pieceAt(newState, move.to_col, move.to_row);
    if (target && target.side !== move.side) {
      const idx = newState.pieces.findIndex(p => p.id === target.id);
      newState.pieces[idx] = { ...target, dead: true };
    }
  }

  // 移动
  let idx = newState.pieces.findIndex(p => p.id === move.piece_id);
  let moved = { ...newState.pieces[idx], col: move.to_col, row: move.to_row };
  newState.pieces[idx] = moved;

  // 武王首次移动
  if (moved.type === PIECE_TYPE.KING && !moved.is_clone && !moved.has_moved) {
    moved = { ...moved, has_moved: true };
    newState.pieces[idx] = moved;
    newState.side_clone_unlocked[moved.side] = true;
  }

  // 暴走
  let s = berserkCheck(newState, moved);
  moved = s.pieces.find(p => p.id === moved.id);

  // 主动解锁
  s = activeUnlockCheck(s, moved);

  // 分身
  const [s2, candidates] = cloneOfferCheck(s, moved);

  // 重算
  let final = recomputeKingStates(s2);

  if (cloneDecision && candidates.length > 0) {
    final = performClone(final, moved.side);
  }
  return [final, candidates];
}

export function endTurn(state, positionCount = null) {
  const newState = stateClone(state);
  newState.step_count++;

  const term = checkWinLoss(newState);
  if (term) {
    newState.game_over = term;
    return [newState, term];
  }

  newState.turn = newState.turn === SIDE.WHITE ? SIDE.BLACK : SIDE.WHITE;

  if (!hasAnyMove(newState, newState.turn)) {
    const winner = newState.turn === SIDE.WHITE ? SIDE.BLACK : SIDE.WHITE;
    const t = { winner, reason: "stalemate" };
    newState.game_over = t;
    return [newState, t];
  }

  if (positionCount) {
    const h = positionHash(newState);
    positionCount[h] = (positionCount[h] || 0) + 1;
    if (positionCount[h] >= 3) {
      const t = { winner: "draw", reason: "threefold_repetition" };
      newState.game_over = t;
      return [newState, t];
    }
  }

  return [newState, null];
}

// ===== 评估函数 =====
function _hasAnyReach(state, piece) {
  return legalMoves(state, piece).length > 0;
}

function _coverage(state, king) {
  if (!king) return 0;
  let n = 0;
  for (const p of state.pieces) {
    if (p.dead || p.side === king.side || p.type !== PIECE_TYPE.SOLDIER) continue;
    if (Math.max(Math.abs(p.col - king.col), Math.abs(p.row - king.row)) <= 2) n++;
  }
  return n;
}

function _aiCloneOption(state, side) {
  if (state.side_lost_clone[side]) return 0;
  if (!state.side_clone_unlocked[side]) return 0;
  if (bigCount(state, side) >= 2) return 0;
  for (const s of state.pieces) {
    if (s.dead || s.side !== side || s.type !== PIECE_TYPE.SOLDIER) continue;
    for (const k of state.pieces) {
      if (k.dead || k.side !== side) continue;
      if (k.type !== PIECE_TYPE.KING && k.type !== PIECE_TYPE.CLONE) continue;
      if (Math.max(Math.abs(s.col - k.col), Math.abs(s.row - k.row)) <= 2) return 1;
    }
  }
  return 0;
}

export function evaluate(state, side) {
  const opp = side === SIDE.WHITE ? SIDE.BLACK : SIDE.WHITE;
  let myS = 0, opS = 0, myMob = 0, opMob = 0, mySoldiers = 0, opSoldiers = 0;
  let myKing = null, opKing = null;

  for (const p of state.pieces) {
    if (p.dead) continue;
    let v = 0;
    if (p.type === PIECE_TYPE.SOLDIER) {
      v = 100;
      if (p.side === side) mySoldiers++;
      else opSoldiers++;
    } else if (p.type === PIECE_TYPE.CLONE) {
      v = 350;
    } else {
      v = 1500;
      if (p.state === KING_STATE.IMPRISONED_INVINCIBLE) v -= 500;
      else if (!p.has_moved) v += 200;
    }
    if (p.state === KING_STATE.BERSERK) v += 400;
    if (p.side === side) myS += v;
    else opS += v;
    if (p.type === PIECE_TYPE.KING && !p.is_clone) {
      if (p.side === side) myKing = p;
      else opKing = p;
    }
    if (_hasAnyReach(state, p)) {
      if (p.side === side) myMob++;
      else opMob++;
    }
  }

  let score = (myS - opS) + (myMob - opMob) * 2;
  if (myKing && myKing.has_moved) score -= 300;
  if (opKing && opKing.has_moved) score += 300;
  if (myKing && myKing.state === KING_STATE.IMPRISONED_INVINCIBLE && mySoldiers <= 2) score -= (3 - mySoldiers) * 150;
  if (opKing && opKing.state === KING_STATE.IMPRISONED_INVINCIBLE && opSoldiers <= 2) score += (3 - opSoldiers) * 150;
  score += _aiCloneOption(state, side) - _aiCloneOption(state, opp);

  if (opKing) {
    score += _coverage(state, opKing) * 50;
    for (const s of state.pieces) {
      if (s.dead || s.side !== side || s.type !== PIECE_TYPE.SOLDIER) continue;
      const d = Math.max(Math.abs(s.col - opKing.col), Math.abs(s.row - opKing.row));
      score += Math.max(0, 12 - d) * 5;
    }
  }

  if (myKing && myKing.state === KING_STATE.IMPRISONED_INVINCIBLE) {
    let best = 99;
    for (const s of state.pieces) {
      if (s.dead || s.side !== side || s.type !== PIECE_TYPE.SOLDIER) continue;
      const d = Math.max(Math.abs(s.col - myKing.col), Math.abs(s.row - myKing.row));
      if (d < best) best = d;
    }
    if (best < 99) {
      score += Math.max(0, 12 - best) * 6 + (best <= 2 ? 100 : 0);
    }
  }
  return score;
}

// ===== Zobrist 哈希 =====
const ZOBRIST_SEED = 0xA1B2C3D4;

function _mulberry32(seed) {
  let state = seed & 0xFFFFFFFF;
  return function () {
    state = (state + 0x6D2B79F5) & 0xFFFFFFFF;
    let t = state;
    t = ((t ^ (t >>> 15)) * (t | 1)) & 0xFFFFFFFF;
    t = (t ^ (t + (((t ^ (t >>> 7)) * (t | 61)) & 0xFFFFFFFF))) & 0xFFFFFFFF;
    return ((t ^ (t >>> 14)) >>> 0);
  };
}

function _initZobrist() {
  const rnd = _mulberry32(ZOBRIST_SEED);
  const z = {};
  const sides = ["white", "black"];
  const types = ["king", "soldier", "clone"];
  const states = ["imprisoned_invincible", "free", "berserk"];
  for (const side of sides) {
    for (const t of types) {
      for (const st of states) {
        for (let c = 0; c < SIZE; c++) {
          for (let r = 0; r < SIZE; r++) {
            z[`${side}|${t}|${st}|${c}|${r}`] = [rnd(), rnd()];
          }
        }
      }
    }
  }
  return { z, whiteToMove: [rnd(), rnd()], blackToMove: [rnd(), rnd()] };
}

const { z: ZOBRIST, whiteToMove: WHITE_TO_MOVE, blackToMove: BLACK_TO_MOVE } = _initZobrist();

export function stateHash(state) {
  let h1 = 0, h2 = 0;
  for (const p of state.pieces) {
    if (p.dead) continue;
    const key = `${p.side}|${p.type}|${p.state}|${p.col}|${p.row}`;
    const [k1, k2] = ZOBRIST[key];
    h1 ^= k1;
    h2 ^= k2;
  }
  const turnKey = state.turn === SIDE.WHITE ? WHITE_TO_MOVE : BLACK_TO_MOVE;
  h1 ^= turnKey[0];
  h2 ^= turnKey[1];
  return [h1, h2];
}

// ===== AI 引擎 =====
const DEFAULT_TT_SIZE = 1 << 18;
const AI_M = 1_000_000;

export const AI_LEVELS = {
  rookie: { depth: 1, top_n: 4, label: "rookie" },
  advanced: { depth: 4, time_limit_ms: 2500, label: "advanced" },
  master: { depth: 5, time_limit_ms: 4500, label: "master" },
};

class AITimeout extends Error {
  constructor() { super("AI_TIMEOUT"); this.name = "AITimeout"; }
}

function moveKey(move) {
  return (move.from_col * 19 + move.from_row) * 361 + (move.to_col * 19 + move.to_row);
}

function genMoves(state, side) {
  const moves = [];
  for (const p of state.pieces) {
    if (p.dead || p.side !== side) continue;
    for (const m of legalMoves(state, p)) {
      moves.push({
        piece_id: p.id,
        from_col: p.col,
        from_row: p.row,
        to_col: m.col,
        to_row: m.row,
        capture: m.capture,
        clone: false,
      });
    }
  }
  return moves;
}

function sortMoves(moves, ttBest, history) {
  moves.sort((a, b) => {
    const aKey = moveKey(a);
    const bKey = moveKey(b);
    const aTt = (ttBest != null && aKey === ttBest) ? 0 : 1;
    const bTt = (ttBest != null && bKey === ttBest) ? 0 : 1;
    if (aTt !== bTt) return aTt - bTt;
    const aCap = a.capture ? 0 : 1;
    const bCap = b.capture ? 0 : 1;
    if (aCap !== bCap) return aCap - bCap;
    return (history[bKey] || 0) - (history[aKey] || 0);
  });
}

function settleSearch(state) {
  const newState = stateClone(state);
  const term = checkWinLoss(newState);
  if (term) {
    newState.game_over = term;
    return [newState, term];
  }
  newState.turn = newState.turn === SIDE.WHITE ? SIDE.BLACK : SIDE.WHITE;
  if (!hasAnyMove(newState, newState.turn)) {
    const winner = newState.turn === SIDE.WHITE ? SIDE.BLACK : SIDE.WHITE;
    const t = { winner, reason: "stalemate" };
    newState.game_over = t;
    return [newState, t];
  }
  return [newState, null];
}

function negamax(state, depth, alpha, beta, ply, deadline, stats, tt, history) {
  if (deadline && performance.now() > deadline) throw new AITimeout();
  stats.nodes++;
  const term = checkWinLoss(state);
  if (term) {
    if (term.winner === "draw") return 0;
    return (term.winner === state.turn) ? (AI_M - 1) : -(AI_M - 1);
  }
  if (depth <= 0) return evaluate(state, state.turn);
  const h = stateHash(state);
  const entry = tt.get(h[0] + "|" + h[1]);
  if (entry && entry.depth >= depth) return entry.score;

  const moves = genMoves(state, state.turn);
  if (moves.length === 0) return -(AI_M - 1);

  sortMoves(moves, entry ? entry.best_move : null, history);

  let bestScore = -AI_M;
  let bestMk = -1;

  for (const move of moves) {
    const [child, candidates] = applyMove(state, move, false);
    let score;
    if (candidates.length > 0) {
      const c1 = performClone(child, state.turn);
      const [s1, t1] = settleSearch(c1);
      const r1 = _score(s1, t1, state.turn, depth - 1, -beta, -alpha, ply + 1, deadline, stats, tt, history);
      const [c0, t0] = settleSearch(child);
      const r0 = _score(c0, t0, state.turn, depth - 1, -beta, -Math.max(alpha, r1), ply + 1, deadline, stats, tt, history);
      score = Math.max(r1, r0);
    } else {
      const [c0, t0] = settleSearch(child);
      score = -_score(c0, t0, state.turn, depth - 1, -beta, -alpha, ply + 1, deadline, stats, tt, history);
    }
    if (score > bestScore) { bestScore = score; bestMk = moveKey(move); }
    if (score > alpha) alpha = score;
    if (alpha >= beta) {
      const mk = moveKey(move);
      history[mk] = (history[mk] || 0) + depth * depth;
      break;
    }
  }
  tt.set(h[0] + "|" + h[1], { depth, score: bestScore, best_move: bestMk, flag: 0 });
  return bestScore;
}

function _score(state, term, prevTurn, depth, alpha, beta, ply, deadline, stats, tt, history) {
  if (term) {
    if (term.winner === "draw") return 0;
    return (term.winner === prevTurn) ? (AI_M - 1) : -(AI_M - 1);
  }
  return negamax(state, depth, alpha, beta, ply, deadline, stats, tt, history);
}

// ===== AI 选着 =====
export function aiChoose(state, side, level) {
  const t0 = performance.now();
  const deadline = level.time_limit_ms ? (t0 + level.time_limit_ms) : 0;

  const stats = { nodes: 0 };
  const tt = new Map();
  const history = {};

  const moves = genMoves(state, side);
  if (moves.length === 0) return null;

  let scored = moves.map(m => ({ move: m, score: -AI_M, exact: false, clone: false }));
  let completed = 0;
  const maxDepth = level.depth;
  const depthRange = deadline ? null : [maxDepth];

  function doDepth(d) {
    const layer = [];
    let aborted = false;
    let alpha = -AI_M;
    for (const prev of scored) {
      const mv = prev.move;
      try {
        const [child, candidates] = applyMove(state, mv, false);
        let score, clone = false;
        if (candidates.length > 0) {
          const c1 = performClone(child, side);
          const [s1, t1] = settleSearch(c1);
          const r1 = -_score(s1, t1, side, d - 1, -AI_M, -alpha, 1, deadline, stats, tt, history);
          const [c0, t0] = settleSearch(child);
          const r0 = -_score(c0, t0, side, d - 1, -AI_M, -Math.max(alpha, r1), 1, deadline, stats, tt, history);
          score = Math.max(r1, r0);
          clone = r1 >= r0;
        } else {
          const [c0, t0] = settleSearch(child);
          score = -_score(c0, t0, side, d - 1, -AI_M, -alpha, 1, deadline, stats, tt, history);
        }
        layer.push({ move: mv, score, exact: score > alpha, clone });
        if (score > alpha) alpha = score;
      } catch (e) {
        if (e instanceof AITimeout) { aborted = true; break; }
        throw e;
      }
    }
    if (!aborted) {
      layer.sort((a, b) => b.score - a.score);
      scored = layer;
      completed = d;
    }
    return !aborted;
  }

  if (deadline) {
    for (let d = 1; d <= maxDepth; d++) {
      if (!doDepth(d)) break;
    }
  } else {
    doDepth(maxDepth);
  }

  const pick = scored[0];
  let chosen = pick;
  if (level.top_n) {
    const pool = scored.slice(0, level.top_n);
    const wider = scored.slice(0, level.top_n * 2);
    if (wider.some(s => s.move.capture)) chosen = pool[Math.abs(hashMove(pick.move)) % pool.length];
    else chosen = pool[Math.abs(hashMove(pick.move)) % pool.length];
  } else {
    let n = 1;
    while (n < scored.length && scored[n].exact && scored[n].score === scored[0].score) n++;
    if (n > 1) chosen = scored[Math.abs(hashMove(pick.move)) % n];
  }

  const t1 = performance.now();
  return {
    move: chosen.move,
    clone: chosen.clone || false,
    score: chosen.score,
    nodes: stats.nodes,
    depth_reached: completed,
    time_ms: Math.round(t1 - t0),
  };
}

function hashMove(move) {
  return (move.piece_id * 31 + move.from_col * 19 + move.from_row) ^ (move.to_col * 19 + move.to_row);
}

// ===== 棋谱 =====
export function recordFromDict(d) {
  return {
    preset: d.preset || "battle",
    label: d.label || "",
    moves: Array.isArray(d.moves) ? [...d.moves] : [],
  };
}

export function recordToDict(r) {
  return { preset: r.preset, label: r.label, moves: [...r.moves] };
}

export function recordValidate(record) {
  const errors = [];
  if (!WHITE_HALF[record.preset]) {
    errors.push(`未知 preset: ${record.preset}`);
    return errors;
  }
  let state = stateFromPreset(record.preset);
  for (let i = 0; i < record.moves.length; i++) {
    const step = record.moves[i];
    if (!step || typeof step !== "object") {
      errors.push(`move[${i}] 不是 dict`);
      continue;
    }
    for (const k of ["from", "to"]) {
      if (!step[k]) errors.push(`move[${i}] 缺字段 ${k}`);
    }
    if (step.capture === undefined) errors.push(`move[${i}] 缺字段 'capture'`);
    if (step.clone === undefined) errors.push(`move[${i}] 缺字段 'clone'`);
    try {
      const [fc, fr] = strToCoord(step.from);
      const [tc, tr] = strToCoord(step.to);
      const piece = pieceAt(state, fc, fr);
      if (!piece) {
        errors.push(`move[${i}] ${step.from}: 无子`);
        break;
      }
      [state] = applyMove(state, {
        piece_id: piece.id,
        from_col: fc, from_row: fr,
        to_col: tc, to_row: tr,
        capture: !!step.capture,
      }, !!step.clone);
      [state] = endTurn(state);
    } catch (e) {
      errors.push(`move[${i}] ${step.from}: ${e.message}`);
      break;
    }
  }
  return errors;
}

// ===== 全局挂载（浏览器使用） =====
if (typeof window !== "undefined") {
  window.ShangZhouEngine = {
    SIZE, COL_LETTERS, COLS, WHITE_PALACE, BLACK_PALACE,
    SIDE, PIECE_TYPE, KING_STATE, PRESETS,
    inPalace, coordToStr, strToCoord,
    stateFromPreset, stateClone,
    pieceAt, kingOf, bigCount, cloneCount, soldiersOf,
    reachableCells, legalMoves, theoreticalRange,
    isImprisoned, recomputeKingStates, activeUnlockCheck,
    berserkCheck, cloneOfferCheck, performClone,
    sideUnlocked, checkWinLoss, hasAnyMove, positionHash,
    applyMove, endTurn,
    evaluate, stateHash, aiChoose, AI_LEVELS,
    recordFromDict, recordToDict, recordValidate,
  };
}
