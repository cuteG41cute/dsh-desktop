#!/usr/bin/env bash
# ============================================================================
# DeepSeek Harness 桌面版 —— Linux 便携安装器
# ----------------------------------------------------------------------------
# 设计原则（与用户要求一致）：
#   · **不往系统里装任何东西**：Node 用官方 tarball 解进安装目录（便携），
#     dsh 与 pnpm 用这个便携 npm 装进安装目录下的 app/，DSH_HOME 也默认放安装目录下。
#   · 安装位置由用户指定（--prefix），卸载 = 删掉那一个目录。
#   · 不碰 /usr、不碰系统 npm 全局、不需要 root。
#
# 用法：
#   ./install.sh                                  # 装到 ~/.local/opt/deepseek-harness
#   ./install.sh --prefix /opt/dsh                # 指定安装位置
#   ./install.sh --node-tarball ./node.tar.xz     # 离线：用本地 Node 包
#   ./install.sh --dsh-tarball ./dsh.tgz          # 离线：用本地 dsh 包
#   ./install.sh --warmup                         # 装完先跑一次服务，把 profile 依赖装好
#   ./install.sh --uninstall                      # 删除安装目录（二次确认）
#
# 系统依赖（无法便携化，脚本会检查并给命令）：
#   python3 python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1
# ============================================================================
set -euo pipefail

PREFIX="${DSH_PREFIX:-$HOME/.local/opt/deepseek-harness}"
NODE_VERSION="${DSH_NODE_VERSION:-24.19.0}"
DSH_VERSION="${DSH_VERSION:-0.1.5-rc.1}"
NODE_TARBALL="${DSH_NODE_TARBALL:-}"
DSH_TARBALL="${DSH_DSH_TARBALL:-}"
DSH_HOME_DIR=""
WITH_DESKTOP_ENTRY=1
WARMUP=0
UNINSTALL=0
ASSUME_YES=0

say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s ==\n' "$*"; }
warn() { printf '[警告] %s\n' "$*"; }
die()  { printf '[错误] %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix)        PREFIX="$2"; shift 2 ;;
    --node-version)  NODE_VERSION="$2"; shift 2 ;;
    --dsh-version)   DSH_VERSION="$2"; shift 2 ;;
    --node-tarball)  NODE_TARBALL="$2"; shift 2 ;;
    --dsh-tarball)   DSH_TARBALL="$2"; shift 2 ;;
    --dsh-home)      DSH_HOME_DIR="$2"; shift 2 ;;
    --no-desktop-entry) WITH_DESKTOP_ENTRY=0; shift ;;
    --warmup)        WARMUP=1; shift ;;
    --uninstall)     UNINSTALL=1; shift ;;
    --yes|-y)        ASSUME_YES=1; shift ;;
    -h|--help)       sed -n '2,26p' "$0"; exit 0 ;;
    *) die "不认识的参数：$1（--help 看用法）" ;;
  esac
done

PREFIX="${PREFIX/#\~/$HOME}"
APP="$PREFIX/app"
NODE_DIR="$PREFIX/node"
BIN="$PREFIX/bin"
SHARE="$PREFIX/share"
LOGS="$PREFIX/logs"
DSH_HOME="${DSH_HOME_DIR:-$PREFIX/dsh-home}"
NODE="$NODE_DIR/bin/node"
NPM="$NODE_DIR/bin/npm"
ENTRY="$APP/node_modules/@deepseek-ai/dsh/lib/bin.js"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DESKTOP="$(cd "$SRC_DIR/.." && pwd)"
DESKTOP_FILE="$HOME/.local/share/applications/deepseek-harness.desktop"

# ---------------------------------------------------------------- 卸载
if [ "$UNINSTALL" = 1 ]; then
  step "卸载"
  [ -d "$PREFIX" ] || die "目录不存在：$PREFIX"
  say "将删除：$PREFIX（含 node / dsh / 数据目录 dsh-home）"
  if [ "$ASSUME_YES" != 1 ]; then
    printf '确认删除？输入 yes 继续：'
    read -r ans
    [ "$ans" = "yes" ] || { say "已取消"; exit 1; }
  fi
  rm -rf "$PREFIX"
  rm -f "$DESKTOP_FILE"
  say "✓ 已删除；系统里没有留下别的东西（我们没有全局安装任何包）。"
  exit 0
fi

# ---------------------------------------------------------------- 环境检查
step "环境检查"
[ "$(uname -s)" = "Linux" ] || die "这个脚本只用于 Linux"
case "$(uname -m)" in
  x86_64|amd64) ARCH=linux-x64 ;;
  aarch64|arm64) ARCH=linux-arm64 ;;
  *) die "不支持的架构：$(uname -m)" ;;
esac
command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 || die "需要 curl 或 wget 下载 Node"
say "✓ 架构 $ARCH，安装位置 $PREFIX"

gui_missing=0
if ! command -v python3 >/dev/null 2>&1; then
  gui_missing=1
elif ! python3 -c "import gi" 2>/dev/null; then
  gui_missing=1
else
  python3 - <<'PY' >/dev/null 2>&1 || gui_missing=1
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk  # noqa
try:
    gi.require_version('WebKit2', '4.1')
except ValueError:
    gi.require_version('WebKit2', '4.0')
from gi.repository import WebKit2  # noqa
PY
fi
if [ "$gui_missing" = 1 ]; then
  warn "缺图形界面依赖（Node/dsh 照样能装，只是窗口打不开）"
  say "  Debian/Ubuntu/Deepin: sudo apt install -y python3 python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1"
  say "  装完再跑一次本脚本即可。"
else
  say "✓ python3 + GTK3 + WebKitGTK 就绪"
fi

# ---------------------------------------------------------------- 目录
step "创建安装目录"
mkdir -p "$BIN" "$SHARE" "$LOGS" "$APP" "$NODE_DIR" "$DSH_HOME"
say "✓ $PREFIX/{bin,share,logs,app,node,dsh-home}"

# ---------------------------------------------------------------- 便携 Node
step "便携 Node（$NODE_DIR，不碰系统）"
if [ -x "$NODE" ]; then
  say "✓ 已有：$("$NODE" --version)"
else
  tgz="$NODE_TARBALL"
  if [ -n "$tgz" ]; then
    [ -f "$tgz" ] || die "找不到本地 Node 包：$tgz"
  else
    tgz="/tmp/node-v$NODE_VERSION-$ARCH.tar.xz"
    if [ ! -f "$tgz" ]; then
      url="https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-$ARCH.tar.xz"
      say "· 下载 $url"
      if command -v curl >/dev/null 2>&1; then
        curl -fsSL --retry 3 -o "$tgz" "$url" || die "下载失败（可用 --node-tarball 指定离线包）"
      else
        wget -q -O "$tgz" "$url" || die "下载失败（可用 --node-tarball 指定离线包）"
      fi
    fi
  fi
  tar -xJf "$tgz" -C "$NODE_DIR" --strip-components=1
  say "✓ 便携 Node 就绪：$("$NODE" --version)"
fi
export PATH="$NODE_DIR/bin:$PATH"      # npm 的 shebang 需要 PATH 里有 node

# ---------------------------------------------------------------- dsh
step "安装 @deepseek-ai/dsh@$DSH_VERSION + pnpm（进 $APP，不碰全局）"
# 用 package.json 声明依赖再 `npm install`：
#  · 踩过的坑①：先装 dsh 再 `npm install --no-save pnpm` 会把 dsh 当 extraneous **删掉**；
#  · 踩过的坑②：package.json 里的值要写**版本号**，写成 "@scope/name@ver" 会解析失败。
if [ -n "$DSH_TARBALL" ]; then
  [ -f "$DSH_TARBALL" ] || die "找不到本地 dsh 包：$DSH_TARBALL"
  DSH_DEP="file:$DSH_TARBALL"
else
  DSH_DEP="$DSH_VERSION"
fi
cat > "$APP/package.json" <<EOF
{
  "name": "deepseek-harness-portable",
  "private": true,
  "description": "Portable install root for the DeepSeek Harness desktop app",
  "dependencies": {
    "@deepseek-ai/dsh": "$DSH_DEP"
  }
}
EOF

have_ver=""
if [ -f "$ENTRY" ]; then
  have_ver="$("$NODE" -e "try{process.stdout.write(require('$APP/node_modules/@deepseek-ai/dsh/package.json').version)}catch(e){}" 2>/dev/null || true)"
fi
if [ "$have_ver" = "$DSH_VERSION" ]; then
  say "✓ 已安装同一版本（dsh $have_ver）"
else
  ( cd "$APP" && "$NPM" install --no-audit --no-fund ) || die "安装失败（离线请用 --dsh-tarball）"
  say "✓ 已安装"
fi
[ -f "$ENTRY" ] || die "dsh 入口不存在：$ENTRY"

# dsh 的 plugin 子命令会把参数转给 pnpm —— 单独装到 $PREFIX/tools，避免和应用目录互相 prune
if [ ! -x "$PREFIX/tools/node_modules/.bin/pnpm" ]; then
  say "· 把 pnpm 装到 $PREFIX/tools（只有 dsh plugin 会用到）"
  mkdir -p "$PREFIX/tools"
  cat > "$PREFIX/tools/package.json" <<'EOF'
{ "name": "dsh-portable-tools", "private": true, "dependencies": { "pnpm": "9.15.0" } }
EOF
  ( cd "$PREFIX/tools" && "$NPM" install --no-audit --no-fund ) || warn "pnpm 安装失败（只影响 dsh plugin 子命令）"
fi

# ---------------------------------------------------------------- 窗口文件
step "安装桌面窗口"
install -m 0755 "$SRC_DIR/dsh-desktop.py" "$SHARE/dsh-desktop.py"
install -m 0755 "$SRC_DIR/dsh-desktop"    "$SHARE/dsh-desktop"
for icon in "$SRC_DIR/dsh-desktop.png" "$REPO_DESKTOP/dsh-desktop.png"; do
  [ -f "$icon" ] && { install -m 0644 "$icon" "$SHARE/dsh-desktop.png"; break; }
done
PREVIEW_SRC="$REPO_DESKTOP/tools/preview-probe/preview-tools.js"
[ -f "$PREVIEW_SRC" ] || PREVIEW_SRC="$SRC_DIR/preview-tools.js"
if [ -f "$PREVIEW_SRC" ]; then
  install -m 0644 "$PREVIEW_SRC" "$SHARE/preview-tools.js"
  say "✓ 预览增强脚本：$(wc -c < "$SHARE/preview-tools.js") 字节（缩放 / 右键保存 / 拖拽）"
else
  warn "没找到 preview-tools.js —— 窗口能用，但没有预览增强"
fi

# ---------------------------------------------------------------- 启动器
step "写启动器"
cat > "$BIN/dsh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export PATH="$NODE_DIR/bin:$APP/node_modules/.bin:$PREFIX/tools/node_modules/.bin:\$PATH"
export DSH_HOME="\${DSH_HOME:-$DSH_HOME}"
exec "$NODE" "$ENTRY" "\$@"
EOF
cat > "$BIN/dsh-desktop" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export PATH="$NODE_DIR/bin:$APP/node_modules/.bin:$PREFIX/tools/node_modules/.bin:\$PATH"
export DSH_HOME="\${DSH_HOME:-$DSH_HOME}"
export DSH_PREFIX="$PREFIX"
export DSH_SHARE="$SHARE"
export DSH_BIN="$ENTRY"
export DSH_WEB_URL="\${DSH_WEB_URL:-http://127.0.0.1:3080}"
exec "$SHARE/dsh-desktop" "\$@"
EOF
chmod +x "$BIN/dsh" "$BIN/dsh-desktop"
say "✓ $BIN/dsh（命令行）  $BIN/dsh-desktop（窗口）"

if [ "$WITH_DESKTOP_ENTRY" = 1 ]; then
  mkdir -p "$(dirname "$DESKTOP_FILE")"
  cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=DeepSeek Harness
Comment=DeepSeek Harness 桌面窗口（便携安装）
Exec=$BIN/dsh-desktop
Icon=$SHARE/dsh-desktop.png
Terminal=false
Categories=Development;
EOF
  chmod +x "$DESKTOP_FILE"
  say "✓ 应用菜单项：$DESKTOP_FILE"
fi

cat > "$PREFIX/install.json" <<EOF
{
  "prefix": "$PREFIX",
  "node": "$NODE_VERSION",
  "dsh": "$DSH_VERSION",
  "dshHome": "$DSH_HOME",
  "installedAt": "$(date -Iseconds)"
}
EOF

# ---------------------------------------------------------------- 预热
if [ "$WARMUP" = 1 ]; then
  step "预热（首次跑一次服务，把 profile 依赖装好）"
  log="$LOGS/web.log"; : > "$log"
  port=3080
  say "· 启动 dsh web（首次可能要几分钟装 profile 依赖）"
  "$NODE" "$ENTRY" web --no-open --port "$port" >> "$log" 2>&1 &
  pid=$!
  ok=0
  for i in $(seq 1 100); do
    kill -0 "$pid" 2>/dev/null || break
    code=$(curl -s -o /dev/null -w '%{http_code}' -m 2 "http://127.0.0.1:$port/" 2>/dev/null || echo 000)
    [ "$code" != "000" ] && { ok=1; say "· 第 $((i*3)) 秒探测到 HTTP $code"; break; }
    sleep 3
  done
  kill "$pid" 2>/dev/null || true
  if [ "$ok" = 1 ]; then say "✓ 服务可用"; else warn "服务没在 5 分钟内就绪，日志尾部如下（把最后几行发我）："; tail -20 "$log" || true; fi
fi

# ---------------------------------------------------------------- 自检
step "自检"
if command -v python3 >/dev/null 2>&1; then
  DSH_PREFIX="$PREFIX" DSH_SHARE="$SHARE" DSH_HOME="$DSH_HOME" \
    python3 "$SHARE/dsh-desktop.py" --selftest || warn "自检有项目未通过（见上；缺 GTK 的话装完依赖再来）"
else
  warn "没有 python3，跳过自检"
fi

step "完成"
say "安装位置：$PREFIX"
say "  启动窗口：$BIN/dsh-desktop        （或应用菜单里的「DeepSeek Harness」）"
say "  命令行：  $BIN/dsh web"
say "  数据目录：$DSH_HOME（不动 ~/.dsh）"
say "  卸载：    bash $SRC_DIR/install.sh --prefix '$PREFIX' --uninstall"
