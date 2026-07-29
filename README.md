# 商周大战 v2 · Python + Web 版

> 一款自创棋类对战游戏 · 桌面 + 手机浏览器即玩 · 微信小程序发布前 v2 版本

**Play now**：[GitHub Pages](https://<your-username>.github.io/shangzhoudazhanv2/) ·
[Gitee Pages](https://<your-username>.gitee.io/shangzhoudazhanv2/)

## 一句话简介

19×19 围棋棋盘上的双王突围战：白方（周）救武王出黑方王城；黑方（商）阻截并杀白方武王。武王 + 士卒 + 分身 + 暴走 · 完整博弈搜索 AI。

## 玩法

- **棋盘**：19×19 标准围棋棋盘（A..T 跳 I，行 1..19）
- **棋子**：武王 ×1 + 兵 ×10 / 双方对称
- **胜利**：击杀对方所有武王（本体 + 分身）
- **核心机制**：禁锢 / 解锁 / 分身 / 暴走 / 三循环平局

完整规则见 [`docs/《商周大战》棋类游戏规则说明书.txt`](docs/《商周大战》棋类游戏规则说明书.txt)。

## 技术栈

| 层 | 选型 |
|---|---|
| **核心引擎** | Python 3.11+（无第三方依赖） |
| **AI 引擎** | Negamax + α-β + Zobrist 哈希 + 置换表 + 迭代加深 |
| **测试** | pytest（151 个用例） |
| **前端** | HTML + CSS + 原生 JS（ES Modules） |
| **构建** | 无（纯静态站点） |
| **部署** | GitHub Pages / Gitee Pages / Vercel |

完整 v2 架构：[`docs/v2-architecture.md`](docs/v2-architecture.md)

## 仓库结构

```
商周大战Python版/
├── codes/                 # Python 引擎（事实来源）
│   ├── board.py           #   数据层：State / Piece / Move
│   ├── rules.py           #   规则层：移动 / 禁锢 / 分身 / 暴走 / 胜负
│   ├── ai.py              #   AI 引擎：Negamax + α-β + Zobrist
│   ├── replay.py          #   棋谱 JSON 序列化
│   └── presets.py         #   3 档开局（14 / 22 / 34 子）
├── tests/                 # pytest 单元测试 + Parity 测试
│   ├── test_board.py      #   数据层
│   ├── test_rules.py      #   规则层
│   ├── test_ai.py         #   AI 引擎
│   ├── test_replay.py     #   棋谱
│   └── test_parity.py     #   Python ↔ JS 引擎一致性
├── tools/                 # 命令行工具
│   └── replay_check.py    #   棋谱 JSON 校验
├── web/                   # 前端（部署目录）
│   ├── index.html         #   入口
│   └── src/
│       ├── engine.js      #   JS 引擎镜像（Python 1:1 移植）
│       ├── render.js      #   Canvas 渲染
│       ├── ui.js          #   交互 + 游戏循环
│       ├── style.css      #   样式
│       └── main.js        #   入口
├── docs/                  # 设计文档
│   ├── v2-architecture.md #   v2 架构设计
│   ├── deploy.md          #   部署指南
│   ├── 设计文档.md         #   v1 架构文档（参考）
│   ├── AI对战设计文档.md    #   v1 AI 引擎文档
│   ├── 商周大战v1.md       #   v1 源码分析
│   └── 《商周大战》棋类游戏规则说明书.txt
├── .github/workflows/     # CI / CD
│   └── deploy.yml         #   GitHub Pages 自动部署
├── v1/                    # v1 源码（独立项目，参考）
└── README.md              # 本文件
```

## 快速开始

### 在线游玩

直接访问 [GitHub Pages URL] 即可。

### 本地运行

```bash
# 1. 启动 Python 静态服务器
cd web
python -m http.server 8080

# 2. 浏览器打开
# http://localhost:8080/index.html
```

### 运行 Python 测试

```bash
# 安装 pytest
pip install pytest

# 全部测试
pytest -v

# 仅 AI 引擎
pytest tests/test_ai.py -v

# 仅 Python ↔ JS 一致性
pytest tests/test_parity.py -v
```

### 运行 JS 引擎测试

```bash
cd web
node test/engine_test.js
```

### 校验棋谱文件

```bash
python tools/replay_check.py <path/to/replay.json>
```

## 部署

详见 [`docs/deploy.md`](docs/deploy.md)。

支持：
- **GitHub Pages**：自动部署（推送 main 触发 `.github/workflows/deploy.yml`）
- **Gitee Pages**：手动部署（Gitee 控制台 → 服务 → Gitee Pages → 启动）
- **Vercel / Netlify / Cloudflare Pages**：直接导入项目，root 选 `web/`

## 与 v1 的关系

| | v1 | v2 |
|---|---|---|
| 仓库 | `D:\Codes\Projects\商周大战` | `商周大战Python版/`（本仓库） |
| 技术栈 | 纯 HTML + JS 单文件 | Python 引擎 + JS 镜像前端 |
| AI | 同算法 JS | 同算法 Python |
| 棋谱 | JSON（兼容） | JSON（双向兼容） |
| 测试 | 5 个 Node 脚本 | 151 个 pytest + 25 个 Node |

v1 保留作为 v2 的"参考实现"。

## 贡献

- 算法严格对应 v1，不引入新玩法
- Python 引擎是事实来源；JS 引擎通过 Parity 测试保证一致
- 修改任何规则前，先跑 `pytest tests/` 验证

## 许可证

本项目为个人创作，源码以"原样"提供，禁止商业使用。
