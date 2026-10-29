#!/usr/bin/env bash
# 给 Claude Code 装"用代码做视频"的三件套（Remotion / HyperFrames / OpenMontage）。
# 云端会话的容器会被回收，新会话里跑一次这个脚本就能恢复。
#
#   ./scripts/install-video-stack.sh                 全装，OpenMontage 放到 ~/OpenMontage
#   ./scripts/install-video-stack.sh /path/to/dir    OpenMontage 放到指定目录
#
# 需要：node >= 18、python3、ffmpeg、git、make
set -euo pipefail

OM_DIR="${1:-$HOME/OpenMontage}"

echo "==> Remotion agent skills -> ~/.claude/skills"
npx -y skills@latest add remotion-dev/skills -g -a claude-code -y

echo "==> HyperFrames core skills -> ~/.claude/skills"
npx -y hyperframes@latest skills update

echo "==> HyperFrames 渲染用的 headless Chrome"
npx -y hyperframes@latest browser ensure

echo "==> OpenMontage -> $OM_DIR"
if [ ! -d "$OM_DIR/.git" ]; then
  git clone --depth 1 https://github.com/calesthio/OpenMontage.git "$OM_DIR"
fi
make -C "$OM_DIR" setup

# Remotion 默认从 remotion.media 下 Chrome。Node 的下载不走代理，
# 有的网络策略也会拦这个域名，所以改从 Google 官方的 Chrome for Testing 下同一版本。
echo "==> Remotion 渲染用的 headless Chrome"
RC="$OM_DIR/remotion-composer"
ver="$(node -p "require('$RC/node_modules/@remotion/renderer/dist/browser/get-chrome-download-url.js').TESTED_VERSION")"
dest="$RC/node_modules/.remotion/chrome-headless-shell"
if [ "$(cat "$dest/VERSION" 2>/dev/null)" != "$ver" ]; then
  mkdir -p "$dest"
  tmp="$(mktemp -d)"
  curl -sSfL -o "$tmp/chs.zip" \
    "https://storage.googleapis.com/chrome-for-testing-public/$ver/linux64/chrome-headless-shell-linux64.zip"
  rm -rf "$dest/linux64"
  unzip -q "$tmp/chs.zip" -d "$dest/linux64"
  rm -rf "$tmp"
  printf '%s' "$ver" > "$dest/VERSION"
fi
(cd "$RC" && npx remotion browser ensure)

echo ""
echo "完成。新开一个 Claude Code 会话后，这些 skill 才会出现在列表里："
echo "  /remotion-best-practices  /remotion-create  /hyperframes  /hyperframes-cli ..."
echo "OpenMontage 是一个工程，不是 skill：在 $OM_DIR 里打开 Claude Code 再提需求。"
