# 🌾 华农热点 TOP5 · 微信定时推送

每天自动抓取**华南农业大学官网**的资讯，评选出热点 TOP5，推送到你的**微信**。

**资讯来源**（官网公开发布）：

| 栏目 | 说明 |
|------|------|
| 学校要闻 | 官方头条新闻 |
| 科研进展 | 重大科研成果（Nature Communications 等期刊论文动态） |
| 综合新闻 | 校园动态 |
| 媒体聚焦 | 人民日报、广州日报、中国青年报等媒体报道华农 |

**热点算法**：按发布日期降序 + 栏目权重排序；每个栏目最多入选 2 条；同一事件的多篇相似报道只保留 1 条，保证 TOP5 的信息多样性。

---

## 一、获取微信推送 Key（1 分钟，免费）

1. 打开 [https://sct.ftqq.com](https://sct.ftqq.com)
2. 用**微信扫码**登录
3. 复制页面上的 **SendKey**（形如 `SCT123456xxxxxxxx`）

> 微信推送通过「Server酱」服务号实现，免费额度每天 5 条，每日推送 1 次完全够用。

## 二、运行方式（二选一）

### 方式 A：GitHub Actions 免服务器定时推送（推荐）

**优点**：完全免费、零服务器，每天 8:00（北京时间）自动推送。

#### 步骤 1 · 上传代码到 GitHub

下载本项目的 `scau-news.zip`（或整个 `scau-news/` 目录），然后二选一：

**(a) 用脚本一键推送（推荐）**

```bash
# 1. 安装 GitHub CLI（如未装）：https://cli.github.com/
# 2. 生成 Personal Access Token: https://github.com/settings/tokens
#    勾选 Contents: Read and write
# 3. 在解压目录下运行：
export GH_TOKEN=ghp_xxxxxxxxxxxx
bash init_repo.sh
```

**(b) 手动推送**

```bash
cd scau-news
git init
git add .
git commit -m "feat: 华农热点TOP5微信推送 bot"
# 在 GitHub 创建空仓库 scau-news-bot（不要勾选 README/.gitignore）
gh repo create scau-news-bot --public --source=. --remote=origin --push
# 或：
git remote add origin https://github.com/你的用户名/scau-news-bot.git
git branch -M main
git push -u origin main
```

#### 步骤 2 · 添加 Secret

打开仓库 `Settings → Secrets and variables → Actions → New repository secret`：

| 项 | 值 |
|----|-----|
| Name | `SERVERCHAN_SENDKEY` |
| Secret | 你的 SendKey（形如 `SCT4110...100vQs`）|

点 **Add secret** 保存。

#### 步骤 3 · 测试一次手动推送

打开仓库 **Actions** 标签 → 左侧选「华农热点推送」→ 右侧 **Run workflow** → 选 main 分支 → 点击绿色按钮。

等待约 30 秒，步骤会变成 ✅；同时打开微信「**Server酱**」服务号，会收到 `🌾华农热点TOP5` 消息。

#### 步骤 4 · 启用定时

定时已经写在 `.github/workflows/push.yml` 里（每天 UTC 2:00 = 北京时间早 10:00）。**首次运行后 GitHub 会自动按 cron 调度**，无需额外操作。

> ⚠️ GitHub Actions 定时可能因平台负载有 10–60 分钟漂移，对"每日资讯"足够精准。

#### 想要换推送时间

编辑 `.github/workflows/push.yml` 中的 cron 表达式（UTC 时间）：

| 北京时间 | cron |
|---------|------|
| 早 7:00 | `'0 23 * * *'` |
| 早 8:00 | `'0 0 * * *'` |
| 早 10:00 | `'0 2 * * *'`（当前）|
| 中午 12:00 | `'0 4 * * *'` |
| 晚 20:00 | `'0 12 * * *'` |

每天推两次：把 `- cron: '0 12 * * *'` 这行取消注释即可。

### 方式 B：本地/自己的服务器定时运行

```bash
# 安装依赖
pip3 install requests beautifulsoup4 markdown

# 立即推送一次
python3 scau_news.py --key SCTxxxxxxxx

# 或用环境变量
export SERVERCHAN_SENDKEY=SCTxxxxxxxx
python3 scau_news.py

# 自定义条数（如 TOP8）
python3 scau_news.py --top 8

# 只看效果不推送（生成 preview.html 用浏览器打开）
python3 scau_news.py --dry-run
```

配合 crontab 每天早 8 点推送：

```bash
crontab -e
# 添加一行（注意替换成你的真实路径和 SendKey）：
0 8 * * * cd /path/to/scau-news && /usr/bin/python3 scau_news.py --key SCTxxxxxxxx >> run.log 2>&1
```

## 三、推送到微信后长什么样

微信「Server酱」服务号会收到一条消息卡片，标题如：

> 🌾华农热点TOP5｜09月03日

正文为 Markdown 排版的 5 条资讯，每条含**栏目标签、标题、日期、摘要、阅读原文链接**。

执行 `python3 scau_news.py --dry-run` 会生成 `preview.html`，是推送内容的手机样式预览，可用浏览器直接打开查看效果。

## 四、常见问题

| 问题 | 说明 |
|------|------|
| 推送失败 `40001 错误的Key` | SendKey 复制不完整或已重置，到 [sct.ftqq.com](https://sct.ftqq.com) 重新复制 |
| GitHub Actions 没跑 | 检查 Actions 标签页是否被禁用，公开仓库每月 2000 分钟额度足够每天跑 1 次 |
| Secret 改完没生效 | Actions 页面重新 Run workflow 一次即可，cron 下次调度也会用新值 |
| 免费额度限制 | Server酱免费版每天 5 条、每日推 1 次无压力；超量可换 [PushPlus](https://www.pushplus.plus)（改一下 `push_serverchan` 函数的 API 即可） |
| 想换其他大学 | 修改 `scau_news.py` 顶部的 `BASE`、`COLUMN_MAP`、`SOURCES` 为目标高校官网对应栏目列表页即可 |
| 官网改版 | 爬虫基于列表页 `news_list` 结构解析，若失效需调整 `parse_news_page` 中的选择器 |