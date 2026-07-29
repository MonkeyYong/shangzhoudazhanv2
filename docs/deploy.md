# 部署指南

支持三种部署方式：GitHub Pages（推荐）、Gitee Pages（国内）、Vercel。

## 一、GitHub Pages（推荐）

### 自动部署（已配置）

推送 `main` 分支触发 `.github/workflows/deploy.yml`：

1. 跑全部 pytest（防退化）
2. 拷贝 `web/` 内容到 `_deploy/`
3. 添加 `.nojekyll`（防止 Jekyll 干扰）
4. 部署到 GitHub Pages

### 首次启用

1. 进入 GitHub 仓库 → **Settings** → **Pages**
2. Source: **GitHub Actions**
3. 等待首次部署完成
4. 访问 URL：`https://<username>.github.io/shangzhoudazhanv2/`

### 手动触发

GitHub → Actions → "Deploy to GitHub Pages" → **Run workflow**。

## 二、Gitee Pages（国内访问快）

### 一次性配置

1. 进入 Gitee 仓库 → **服务** → **Gitee Pages**
2. 启动服务（Gitee 要求实名认证）
3. 部署分支：选 `main`
4. 部署目录：选 `web/`（或先合并到一个 `gh-pages` 子目录）
5. 访问 URL：`https://<username>.gitee.io/shangzhoudazhanv2/`

### 注意

- Gitee Pages 不支持 GitHub Actions 自动部署（免费版）
- 需要 Gitee 账号已实名认证
- 每次更新后需手动点击"更新"按钮

### 替代方案：GitHub Actions → Gitee 同步

可加 `.github/workflows/sync-gitee.yml`（需 Gitee API Token）：

```yaml
name: Sync to Gitee
on:
  push:
    branches: [main]
jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Push to Gitee
        run: |
          git remote add gitee git@gitee-personal:GoldenCudgel/shangzhoudazhanv2.git
          git push -f gitee main
        env:
          GITEE_TOKEN: ${{ secrets.GITEE_TOKEN }}
```

Gitee Pages 仍需手动触发部署。

## 三、Vercel / Netlify / Cloudflare Pages

通用步骤：

1. 导入 GitHub 仓库
2. **Build settings**：
   - Build command: `pip install pytest && pytest tests/ -v`（可选，作为部署前的健康检查）
   - Output directory: `web`
   - Root directory: 留空
3. 部署

Vercel 自动获得 `https://<project>.vercel.app` URL。

## 四、本地预览

```bash
cd web
python -m http.server 8080
# 浏览器打开 http://localhost:8080/index.html
```

或使用 Node.js：
```bash
cd web
npx http-server -p 8080
```

## 五、自定义域名

### GitHub Pages

1. 仓库根创建 `web/CNAME` 文件，写入域名（如 `game.example.com`）
2. DNS 添加 CNAME 记录指向 `<username>.github.io`
3. GitHub Settings → Pages → Custom domain 输入域名
4. 勾选 **Enforce HTTPS**

### Vercel

在项目设置 → Domains 添加并配置。

## 六、部署前检查清单

每次发布前确认：

- [ ] `pytest tests/` 全部通过（151 个用例）
- [ ] `node web/test/engine_test.js` 全部通过（25 个用例）
- [ ] `pytest tests/test_parity.py` 全部通过（6 个用例，Python ↔ JS 一致）
- [ ] 浏览器手动验证：开局 / 移动 / 吃子 / AI / 棋谱导入导出
- [ ] 移动端浏览器（DevTools 切换）布局正常

## 七、常见问题

### Q: 部署后页面空白？
A: 检查 `web/.nojekyll` 是否存在；检查 `web/index.html` 路径是否正确。

### Q: 静态资源 404？
A: 确认 `output directory` 配置为 `web/`（不是 `web/src/`）。

### Q: AI 反应慢？
A: master 档单步 2.5-4.5s 正常；CPU 较弱的设备可选 advanced / rookie。

### Q: 移动端点击不灵敏？
A: viewport meta 已设置；如有问题可调整 canvas 的 `touch-action: manipulation`。
