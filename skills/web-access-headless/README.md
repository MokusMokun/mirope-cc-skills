# web-access-headless

> **Forked from [eze-is/web-access](https://github.com/eze-is/web-access) (MIT) at commit [`1116c08`](https://github.com/eze-is/web-access/commit/1116c082a7f13860c3befd5307a272d6a120206f).**
> Patched for **safety-first headless isolation** — does **not** reuse the user's daily Chrome.

给 Claude Code 装上完整联网能力的 skill：联网策略调度 + CDP 浏览器操作 + 站点经验积累。

---

## 与上游的核心差异

| | 上游 `eze-is/web-access` | 本 fork `web-access-headless` |
|---|---|---|
| Chrome 实例 | 复用用户日常 Chrome | **启动独立 headless Chrome** |
| 调试端口 | 默认探测 9222 / 9229 / 9333 | **只用 9333（专用）** |
| Profile | 用户日常 profile | `~/.cache/chrome-cdp-profile`（独立、跨重启持久） |
| 登录态 | 自动继承用户已登录的所有站点 | **空白 profile，需要在 headless 实例内单独登录** |
| 对用户主浏览器影响 | 共享窗口/tab（依赖"只在后台 tab 操作"自律） | **零影响**，主 Chrome 完全不感知 |
| Dock / 焦点 | Chrome 已开则无新窗口；未开会启动 GUI | 始终 headless，不进 Dock，不抢焦点 |
| 安全模型 | 信任 | **多层 SAFETY 校验**：仅接受 `User-Agent` 含 `HeadlessChrome` 的实例；提供 `CDP_ALLOW_USER_CHROME=1` 显式逃生口 |

### 选 fork 还是选上游？

- **想要"开了就能用，自动带登录态"** → 用上游
- **想要"调研 Agent 在后台跑，绝不动我正在浏览的窗口"** → 用本 fork

本 fork 的成本：需要登录的站（小红书、X、知乎、微信公众号、内部 SaaS 等），第一次访问需要在 headless 实例里单独完成登录流程；好处是登录后 cookie 写在 `~/.cache/chrome-cdp-profile` 里跨重启保留。

---

## 安装

```bash
# clone monorepo
git clone https://github.com/MokusMokun/mirope-cc-skills.git ~/code/mirope-cc-skills

# symlink 到 CC skills 目录
ln -s ~/code/mirope-cc-skills/skills/web-access-headless ~/.claude/skills/web-access-headless
```

> 不要同时安装上游 `web-access` 和本 fork——两者会争抢 Proxy 的 3456 端口，且 SKILL 描述会让模型在两者之间犹豫，工具选择质量下降。

## 前置配置

需要 Node.js 22+ 和系统装有 Google Chrome。**无需手动开启 chrome://inspect**——本 fork 会自己拉一个独立 headless 实例。

环境检查（首次运行会自动启动 headless Chrome）：

```bash
bash ~/.claude/skills/web-access-headless/scripts/check-deps.sh
```

## CDP Proxy API

Proxy 通过 WebSocket 直连独立 headless Chrome 实例，提供 HTTP API：

```bash
# 启动（check-deps.sh 通过后会自动拉起）
node ~/.claude/skills/web-access-headless/scripts/cdp-proxy.mjs &

# 页面操作（与上游一致）
curl -s "http://localhost:3456/new?url=https://example.com"
curl -s -X POST "http://localhost:3456/eval?target=ID" -d 'document.title'
curl -s -X POST "http://localhost:3456/click?target=ID" -d 'button.submit'
curl -s "http://localhost:3456/screenshot?target=ID&file=/tmp/shot.png"
curl -s "http://localhost:3456/scroll?target=ID&direction=bottom"
curl -s "http://localhost:3456/close?target=ID"
```

完整 API 见 [`references/cdp-api.md`](./references/cdp-api.md)。

## 环境变量（fork 新增）

| 变量 | 作用 |
|---|---|
| `CDP_CHROME_PORT` | 由 `check-deps.sh` 自动 export，把端口钉给 `cdp-proxy.mjs`，避免误探测到主 Chrome |
| `CDP_ALLOW_USER_CHROME=1` | **显式 opt-in 复用用户主 Chrome**——禁用 HeadlessChrome 校验。仅在你确实需要继承日常登录态时设置 |

## License

MIT。上游 © [一泽 Eze](https://github.com/eze-is)；本 fork 改动 © yuhao。

## 与上游同步策略

本 fork 与上游设计哲学冲突，**上游不会 merge 本改动**。计划：
- 不主动追上游 commit
- 上游有重要 bugfix（CDP 协议变更、Proxy 稳定性）时手动 cherry-pick
- 不引入上游新功能（如 `find-url.mjs`）除非确认与 headless 隔离兼容
