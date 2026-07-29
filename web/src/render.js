// render.js - Canvas 渲染（v1 算法移植）
//
// 绘制顺序：
// 1. 棋盘背景（六宫格 + 渐变 + 边线）
// 2. 网格 / 坐标 / 王城（轮廓 + 装饰）
// 3. 高亮（选中 / 合法着法 / 吃子光环 / 悬停）
// 4. 棋子（按层次 / 阴影 / 立体感）

import { SIZE, COL_LETTERS, WHITE_PALACE, BLACK_PALACE, SIDE, KING_STATE, inPalace, coordToStr, pieceAt } from "./engine.js";

const LOGICAL_PX = 640;
const MARGIN = 32;
const CELL = (LOGICAL_PX - 2 * MARGIN) / (SIZE - 1); // 32px
const STONE_R_SMALL = 11;
const STONE_R_BIG = 14;
const HOVER_GROW = 0.12;
const SELECT_RING_R = 18;
const CAPTURE_RING_GAP = 4;
const CAPTURE_RING_W = 3;

const PAL_WHITE = {
  g0: [44, 156, 150], g1: [34, 112, 128], g2: [30, 82, 140],
  glow: [86, 224, 210], border: [52, 216, 200], borderSoft: [150, 240, 232],
  stud: [60, 210, 196], emFill: [190, 250, 244], emRing: [150, 236, 228],
};

const PAL_BLACK = {
  g0: [196, 46, 58], g1: [142, 30, 40], g2: [92, 18, 26],
  glow: [255, 86, 74], border: [232, 80, 72], borderSoft: [255, 150, 140],
  stud: [232, 90, 82], emFill: [255, 190, 185], emRing: [255, 150, 145],
};

export function fitCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const cssSize = Math.min(rect.width || LOGICAL_PX, LOGICAL_PX);
  canvas.style.width = cssSize + "px";
  canvas.style.height = cssSize + "px";
  canvas.width = Math.round(cssSize * dpr);
  canvas.height = Math.round(cssSize * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(cssSize * dpr / LOGICAL_PX, 0, 0, cssSize * dpr / LOGICAL_PX, 0, 0);
}

function cellToXY(col, row) {
  return [MARGIN + col * CELL, MARGIN + (SIZE - 1 - row) * CELL];
}

function xyToCell(x, y) {
  const col = Math.round((x - MARGIN) / CELL);
  const row = SIZE - 1 - Math.round((y - MARGIN) / CELL);
  if (col < 0 || col >= SIZE || row < 0 || row >= SIZE) return null;
  return [col, row];
}

export { cellToXY, xyToCell, LOGICAL_PX, MARGIN, CELL };

// ===== 主绘制函数 =====

export function render(ctx, state, options = {}) {
  const { selected, legalMoves, hoverCell, lastMove } = options;
  drawBoard(ctx);
  drawPalaceDecor(ctx);
  drawCoordinates(ctx);
  drawHighlights(ctx, selected, legalMoves, hoverCell, lastMove);
  drawPieces(ctx, state, hoverCell);
}

// ===== 棋盘背景 =====

function drawBoard(ctx) {
  // 暖色木纹底
  const bg = ctx.createLinearGradient(0, 0, LOGICAL_PX, LOGICAL_PX);
  bg.addColorStop(0, "#e8c674");
  bg.addColorStop(0.5, "#d8b35b");
  bg.addColorStop(1, "#c8a045");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, LOGICAL_PX, LOGICAL_PX);

  // 网格
  ctx.strokeStyle = "rgba(60, 30, 0, 0.55)";
  ctx.lineWidth = 1;
  for (let i = 0; i < SIZE; i++) {
    const [x1, y1] = cellToXY(i, 0);
    const [x2, y2] = cellToXY(i, SIZE - 1);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    const [x3, y3] = cellToXY(0, i);
    const [x4, y4] = cellToXY(SIZE - 1, i);
    ctx.beginPath();
    ctx.moveTo(x3, y3);
    ctx.lineTo(x4, y4);
    ctx.stroke();
  }

  // 边线（更粗）
  ctx.strokeStyle = "rgba(60, 30, 0, 0.85)";
  ctx.lineWidth = 2;
  ctx.strokeRect(MARGIN, MARGIN, LOGICAL_PX - 2 * MARGIN, LOGICAL_PX - 2 * MARGIN);
}

function drawCoordinates(ctx) {
  ctx.fillStyle = "rgba(60, 30, 0, 0.75)";
  ctx.font = "10px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (let i = 0; i < SIZE; i++) {
    const [x, _] = cellToXY(i, 0);
    ctx.fillText(COL_LETTERS[i], x, MARGIN / 2);
    const [x2, _2] = cellToXY(i, SIZE - 1);
    ctx.fillText(COL_LETTERS[i], x2, LOGICAL_PX - MARGIN / 2);
  }
  for (let i = 0; i < SIZE; i++) {
    const [_, y] = cellToXY(0, i);
    ctx.fillText(String(i + 1), MARGIN / 2, y);
    const [_, y2] = cellToXY(SIZE - 1, i);
    ctx.fillText(String(i + 1), LOGICAL_PX - MARGIN / 2, y2);
  }
}

function drawPalaceDecor(ctx) {
  drawPalace(ctx, "white", WHITE_PALACE);
  drawPalace(ctx, "black", BLACK_PALACE);
}

function drawPalace(ctx, side, [c0, c1, r0, r1]) {
  // 王城平台：高亮 + 边框
  const [xL, yT] = cellToXY(c0, r1);
  const [xR, yB] = cellToXY(c1, r0);
  const w = xR - xL;
  const h = yB - yT;

  const pal = side === "white" ? PAL_WHITE : PAL_BLACK;

  // 平台底色（半透明）
  const platformGrad = ctx.createLinearGradient(0, yT, 0, yT + h);
  platformGrad.addColorStop(0, rgba([...pal.g0, 0.18]));
  platformGrad.addColorStop(0.5, rgba([...pal.g1, 0.22]));
  platformGrad.addColorStop(1, rgba([...pal.g2, 0.18]));
  ctx.fillStyle = platformGrad;
  ctx.fillRect(xL - 2, yT - 2, w + 4, h + 4);

  // 王城边框
  ctx.strokeStyle = rgba([...pal.border, 0.7]);
  ctx.lineWidth = 1.5;
  ctx.strokeRect(xL, yT, w, h);

  // 王城四角铆钉
  const studs = [
    [xL, yT], [xR, yT], [xL, yB], [xR, yB],
  ];
  for (const [sx, sy] of studs) {
    ctx.beginPath();
    ctx.arc(sx, sy, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = rgba([...pal.stud, 0.85]);
    ctx.fill();
  }

  // 王城内的九宫格（4×3 斜线连出 X 形 + 中心装饰）
  const inset = 4;
  const corners = [
    [xL + inset, yT + inset],
    [xR - inset, yT + inset],
    [xL + inset, yB - inset],
    [xR - inset, yB - inset],
  ];
  ctx.strokeStyle = rgba([...pal.borderSoft, 0.85]);
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(corners[0][0], corners[0][1]);
  ctx.lineTo(corners[3][0], corners[3][1]);
  ctx.moveTo(corners[1][0], corners[1][1]);
  ctx.lineTo(corners[2][0], corners[2][1]);
  ctx.stroke();
}

function rgba([r, g, b], a = 1) {
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

// ===== 高亮 =====

function drawHighlights(ctx, selected, legalMoves, hoverCell, lastMove) {
  // 合法着法
  if (legalMoves) {
    for (const m of legalMoves) {
      const [x, y] = cellToXY(m.col, m.row);
      if (m.capture) {
        drawCaptureRing(ctx, x, y);
      } else {
        drawMoveDot(ctx, x, y);
      }
    }
  }

  // 选中圈
  if (selected) {
    const [x, y] = cellToXY(selected.col, selected.row);
    ctx.beginPath();
    ctx.arc(x, y, SELECT_RING_R, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(255, 220, 100, 0.95)";
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  // 悬停提示
  if (hoverCell && (!selected || (hoverCell.col !== selected.col || hoverCell.row !== selected.row))) {
    const [x, y] = cellToXY(hoverCell.col, hoverCell.row);
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255, 255, 255, 0.4)";
    ctx.fill();
  }

  // 上一手标记
  if (lastMove) {
    const [x, y] = cellToXY(lastMove.to_col, lastMove.to_row);
    ctx.strokeStyle = "rgba(255, 80, 60, 0.7)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(x, y, STONE_R_BIG + 2, 0, Math.PI * 2);
    ctx.stroke();
  }
}

function drawMoveDot(ctx, x, y) {
  ctx.beginPath();
  ctx.arc(x, y, 5, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(255, 220, 100, 0.85)";
  ctx.fill();
}

function drawCaptureRing(ctx, x, y) {
  ctx.beginPath();
  ctx.arc(x, y, STONE_R_BIG + CAPTURE_RING_GAP, 0, Math.PI * 2);
  ctx.strokeStyle = "rgba(255, 80, 60, 0.95)";
  ctx.lineWidth = CAPTURE_RING_W;
  ctx.stroke();
}

// ===== 棋子 =====

function drawPieces(ctx, state, hoverCell) {
  // 按 type 分层：king/clone 在底层，soldier 在上层
  const sorted = state.pieces
    .filter(p => !p.dead)
    .sort((a, b) => {
      const order = (t) => t === "king" ? 0 : (t === "clone" ? 1 : 2);
      return order(a.type) - order(b.type);
    });

  for (const p of sorted) {
    const isHover = hoverCell && hoverCell.col === p.col && hoverCell.row === p.row;
    drawStone(ctx, p, isHover);
  }
}

function drawStone(ctx, p, isHover) {
  const [x, y] = cellToXY(p.col, p.row);
  const isBig = p.type === "king" || p.type === "clone";
  const baseR = isBig ? STONE_R_BIG : STONE_R_SMALL;
  const r = isHover ? baseR * (1 + HOVER_GROW) : baseR;

  const pal = p.side === "white" ? PAL_WHITE : PAL_BLACK;

  // 阴影
  ctx.beginPath();
  ctx.arc(x + 1, y + 2, r + 1, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0, 0, 0, 0.4)";
  ctx.fill();

  // 主体：球形渐变
  const grad = ctx.createRadialGradient(x - r * 0.35, y - r * 0.35, r * 0.1, x, y, r);
  if (p.state === "berserk") {
    grad.addColorStop(0, "#ffea80");
    grad.addColorStop(0.5, "#ff7a4a");
    grad.addColorStop(1, "#a82020");
  } else {
    grad.addColorStop(0, rgba([...pal.g0], 1));
    grad.addColorStop(0.6, rgba([...pal.g1], 1));
    grad.addColorStop(1, rgba([...pal.g2], 1));
  }
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = grad;
  ctx.fill();

  // 边框
  ctx.strokeStyle = rgba([...pal.border], 0.9);
  ctx.lineWidth = 0.8;
  ctx.stroke();

  // 高光
  ctx.beginPath();
  ctx.arc(x - r * 0.35, y - r * 0.35, r * 0.25, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(255, 255, 255, 0.6)";
  ctx.fill();

  // 中文标识
  if (p.type === "king") {
    drawCharacter(ctx, x, y, "王", "#fff", "#000");
  } else if (p.type === "clone") {
    drawCharacter(ctx, x, y, "分", rgba([...pal.emFill]), "#000");
  } else {
    drawCharacter(ctx, x, y, p.side === "white" ? "周" : "商", "#fff", "#000");
  }
}

function drawCharacter(ctx, x, y, ch, fillColor, strokeColor) {
  ctx.font = "bold 13px 'Microsoft YaHei', sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.lineWidth = 2.5;
  ctx.strokeStyle = strokeColor;
  ctx.strokeText(ch, x, y);
  ctx.fillStyle = fillColor;
  ctx.fillText(ch, x, y);
}

// ===== 工具：取得点击的格子 =====

export function canvasToCell(canvas, e) {
  const rect = canvas.getBoundingClientRect();
  const x = (e.clientX - rect.left) * (LOGICAL_PX / rect.width);
  const y = (e.clientY - rect.top) * (LOGICAL_PX / rect.height);
  return xyToCell(x, y);
}
