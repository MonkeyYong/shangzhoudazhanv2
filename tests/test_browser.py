"""Playwright 自测：本地启动页面，验证棋盘正常渲染。

用途：
- 调试 GitHub Pages 棋盘空白 bug
- 验证 fitCanvas + render 流程
- 输出 canvas 尺寸 + console 日志 + 截图

依赖：
- Playwright Python（pip install playwright）
- Chromium 浏览器（python -m playwright install chromium）

运行：
    python tests/test_browser.py
"""

from __future__ import annotations

import http.server
import mimetypes
import os
import socket
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright


REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
SCREENSHOT_DIR = REPO_ROOT / "tests" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# 关键：Python 默认 mimetypes 不一定知道 .js → application/javascript
# 浏览器对 ES Module 强制 MIME 类型检查，否则拒绝加载
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/json", ".json")


def find_free_port() -> int:
    """找一个空闲端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int) -> socketserver.TCPServer:
    """启动静态文件服务器（serve web/）。"""
    os.chdir(str(WEB_DIR))

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    httpd = socketserver.TCPServer(("127.0.0.1", port), QuietHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def run_test():
    port = find_free_port()
    httpd = start_server(port)
    url = f"http://127.0.0.1:{port}/index.html"
    print(f"[server] 启动 {url}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1024, "height": 800})
            page = context.new_page()

            # 收集 console 消息
            console_logs = []
            def on_console(msg):
                console_logs.append(f"[{msg.type}] {msg.text}")
            page.on("console", on_console)

            # 收集 page error
            page_errors = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))

            # 收集失败的请求
            failed_requests = []
            page.on("requestfailed", lambda r: failed_requests.append(f"{r.url} - {r.failure}"))

            print(f"[browser] 打开 {url}")
            response = page.goto(url, wait_until="networkidle", timeout=20000)
            print(f"[browser] 状态码: {response.status}")

            # 等待 canvas + 渲染
            print("[browser] 等待 2 秒让 render 完成...")
            page.wait_for_timeout(2000)

            # 检查 canvas 尺寸
            canvas_info = page.evaluate("""() => {
              const canvas = document.getElementById('board');
              if (!canvas) return { error: 'canvas not found' };
              const rect = canvas.getBoundingClientRect();
              const ctx = canvas.getContext('2d');
              return {
                canvasWidth: canvas.width,
                canvasHeight: canvas.height,
                clientWidth: canvas.clientWidth,
                clientHeight: canvas.clientHeight,
                rectWidth: rect.width,
                rectHeight: rect.height,
                hasGetContext: !!ctx,
                parentBg: getComputedStyle(canvas.parentElement).background.slice(0, 80),
              };
            }""")
            print(f"[canvas] {canvas_info}")

            # 检查 window.game
            game_info = page.evaluate("""() => {
              const g = window.game;
              if (!g) return { error: 'window.game not found' };
              return {
                hasState: !!g.state,
                pieceCount: g.state ? g.state.pieces.length : 0,
                turn: g.state ? g.state.turn : null,
                opponent: g.opponent,
                lastMove: g.lastMove,
              };
            }""")
            print(f"[game] {game_info}")

            # 检查 canvas 实际像素内容（采样中央）
            pixel_check = page.evaluate("""() => {
              const canvas = document.getElementById('board');
              const ctx = canvas.getContext('2d');
              // 采样 9 个点
              const samples = [];
              for (let i = 0; i < 9; i++) {
                const x = (i % 3 + 1) * 100;
                const y = (Math.floor(i / 3) + 1) * 100;
                const p = ctx.getImageData(x, y, 1, 1).data;
                samples.push({ x, y, rgba: [p[0], p[1], p[2], p[3]] });
              }
              return samples;
            }""")
            print(f"[pixel] 9 点采样：")
            for p in pixel_check:
                r, g, b, a = p["rgba"]
                print(f"   ({p['x']},{p['y']}): rgb({r},{g},{b}) a={a}")

            # 截图
            screenshot_path = SCREENSHOT_DIR / "github_pages_test.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"[screenshot] {screenshot_path}")

            # ===== 交互测试：点击 H1 → H3 落子 =====
            print("\n[interact] 模拟点击 H1 → H3 落子")
            # H1 = col 7, row 0；H3 = col 7, row 2
            # 棋盘由 32px margin + 32px cell，CSS 640×640
            # canvas 的 x = 32 + col*32, y = 32 + (18-row)*32
            # H1: x=32+7*32=256, y=32+18*32=608
            # H3: x=32+7*32=256, y=32+16*32=544
            canvas_box = page.locator("#board").bounding_box()
            scale = canvas_box["width"] / 640
            h1_x = canvas_box["x"] + (32 + 7 * 32) * scale
            h1_y = canvas_box["y"] + (32 + 18 * 32) * scale
            h3_x = canvas_box["x"] + (32 + 7 * 32) * scale
            h3_y = canvas_box["y"] + (32 + 16 * 32) * scale

            page.mouse.click(h1_x, h1_y)
            page.wait_for_timeout(100)
            page.mouse.click(h3_x, h3_y)
            page.wait_for_timeout(200)

            # 验证状态更新
            after_move = page.evaluate("""() => {
              const g = window.game;
              const sheet = document.querySelector('#scoresheet').innerHTML;
              return {
                pieceCount: g.state.pieces.length,
                turn: g.state.turn,
                moveCount: g.record.moves.length,
                lastMove: g.lastMove,
                pieceAtH1: g.state.pieces.find(p => p.col === 7 && p.row === 0),
                pieceAtH3: g.state.pieces.find(p => p.col === 7 && p.row === 2),
                scoresheet: sheet,
              };
            }""")
            print(f"[after move] {after_move}")

            after_screenshot = SCREENSHOT_DIR / "after_first_move.png"
            page.screenshot(path=str(after_screenshot), full_page=True)
            print(f"[screenshot] {after_screenshot}")

            # 断言
            assert after_move["turn"] == "black", f"轮到黑方，实际 {after_move['turn']}"
            assert after_move["moveCount"] == 1, f"应有 1 步，实际 {after_move['moveCount']}"
            assert after_move["pieceAtH1"] is None, "H1 应空"
            assert after_move["pieceAtH3"] is not None, "H3 应该有子"
            assert after_move["scoresheet"].count("H1→H3") == 1, "棋谱应显示 H1→H3"

            print("[OK] 交互测试通过：点击 H1 → H3 落子成功")

            # 报告
            print("\n========== 报告 ==========")
            print("\n========== 报告 ==========")
            print(f"console 日志（{len(console_logs)} 条）：")
            for log in console_logs:
                print(f"  {log}")
            if page_errors:
                print(f"\npage errors（{len(page_errors)} 条）：")
                for err in page_errors:
                    print(f"  {err}")
            if failed_requests:
                print(f"\n失败请求（{len(failed_requests)} 条）：")
                for r in failed_requests:
                    print(f"  {r}")

            # 断言
            assert canvas_info.get("canvasWidth", 0) > 0, "canvas 宽度为 0"
            assert canvas_info.get("canvasHeight", 0) > 0, "canvas 高度为 0"
            assert game_info.get("pieceCount", 0) == 22, f"应有 22 子，实际 {game_info.get('pieceCount')}"
            assert not page_errors, f"页面错误: {page_errors}"

            # 检查像素：中央格子应该是浅木色（gradient #e8c674 系列）
            center = pixel_check[4]  # (200, 200)
            r, g, b, _ = center["rgba"]
            if (220 <= r <= 245) and (180 <= g <= 220) and (90 <= b <= 150):
                print(f"\n[OK] canvas 中央像素 rgb({r},{g},{b}) 是预期的木色 gradient")
            else:
                print(f"\n[WARN] canvas 中央像素 rgb({r},{g},{b}) 不是预期木色")
                print(f"       预期范围：r=220~245, g=180~220, b=90~150")

            browser.close()
            print("\n[SUCCESS] 全部检查通过！")
            return 0
    finally:
        httpd.shutdown()
        httpd.server_close()


if __name__ == "__main__":
    sys.exit(run_test())
