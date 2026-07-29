# 《商周大战》v2 应用程序 · 技术架构设计文档

> 本文档指导 **v2（Python 版）** 的实现。规则权威来源为 `D:\Codes\Projects\商周大战\docs\《商周大战》棋类游戏规则说明书.txt`；v1 设计文档参考 `D:\Codes\Projects\商周大战\docs\设计文档.md` 与 `D:\Codes\Projects\商周大战\docs\AI对战设计文档.md`；游戏机制在 v1 已稳定，v2 不引入新玩法。

## 〇、目录布局（v1 与 v2 并存）

v1（仅 HTML/JS 单文件版）与 v2（Python 版）**作为两个独立项目目录并存**，互不依赖：

| 角色 | 路径 | 内容 |
|---|---|---|
| **v1 源码**（只读，不修改） | `D:\Codes\Projects\商周大战\` | `index.html` / `codes/商周大战.html` / `docs/` / `.claude/` / `sync-index.bat` |
| **v2 当前项目目录**（本设计文档落点） | `D:\Codes\Projects\商周大战Python版\` | `docs/`（含本设计文档）/ 待建的 `pyengine/` / `tests/` / `tools/` / `web/` |

- v1 是**只读参考**：v2 实现对照 v1 行为，但**不修改 v1 文件**。
- v2 在 `商周大战Python版\` 下建子目录：`pyengine/` / `tests/` / `tools/` / `web/` / `docs/`（已含本设计文档）。
- v1 棋谱 / 规则书 / 截图 **跨目录引用**：v2 的 `tests/fixtures/` 会从 v1 的 `docs/` 拷入棋谱示例。

---

## 一、背景与目标

### 1.1 v1 现状（位于 `D:\Codes\Projects\商周大战\`）

- 代码：`codes/商周大战.html`（单文件 3019 行），部署副本 `index.html`（`sync-index.bat` 同步）。
- 技术栈：纯 HTML + CSS + 原生 JS，零依赖、双击即玩。
- 桌面浏览器运行良好；移动端靠 CSS 媒体查询 + Canvas `touch-action` 简单适配。
- AI 引擎已包含完整博弈搜索：Negamax + α-β + Zobrist 哈希 + 置换表（`1<<18`）+ 迭代加深 + 时间预算，三档（rookie/advanced/master）。
- 已有 5 个 Node.js 脚本（`.claude/ai-*.js`）做 AI 冒烟 / 性能 / 棋力诊断。

### 1.2 v2 目标

- **Python 实现核心引擎**：游戏规则 + AI 算法 + 棋谱格式权威化，用 Python 写一次。
- **桌面 + 手机都能玩**：保留 v1 的 Canvas 渲染思路，前端现代化。
- **可分享给朋友**：把链接发出去，对方打开浏览器即可玩。
- **不引入新玩法**：玩法范围与 v1 完全一致。

### 1.3 非目标

- 不做微信小程序 / 原生 App（用户明确"主要为分享"）。
- 不做联机对战 / 账号系统 / 云存档。
- 不做 PWA 安装提示（v3 再考虑）。
- 不重写 v1 → v2 的迁移工具（提供棋谱 JSON 兼容即可）。

---

## 二、技术栈与交付物

| 层 | 选型 | 理由 |
|---|---|---|
| 核心引擎 | **Python 3.11+**（无第三方依赖） | 用户要求；规则 / AI 用 dataclass + 纯函数实现 |
| 测试 | pytest | Python 标准 |
| 前端 | HTML + CSS + 原生 JS（ES2020+） | 复用 v1 Canvas 思路；不引入框架 |
| 构建 | 无（可选 Vite + TypeScript） | 静态部署最简；未来模块收益大于复杂度时再升级 |
| 部署 | GitHub Pages / Vercel / Cloudflare Pages | 静态站点，发链接即可 |
| 棋谱格式 | JSON（兼容 v1 导出格式） | 双向兼容，迁移零成本 |

**选型理由**：用户的主要诉求是"分享"。Pyodide（Python in WASM）虽然能单代码库，但 6+ MB 下载 + 移动端慢启动不友好；Python 后端需要服务器，违反"发链接即玩"。**双写（Python 引擎 + JS 镜像前端）+ Parity 测试** 是最务实的折中。

---

## 三、整体架构

> 以下目录树全部位于 **v2 项目根目录**：`D:\Codes\Projects\商周大战Python版\`

```
D:\Codes\Projects\商周大战Python版\   ← v2 项目根
├── pyengine/                  ← Python 核心引擎（事实来源）
│   ├── __init__.py
│   ├── board.py               数据层：Board / Piece / State / Position
│   ├── rules.py               规则层：move / capture / king state / clone / berserk / win-loss
│   ├── ai.py                  AI 引擎：Negamax + α-β + Zobrist + 置换表 + 迭代加深
│   ├── presets.py             3 档开局（14/22/34 子）
│   └── replay.py              棋谱 record + JSON 序列化
├── tests/                     ← pytest
│   ├── fixtures/              ← v1 棋谱样本（从 v1 项目复制）
│   ├── test_rules.py          规则层各分支
│   ├── test_ai.py             AI 三档合法着法 + 自对弈
│   ├── test_replay.py         v1 棋谱回放回归
│   └── test_parity.py         Py ↔ JS 引擎一致性
├── tools/                     ← 命令行工具
│   ├── replay_check.py        校验棋谱 JSON
│   └── ai_bench.py            AI 性能基准
├── web/                       ← 前端（部署目录）
│   ├── index.html
│   ├── src/
│   │   ├── engine.js          ← Py 同构镜像（命名 / 入参 / 返回值一致）
│   │   ├── render.js          Canvas 渲染（参考 v1 drawBoard 等）
│   │   ├── ui.js              交互层（鼠标 / 触摸 / 按钮）
│   │   └── style.css
│   └── assets/
└── docs/
    ├── v2-architecture.md     ← 本文档（已落位）
    └── v2-parity.md           Python ↔ JS 一致性测试指南
```

### 3.1 数据流

```
        ┌────────────────────────────────────────────────────┐
        │                  pyengine/  (Python)               │
        │  board.py ─→ rules.py ─→ ai.py ─→ replay.py        │
        │      ↑                                       ↓      │
        │      └──── JSON 棋谱 (兼容 v1) ──────────────┘      │
        └────────────────────────────────────────────────────┘
                          │                ▲
        ┌─────────────────┘                │
        │ Parity 测试 (Node + Py)         │
        │ 同一棋谱两端逐手执行 hash 比对   │
        ▼                                 │
        ┌────────────────────────────────────────────────────┐
        │                  web/src/  (JS)                    │
        │  engine.js ─→ render.js ─→ ui.js                   │
        │      ↑              ↓                              │
        │      └─ localStorage (皮肤 / 自定义阵容) ──┘       │
        └────────────────────────────────────────────────────┘
                          │
                          ▼
                  浏览器（桌面 / 手机）
```

**两条平行链**：
- **Python 链**：编排规则 + AI 搜索 + 棋谱分析；产出 pytest 覆盖、CLI 工具、Parity 测试数据。
- **JS 链**：浏览器运行时；通过 Parity 测试与 Python 镜像保证行为一致。

### 3.2 与 v1 架构的对应

| v1（HTML 单文件） | v2（Python + JS） |
|---|---|
| `<style>` 标签 | `web/src/style.css` |
| `<body>` 布局 | `web/index.html` |
| `<script>` 游戏逻辑 | `pyengine/`（Py）+ `web/src/engine.js`（JS 镜像） |
| `initZobrist / simHash` | `pyengine/ai.py` |
| `aiChooseMove` | `pyengine/ai.py` |
| `drawBoard / drawPieces` | `web/src/render.js` |
| 鼠标 / 触摸事件 | `web/src/ui.js` |
| `localStorage` 皮肤 | `web/src/engine.js`（保留） |
| `exportRecord / importRecord` | `pyengine/replay.py`（Py）+ `web/src/engine.js`（JS） |
| `.claude/ai-*.js` | `v2/tests/` + `v2/tools/` |

**关键变化**：
- 数据层从全局变量 → Python dataclass + JS 普通对象。
- 规则层从非纯函数 → 纯函数（输入 State，输出新 State，不改原对象）。
- AI 引擎从 `sim*` + `Int16Array` → Python `dict` / `list`（性能不是瓶颈，py 透明度更高）。
- 棋谱从全局 `moveLog` → `replay.Record` 对象。

---

## 四、核心模块设计

### 4.1 数据层（`pyengine/board.py`）

```python
from dataclasses import dataclass, field
from enum import Enum

# 棋盘常量
SIZE = 19
COLS = "ABCDEFGHJKLMNOPQRST"  # 跳过 I，行 1..19
WHITE_PALACE = (7, 11, 0, 3)   # H-M / 1-4
BLACK_PALACE = (7, 11, 15, 18) # H-M / 16-19

class Side(str, Enum):
    WHITE = "white"
    BLACK = "black"

class PieceType(str, Enum):
    KING = "king"
    SOLDIER = "soldier"
    CLONE = "clone"

class KingState(str, Enum):
    IMPRISONED_INVINCIBLE = "imprisoned_invincible"
    FREE = "free"
    BERSERK = "berserk"

@dataclass
class Piece:
    id: int
    side: Side
    type: PieceType
    col: int          # 0..18
    row: int          # 0..18
    state: KingState = KingState.FREE
    is_clone: bool = False
    has_moved: bool = False
    actively_unlocked: bool = False
    dead: bool = False

@dataclass
class State:
    pieces: list[Piece] = field(default_factory=list)
    turn: Side = Side.WHITE
    side_lost_clone: dict[Side, bool] = field(default_factory=lambda: {Side.WHITE: False, Side.BLACK: False})
    side_clone_unlocked: dict[Side, bool] = field(default_factory=lambda: {Side.WHITE: False, Side.BLACK: False})
    step_count: int = 0
    game_over: dict | None = None  # {"winner": "white"|"black"|"draw"} 或 None

    @classmethod
    def from_preset(cls, name: str) -> "State": ...
    @classmethod
    def from_dict(cls, d: dict) -> "State": ...
    def to_dict(self) -> dict: ...
    def clone(self) -> "State":
        # 浅拷贝 pieces + 字典 + 数字字段；pointers 不共享
        ...
```

**JS 镜像**（`web/src/engine.js`）：用普通对象 + `JSON.parse(JSON.stringify(...))` 深拷贝；保留 v1 的 `pieces`/`turn`/`selected`/`legalMap` 字段名便于移植。

### 4.2 规则层（`pyengine/rules.py`）

**核心理念**：所有函数**纯函数化**。v1 规则层直接读写全局 `pieces`/`turn` 的非纯风格，v2 改为：

```python
def legal_moves(state: State, piece_id: int) -> list[Move]:
    """返回 piece_id 的所有合法着法；不改原 state"""
    ...

def apply_move(state: State, move: Move, clone_decision: bool | None = None) -> State:
    """返回执行 move 后的新 state；不改原 state
    
    clone_decision: None=分身由 apply_move 自动判断（提供弹窗给前端）；True/False=手动指定
    """
    new_state = state.clone()
    _apply_move_inplace(new_state, move, clone_decision)
    return new_state

def check_win_loss(state: State) -> dict | None:
    """返回 None 或 {"winner": ..., "reason": ...}"""
    ...

def position_hash(state: State) -> str:
    """Zobrist 哈希字符串；用于循环局面检测 + Parity 测试"""
    ...
```

**关键函数清单**（与 v1 L910–1448 对应）：

| 函数 | v1 行号 | v2 形态 |
|---|---|---|
| `piece_at(state, col, row)` | 904 | `state.pieces` 线性查找（py 性能足够） |
| `reachable_cells(state, piece)` | 933 | 纯函数 |
| `legal_moves(state, piece)` | 956 | 纯函数 |
| `theoretical_range(king)` | 965 | 纯函数 |
| `is_imprisoned(state, king)` | 979 | 纯函数 |
| `king_of(state, side)` | 992 | 改写为 `state.pieces` 遍历 |
| `recompute_king_states(state)` | 997 | 返回新 state 或 new_state 内部更新（apply_move 内部调用） |
| `check_win_loss(state)` | 1086 | 纯函数 |
| `has_any_move(state, side)` | 1097 | 纯函数 |
| `position_hash(state)` | 1105 | 纯函数（Zobrist 哈希字符串） |

### 4.3 AI 引擎（`pyengine/ai.py`）

**算法**：v1 L1449–2060 同算法 Python 移植。
- Zobrist 哈希（mulberry32 固定种子，确定性强）
- 置换表（`dict` 而非 `Int32Array`；Python 字典 O(1) 且更易调试）
- Negamax + α-β 剪枝
- 迭代加深 + 时间预算（`deadline = now + timeLimitMs`）
- 评估函数（`simEval`）：王价值 + 机动 + 围王 + 解锁梯度 + 灭子判负风险

**关键 API**：

```python
@dataclass
class AILevel:
    depth: int
    time_limit_ms: int | None = None  # None 表示无时间限制
    top_n: int | None = None          # rookie 模式：topN 内随机
    label: str = ""

AI_LEVELS = {
    "rookie":   AILevel(depth=1, top_n=4, label="rookie"),
    "advanced": AILevel(depth=4, time_limit_ms=2500, label="advanced"),
    "master":   AILevel(depth=5, time_limit_ms=4500, label="master"),
}

def ai_choose(state: State, side: Side, level: AILevel) -> Move | None:
    """返回 root 选着；超时时保留上一层完整结果（v1 同语义）"""
    ...

def evaluate(state: State, side: Side) -> int:
    """评估函数；返回 side 视角分值（更大=对我方越有利）"""
    ...
```

**性能预期**：
- v1 master 档单步 2.5–4.5s（JS 实现）
- v2 master 档单步 ≤ 5s（Py 实现，可接受）
- 如果性能不够，预留 NumPy 加速 sim 的扩展点（v3 再优化）

### 4.4 棋谱（`pyengine/replay.py`）

**棋谱 JSON 格式**（兼容 v1 导出）：

```json
{
  "preset": "battle",
  "label": "测试对局",
  "moves": [
    {"from": "H1", "to": "H3", "capture": false, "clone": false},
    {"from": "H19", "to": "H17", "capture": false, "clone": false},
    ...
  ]
}
```

**Record 类**：

```python
@dataclass
class Record:
    preset: str
    label: str = ""
    moves: list[Move] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Record": ...
    def to_dict(self) -> dict: ...
    def replay_index(self, n: int) -> State:
        """重放到第 n 步；返回对应的 State"""
        ...
    def validate(self) -> list[str]:
        """返回所有错误信息；空列表 = 合法"""
        ...
```

### 4.5 前端（`web/`）

`web/src/engine.js` 是 Python 引擎的同构镜像：
- 同名函数（`legal_moves` / `apply_move` / `evaluate` / `ai_choose` 等）
- 同输入输出（`State` 对象结构对齐）
- 同算法（Negamax + α-β + Zobrist）

**复用 v1 渲染/交互**：
- `render.js` 参考 v1 `drawBoard / drawPieces / drawPalaceDecor / drawHighlights`（L2062–2518）
- `ui.js` 参考 v1 鼠标 / 触摸事件 + 按钮（`newGame / undo / redo / preset / opponent / level / ...`）
- 保留 v1 皮肤系统（4 套：warm / qinglv / shanshui / neon）
- 保留 v1 摆子 / 复盘 / 棋谱导入导出

**新前端 ≠ 推倒重来**：v1 的渲染层 800 行（drawBoard + drawPieces + skin）值得保留；v2 的前端是 v1 的"现代化 + 引擎替换"。

### 4.6 启动流程

**Python 引擎**（CLI 工具示例）：
```python
# tools/ai_bench.py
from pyengine.board import State
from pyengine.ai import ai_choose, AI_LEVELS

state = State.from_preset("battle")
move = ai_choose(state, Side.WHITE, AI_LEVELS["master"])
print(f"AI 选择: {move}")
```

**前端**：
```
浏览器加载 web/index.html
  └─ 加载 web/src/engine.js / render.js / ui.js
       ├─ engine.js 暴露：State / legal_moves / apply_move / ai_choose / ...
       ├─ render.js：fitCanvas / drawBoard / drawPieces / renderScoresheet
       └─ ui.js：注册点击 / 拖拽 / 按钮事件
  └─ 启动序列：
       initPieces → buildSkinRow → loadSkin → fitCanvas → applySkin → renderScoresheet
```

---

## 五、关键设计原则

1. **Python 引擎无 IO 副作用**：所有函数纯函数化（v1 设计文档 §三的"数据层只存状态，不碰 DOM"理念延伸到 Python）。
2. **棋谱是唯一序列化载体**：JSON 双向兼容 v1，便于迁移与回归。
3. **AI 自对弈 = 黄金测试**：Python 跑两 AI 互弈当回归测试，跑通即认为引擎管线 OK。
4. **同名同步**：Python 函数与 JS 函数命名一致（snake_case ↔ camelCase 转换由镜像层处理），便于人脑对照。
5. **风险范围控制**：v2 范围 = v1 范围 + Python 化 + 现代前端，**不引入新玩法**。

---

## 六、迁移路径（v1 → v2）

> v1 源码在 `D:\Codes\Projects\商周大战\`，v2 项目根在 `D:\Codes\Projects\商周大战Python版\`。所有 v2 命令在 v2 项目根下执行。

按依赖顺序推进：

| 阶段 | 内容 | 验证 |
|---|---|---|
| 1 | 数据层：`pyengine/board.py`（`State` / `Piece` / 常量 / presets） | `python -c "from pyengine.board import State; print(State.from_preset('battle'))"` 摆子正确 |
| 2 | 规则层：`pyengine/rules.py`（`legal_moves` / `apply_move` / `check_win_loss` / `position_hash`） | `pytest tests/test_rules.py` 100% pass |
| 3 | AI 引擎：`pyengine/ai.py`（`evaluate` / `negamax` / `ai_choose`） | `pytest tests/test_ai.py` 三档都能产合法着法 |
| 4 | 棋谱：`pyengine/replay.py`（`Record` / JSON 序列化） | `pytest tests/test_replay.py` v1 棋谱可回放 |
| 5 | 前端镜像：`web/src/engine.js`（Py 同构） | `pytest tests/test_parity.py` 一致 |
| 6 | 前端 UI：`web/src/render.js` / `ui.js` / `index.html` / `style.css` | 浏览器手工验证 |
| 7 | 部署：GitHub Pages / Vercel 自动部署 | 链接分享给朋友 |

**硬约束**：
- 任何阶段发现 v1 规则 bug，必须先修复 v1 HTML（`D:\Codes\Projects\商周大战\codes\商周大战.html`），再移植到 v2（防止 v2 与 v1 行为分叉）。
- v1 仅作参考，**在 v2 实现过程中不修改 v1 文件**。

---

## 七、验证（如何判断 v2 跑通）

> 所有命令均在 **v2 项目根** 执行：`D:\Codes\Projects\商周大战Python版\`

### 7.1 单元测试
```bash
cd D:\Codes\Projects\商周大战Python版
pytest -v
```
通过条件：
- `test_rules.py` 100% pass（覆盖禁锢 / 分身 / 暴走 / 胜负 / 循环 5 大分支）
- `test_ai.py` 三个档位都能产合法着法；自对弈 200 步内必终局
- `test_replay.py` v1 导出棋谱可被 Python 完整回放

### 7.2 AI 性能基准
```bash
cd D:\Codes\Projects\商周大战Python版
python tools/ai_bench.py --level master --moves 100
```
对照指标：单步 ≤ 5s（v1 同档 2.5–4.5s）。

### 7.3 棋谱回归
从 v1 项目复制 3–5 份实际游玩导出的棋谱到 v2 的 `tests/fixtures/`：
```bash
# 一次性复制（按需调整源文件名）
cp D:\Codes\Projects\商周大战\docs\*.json D:\Codes\Projects\商周大战Python版\tests\fixtures\
# 跑测试
pytest tests/test_replay.py -v
```

### 7.4 Python ↔ JS Parity
```bash
cd D:\Codes\Projects\商周大战Python版
# JS 引擎导出到 Node
node web/src/engine.js  # 暴露 engine 对象
# Python 桥接比对
pytest tests/test_parity.py -v
```
通过条件：相同棋谱逐手执行，Python 与 JS 的 `positionHash` 字符串完全一致。

### 7.5 前端跑通
```bash
cd D:\Codes\Projects\商周大战Python版\web
python -m http.server 8080
# 浏览器打开 http://localhost:8080
```
手工验证清单：
- [ ] 三档开局摆子正确（14 / 22 / 34 子）
- [ ] 移动 / 吃子 / 禁锢 / 分身 / 暴走 / 胜负 全部正常
- [ ] 三档 AI 都能用（rookie / advanced / master）
- [ ] 棋谱导入导出往返一致
- [ ] 移动端浏览器（DevTools 切移动）布局正常
- [ ] 皮肤切换正常（4 套）

### 7.6 部署验证
```bash
cd D:\Codes\Projects\商周大战Python版
git push origin main  # 触发 GitHub Pages 自动部署
# 分享 URL 给朋友，朋友打开浏览器即可玩
```

---

## 八、风险与缓解

| 风险 | 缓解 |
|---|---|
| Python ↔ JS parity drift | Parity 单元测试 + 同一棋谱两端逐手执行 hash 比对；每次 Py 修改必跑 Parity |
| AI 性能不达（Py 比 JS 慢） | 复用 v1 深度 / 时间预算；若不够再考虑 NumPy 加速 sim |
| 移动端性能差（JS 引擎可接受） | 沿用 v1 离屏缓存 + hover RAF + 增量更新 |
| 用户希望在 v2 加新玩法 | **明确不做**（参见 非目标 1.3）；新功能单独立文档讨论 |
| v1 规则 bug 被无意"修复" | 硬约束：v2 行为必须与 v1 严格一致；任何偏差视为 v2 bug，需先回到 v1 修复 |

---

## 九、关键文件清单

> **v2 项目根**：`D:\Codes\Projects\商周大战Python版\`
> **v1 源码根**：`D:\Codes\Projects\商周大战\`（仅参考，不修改）

### v2 新建文件（全部位于 v2 项目根）

- `pyengine/__init__.py`
- `pyengine/board.py` / `rules.py` / `ai.py` / `presets.py` / `replay.py`
- `tests/fixtures/`（从 v1 复制棋谱样本）
- `tests/test_rules.py` / `test_ai.py` / `test_replay.py` / `test_parity.py`
- `tools/replay_check.py` / `ai_bench.py`
- `web/index.html`
- `web/src/engine.js` / `render.js` / `ui.js` / `style.css`
- `web/assets/`
- `docs/v2-architecture.md`（**本文档**，已落位）
- `docs/v2-parity.md`
- `README.md`

### v1 复用文件（只读，**绝对路径**）

- `D:\Codes\Projects\商周大战\index.html`（v1 入口）
- `D:\Codes\Projects\商周大战\codes\商周大战.html`（v1 源码权威）
- `D:\Codes\Projects\商周大战\docs\《商周大战》棋类游戏规则说明书.txt`（规则权威）
- `D:\Codes\Projects\商周大战\docs\设计文档.md`（v1 架构文档）
- `D:\Codes\Projects\商周大战\docs\AI对战设计文档.md`（v1 AI 引擎文档）
- `D:\Codes\Projects\商周大战\docs\14子 小局.png` / `22子 大战.png` / `34子 决战.png`（开局截图）

### 跨目录引用约定

- v2 代码中如需引用 v1 规则书 / 棋谱示例，**用绝对路径**或**复制到 v2 的 `tests/fixtures/`**（避免运行时依赖 v1 位置）。
- 推荐做法：v1 棋谱一旦有更新，**手动复制**到 v2 的 `tests/fixtures/`（不引入文件同步工具，简单优先）。

---

## 十、对比 v1 的关键变化

| 维度 | v1 | v2 |
|---|---|---|
| 核心语言 | JavaScript | Python（核心） + JavaScript（前端镜像） |
| 代码结构 | 单文件 3019 行 | 5 个 Python 模块 + 4 个 JS 模块 |
| 规则层 | 非纯函数（直接读写全局） | 纯函数（输入 State → 输出 State） |
| 数据层 | 全局变量 | dataclass + 字典 |
| 测试 | 5 个 Node 脚本（`.claude/ai-*.js`） | pytest 全套（单元 + 集成 + Parity） |
| 部署 | 单 HTML 文件双击 | 静态站点发链接 |
| 前端框架 | 无（原生 JS） | 无（保留原生 JS） |
| 移动端 | 简单媒体查询 | 同 v1（已够用） |
| AI 引擎 | 同算法 JS 实现 | 同算法 Python 实现 |
| 棋谱 | JSON 兼容 | JSON 兼容（**双向兼容**） |

**核心收益**：
- Python 拿到"游戏引擎 + AI 引擎 + 工具链"完整资产（规则文档化、pytest 覆盖、棋谱离线分析、AI 调权重）。
- 朋友通过链接直接玩（GitHub Pages / Vercel 静态部署）。
- v1 的 HTML/JS 经验完全复用（前端是 v1 的现代化版本）。

---

> 本文档与 v1 文档配套使用：v1 文档讲"是什么"，本文档讲"v2 怎么变成 Python"。
> 实现过程中如有结构性偏差（如发现 v1 规则 bug），先回到 v1 修复，再回到 v2 同步。
