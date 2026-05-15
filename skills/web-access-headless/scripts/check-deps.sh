#!/usr/bin/env bash
# 环境检查 + 确保 CDP Proxy 就绪

# Node.js
if command -v node &>/dev/null; then
  NODE_VER=$(node --version 2>/dev/null)
  NODE_MAJOR=$(echo "$NODE_VER" | sed 's/v//' | cut -d. -f1)
  if [ "$NODE_MAJOR" -ge 22 ] 2>/dev/null; then
    echo "node: ok ($NODE_VER)"
  else
    echo "node: warn ($NODE_VER, 建议升级到 22+)"
  fi
else
  echo "node: missing — 请安装 Node.js 22+"
  exit 1
fi

# Chrome 调试端口探测函数（可多次调用）
# SAFETY: 只接受 HeadlessChrome 实例，绝不复用用户主 Chrome（即便它恰好开着调试端口）
find_chrome_port() {
  node -e "
const fs = require('fs');
const path = require('path');
const os = require('os');
const net = require('net');
const http = require('http');

function checkPort(port) {
  return new Promise((resolve) => {
    const socket = net.createConnection(port, '127.0.0.1');
    const timer = setTimeout(() => { socket.destroy(); resolve(false); }, 2000);
    socket.once('connect', () => { clearTimeout(timer); socket.destroy(); resolve(true); });
    socket.once('error', () => { clearTimeout(timer); resolve(false); });
  });
}

function isHeadlessChrome(port) {
  return new Promise((resolve) => {
    const req = http.get({ host: '127.0.0.1', port, path: '/json/version', timeout: 2000 }, (res) => {
      let body = '';
      res.on('data', (c) => body += c);
      res.on('end', () => {
        try {
          const v = JSON.parse(body);
          // Chrome --headless=new reports Browser='Chrome/...' but
          // User-Agent contains 'HeadlessChrome/...'. Check both.
          const browser = typeof v.Browser === 'string' ? v.Browser : '';
          const ua = typeof v['User-Agent'] === 'string' ? v['User-Agent'] : '';
          resolve(/HeadlessChrome/i.test(browser) || /HeadlessChrome/i.test(ua));
        } catch { resolve(false); }
      });
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => { req.destroy(); resolve(false); });
  });
}

function activePortFiles() {
  const home = os.homedir();
  const localAppData = process.env.LOCALAPPDATA || '';
  switch (process.platform) {
    case 'darwin':
      return [
        path.join(home, 'Library/Application Support/Google/Chrome/DevToolsActivePort'),
        path.join(home, 'Library/Application Support/Google/Chrome Canary/DevToolsActivePort'),
        path.join(home, 'Library/Application Support/Chromium/DevToolsActivePort'),
      ];
    case 'linux':
      return [
        path.join(home, '.config/google-chrome/DevToolsActivePort'),
        path.join(home, '.config/chromium/DevToolsActivePort'),
      ];
    case 'win32':
      return [
        path.join(localAppData, 'Google/Chrome/User Data/DevToolsActivePort'),
        path.join(localAppData, 'Chromium/User Data/DevToolsActivePort'),
      ];
    default:
      return [];
  }
}

(async () => {
  for (const filePath of activePortFiles()) {
    try {
      const lines = fs.readFileSync(filePath, 'utf8').trim().split(/\r?\n/).filter(Boolean);
      const port = parseInt(lines[0], 10);
      if (port > 0 && port < 65536 && await checkPort(port) && await isHeadlessChrome(port)) {
        console.log(port);
        process.exit(0);
      }
    } catch (_) {}
  }

  // SAFETY: only probe 9333 (our dedicated headless port). Never 9222 — that's
  // typically the user's main Chrome and would attach silently.
  for (const port of [9333]) {
    if (await checkPort(port) && await isHeadlessChrome(port)) {
      console.log(port);
      process.exit(0);
    }
  }

  process.exit(1);
})();
" 2>/dev/null
}

# Chrome 调试端口 — 用独立 CDP-only 实例，绑定专用端口 9333（避开常用 9222）
#
# SAFETY: 9333 是为本 skill 保留的专用端口。9222 通常是用户主 Chrome；如果
#   不小心复用了主 Chrome，CDP 的 /new、/close 等会作用在用户真实窗口上。
#   选 9333 是为了从根本上消除端口冲突。
#
# 设计：用独立 user-data-dir (~/.cache/chrome-cdp-profile) 启动专属后台 Chrome。
#   - 不会触碰用户正在使用的主 Chrome 窗口/标签/会话
#   - 没有 osascript quit，没有"控制其他应用"权限请求
#   - headless 模式 → 不抢焦点、不出现在 Dock
#   - 实例可常驻，下次直接复用同一端口（DevToolsActivePort 文件检测）
#   - profile 放在 ~/.cache 而非 /tmp：cookie/登录态可跨重启保留
CDP_PROFILE="$HOME/.cache/chrome-cdp-profile"
CDP_PORT="9333"
CDP_PORT_FILE="$CDP_PROFILE/DevToolsActivePort"
CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# 探测专属 CDP 实例端口
#   优先级 1: 直接探测固定端口 9333 是否有 HeadlessChrome 在响应
#   优先级 2: 读 user-data-dir 下的 DevToolsActivePort
find_cdp_instance_port() {
  # 直接探测 9333
  local ver
  ver=$(curl -s --connect-timeout 2 --max-time 3 "http://127.0.0.1:$CDP_PORT/json/version" 2>/dev/null)
  # SAFETY: --headless=new 在 Browser 字段写 "Chrome/..."（无 Headless 前缀），
  #   但 User-Agent 里有 "HeadlessChrome/..."。两个字段任一匹配即算 headless。
  if echo "$ver" | grep -q '"Browser"'; then
    if echo "$ver" | grep -q -i 'HeadlessChrome'; then
      echo "$CDP_PORT"
      return 0
    fi
  fi
  # 兜底：读 active port 文件
  if [ -f "$CDP_PORT_FILE" ]; then
    local p
    p=$(head -1 "$CDP_PORT_FILE" 2>/dev/null)
    # SAFETY: 即便文件读到端口，也要验证是 HeadlessChrome 才能用
    if [ -n "$p" ]; then
      local v
      v=$(curl -s --connect-timeout 2 --max-time 3 "http://127.0.0.1:$p/json/version" 2>/dev/null)
      if echo "$v" | grep -q -i 'HeadlessChrome'; then
        echo "$p"
        return 0
      fi
    fi
  fi
  return 1
}

if CHROME_PORT=$(find_cdp_instance_port); then
  : # 已有独立 CDP 实例在跑，直接复用
elif CHROME_PORT=$(find_chrome_port); then
  : # 通过 active port 文件 + HeadlessChrome 验证发现的实例（罕见但合法）
else
  # 启动一个完全独立的 CDP-only Chrome：
  #   --remote-debugging-port=9333  专用端口，绝不与用户主 Chrome (9222) 冲突
  #   --user-data-dir              隔离 profile，避免与用户主 Chrome 共用单实例锁
  #   --headless=new               不弹窗、不抢焦点、不进入 Dock（截图/CDP 仍完全可用）
  #   --no-first-run / --no-default-browser-check：跳过首次启动向导
  echo "🚀 启动独立 CDP Chrome 实例 (端口 $CDP_PORT, profile: $CDP_PROFILE, headless)..."
  mkdir -p "$CDP_PROFILE"
  "$CHROME_BIN" \
    --remote-debugging-port=$CDP_PORT \
    --user-data-dir="$CDP_PROFILE" \
    --headless=new \
    --no-first-run \
    --no-default-browser-check \
    --disable-features=ChromeWhatsNewUI \
    > /tmp/chrome-cdp.log 2>&1 &
  disown 2>/dev/null || true

  for i in $(seq 1 15); do
    sleep 1
    if CHROME_PORT=$(find_cdp_instance_port); then
      break
    fi
  done

  if [ -z "$CHROME_PORT" ]; then
    echo "❌ CDP Chrome 启动失败，详见 /tmp/chrome-cdp.log"
    exit 1
  fi
  echo "✅ 独立 CDP Chrome 已就绪（端口 $CDP_PORT，不影响你的主 Chrome）"
fi
echo "chrome: ok (port $CHROME_PORT)"
# Export so cdp-proxy.mjs (started below) honors the same port pin
export CDP_CHROME_PORT="$CHROME_PORT"

# CDP Proxy — 用 /targets 统一判断：返回 JSON 数组即 ready，失败则启动并重试
TARGETS=$(curl -s --connect-timeout 3 "http://127.0.0.1:3456/targets" 2>/dev/null)
if echo "$TARGETS" | grep -q '^\['; then
  echo "proxy: ready"
else
  # /targets 失败：proxy 未运行或未连接 Chrome，尝试启动（已运行会自动跳过）
  echo "proxy: connecting..."
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
  node "$SCRIPT_DIR/cdp-proxy.mjs" > /tmp/cdp-proxy.log 2>&1 &
  sleep 2  # 等 proxy 进程就绪
  for i in $(seq 1 15); do
    # connect-timeout 5s：给 Chrome 授权弹窗留够响应时间，避免超时后重复触发连接
    curl -s --connect-timeout 5 --max-time 8 http://localhost:3456/targets 2>/dev/null | grep -q '^\[' && echo "proxy: ready" && exit 0
    [ "$i" -eq 1 ] && echo "⚠️  Chrome 可能有授权弹窗，请点击「允许」后等待连接..."
  done
  echo "❌ 连接超时，请检查 Chrome 调试设置"
  exit 1
fi
