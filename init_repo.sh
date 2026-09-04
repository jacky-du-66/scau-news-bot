#!/usr/bin/env bash
# 一键部署华农热点到 GitHub 仓库
# 用法：
#   1. 到 https://github.com/settings/tokens 生成一个 Fine-grained token，
#      勾选 Contents: Read and write
#   2. export GH_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
#   3. bash init_repo.sh
#
# 也可以手动执行下面命令而不跑脚本（详见 README.md）

set -e

REPO_NAME="${REPO_NAME:-scau-news-bot}"
DESC="${REPO_DESC:-华南农业大学热点TOP5 · 微信定时推送}"

if [ -z "$GH_TOKEN" ]; then
  echo "❌ 请先设置环境变量 GH_TOKEN（GitHub Personal Access Token）"
  echo "   生成地址: https://github.com/settings/tokens"
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "❌ 需要安装 GitHub CLI: https://cli.github.com/"
  echo "   或参考 README 手动 git push"
  exit 1
fi

cd "$(dirname "$0")"

echo "📦 创建仓库 $REPO_NAME ..."
gh repo create "$REPO_NAME" --public --description "$DESC" --source=. --remote=origin --push 2>&1 || {
  # 如果仓库已存在（重试场景），改用 git push
  echo "⚠️ 仓库可能已存在，尝试用 git 推送..."
  git init -q 2>/dev/null || true
  git remote remove origin 2>/dev/null || true
  git remote add origin "https://x-access-token:${GH_TOKEN}@github.com/$(gh api user -q .login)/$REPO_NAME.git"
  git add .
  git commit -q -m "feat: 华农热点TOP5微信推送 bot" || true
  git push -u origin main --force
}

echo ""
echo "✅ 代码已推送！接下来："
echo "   1. 打开 https://github.com/$(gh api user -q .login)/$REPO_NAME/settings/secrets/actions/new"
echo "   2. Name:  SERVERCHAN_SENDKEY"
echo "   3. Value: 你的 Server酱 SendKey"
echo "   4. 提交后，到 Actions 页面手动 Run workflow 试一次"