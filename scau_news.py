#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
华南农业大学热点资讯 TOP5 → 微信推送（Server酱）

用法：
  1. 测试运行（不推送，生成 HTML 预览）:
     python3 scau_news.py --dry-run
  2. 正式推送（需要 Server酱 SendKey，https://sct.ftqq.com 微信扫码免费获取）:
     python3 scau_news.py --key SCTxxxxxxxx
     或: export SERVERCHAN_SENDKEY=SCTxxxxxxx && python3 scau_news.py
  3. 自定义条数:
     python3 scau_news.py --top 8 --key SCTxxxxxxxx
"""

import argparse
import datetime
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup

BASE = "https://www.scau.edu.cn"
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}

# 栏目编号 → 名称（URL 中 c17646a442957 的 17646 即栏目号）
COLUMN_MAP = {
    "17646": "学校要闻",
    "17648": "科研进展",
    "17649": "学术活动",
    "17861": "综合新闻",
    "1390": "通知公告",
    "17832": "通知",
    "17647": "媒体聚焦",
}

# 同日排序权重：越小越靠前
WEIGHT = {
    "学校要闻": 0,
    "科研进展": 1,
    "媒体聚焦": 2,
    "综合新闻": 3,
    "学术活动": 4,
    "通知公告": 5,
    "通知": 6,
}

# 抓取源：聚合页含"学校要闻/科研进展/学术活动"多个区块
SOURCES = [
    ("news", f"{BASE}/17646/list.htm"),   # 新闻中心聚合页
    ("news", f"{BASE}/zhxw/list.htm"),    # 综合新闻
    ("media", f"{BASE}/17647/list.htm"),  # 媒体聚焦（外部报道）
]


def date_from_url(href: str):
    """从 URL /2026/0903/c17648a443005/ 中提取发布日期"""
    m = re.search(r"/(\d{4})/(\d{2})(\d{2})/c\d+a\d+/", href)
    if m:
        y, mth, d = m.groups()
        return f"{y}-{mth}-{d}"
    return None


def date_from_text(li):
    """从列表项文本中提取日期（2026-09-03 / 2026.09.03 等）"""
    for s in li.stripped_strings:
        m = re.search(r"(\d{4})[-./年](\d{1,2})[-./月](\d{1,2})", s)
        if m:
            y, mth, d = m.groups()
            return f"{y}-{int(mth):02d}-{int(d):02d}"
    return None


def parse_news_page(html: str):
    """解析校内新闻列表页（学校要闻/科研进展/综合新闻等）"""
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for li in soup.find_all("li"):
        # 标题链接优先取 news_title 容器内的，其次取带 title 属性的文章链接
        a = None
        box = li.find("div", class_="news_title")
        if box:
            a = box.find("a", href=re.compile(r"c\d+a\d+/page\.htm"))
        if a is None:
            a = li.find("a", href=re.compile(r"c\d+a\d+/page\.htm"), title=True)
        if a is None:
            continue
        href = a["href"]
        if href.startswith("/"):
            href = BASE + href
        if href in seen:
            continue
        title = (a.get("title") or a.get_text(strip=True)).strip()
        if not title:
            continue
        # 优先取页面显示日期（发布日期），URL 日期是创建日期，可能偏早
        date = date_from_text(li) or date_from_url(href)
        col_m = re.search(r"c(\d+)a\d+/page\.htm", href)
        column = COLUMN_MAP.get(col_m.group(1), "校内资讯") if col_m else "校内资讯"
        # 摘要（若有）
        text_box = li.find("div", class_="news_text")
        summary = text_box.get_text(strip=True)[:80] if text_box else ""
        seen.add(href)
        items.append(
            {"title": title, "url": href, "date": date or "0000-00-00",
             "column": column, "summary": summary}
        )
    return items


def parse_media_page(html: str):
    """解析媒体聚焦页：外部媒体报道链接"""
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for li in soup.find_all("li"):
        a = li.find("a", href=re.compile(r"^https?://"))
        if not a or "scau.edu.cn" in a["href"]:
            continue
        title = (a.get("title") or a.get_text(strip=True)).strip()
        if not title or len(title) < 8:  # 过滤导航类短链接
            continue
        date = date_from_text(li) or date_from_url(li.get_text() or "")
        if date is None:  # 媒体聚焦列表文本里有日期
            m = re.search(r"(\d{4}-\d{2}-\d{2})", li.get_text())
            date = m.group(1) if m else None
        href = a["href"]
        if href in seen:
            continue
        seen.add(href)
        items.append(
            {"title": title, "url": href, "date": date or "0000-00-00",
             "column": "媒体聚焦", "summary": ""}
        )
    return items


def fetch_article_summary(url: str, max_len: int = 90) -> str:
    """抓取华农官网文章详情页正文首段作为摘要
    适用校内栏目：学校要闻 / 科研进展 / 综合新闻（部分列表页无 news_text 摘要）"""
    try:
        r = requests.get(url, headers=UA, timeout=12)
        r.encoding = "utf-8"
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # 博达 CMS 正文容器：优先 .wp_articlecontent（科研进展）→ .article（学校要闻）→ .v_news_content
        for sel in [".wp_articlecontent p", ".article p", ".v_news_content p",
                    ".entry_con p", ".wp_articlecontent", ".article"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(" ", strip=True)
                # 过滤元信息行：来源/编辑/审核/发布时间等
                for skip in ["来源单位", "编辑：", "审核发布", "发布时间", "供稿", "本网讯"]:
                    if skip in text[:60]:
                        text = text[text.find(skip) + len(skip):].lstrip("：:、 ")
                text = re.sub(r"\s+", " ", text).strip()
                if len(text) > 30:
                    return text[:max_len] + ("…" if len(text) > max_len else "")
        return ""
    except Exception as e:
        print(f"[warn] 详情页抓取失败 {url}: {e}", file=sys.stderr)
        return ""


def enrich_summaries(items, only_missing=True):
    """为没有摘要的校内文章并发抓取详情页首段。媒体聚焦不抓（外站不稳定）"""
    targets = [it for it in items
               if (not only_missing or not it.get("summary"))
               and it["column"] != "媒体聚焦"
               and "scau.edu.cn" in it["url"]]
    if not targets:
        return items
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda it: (it, fetch_article_summary(it["url"])), targets))
    for it, sm in results:
        if sm:
            it["summary"] = sm
    return items


def fetch_all():
    """抓取全部数据源，去重合并"""
    merged, seen_titles = [], set()
    for kind, url in SOURCES:
        try:
            r = requests.get(url, headers=UA, timeout=20)
            r.encoding = "utf-8"
            r.raise_for_status()
            items = parse_media_page(r.text) if kind == "media" else parse_news_page(r.text)
        except Exception as e:
            print(f"[warn] 抓取失败 {url}: {e}", file=sys.stderr)
            continue
        for it in items:
            key = re.sub(r"\s+", "", it["title"])[:30]  # 同题去重（跨栏目转载）
            if key in seen_titles:
                continue
            seen_titles.add(key)
            merged.append(it)
    # 详情页补全摘要（学校要闻列表页没 news_text / 科研进展 / 部分综合新闻）
    enrich_summaries(merged, only_missing=True)
    return merged


def _similar(t1: str, t2: str, n: int = 10) -> bool:
    """两条标题是否存在 n 字以上公共子串（同一事件多篇报道）"""
    if len(t1) < n or len(t2) < n:
        return False
    for i in range(len(t1) - n + 1):
        if t1[i:i + n] in t2:
            return True
    return False


def pick_top5(items, top_n=5):
    """按日期降序 + 栏目权重选出热点 TOP N
    规则：每栏目最多 2 条；同一事件相似标题只保留一条，保证多样性"""
    ranked = sorted(items, key=lambda x: WEIGHT.get(x["column"], 9))
    ranked = sorted(ranked, key=lambda x: x["date"], reverse=True)

    picked, col_cnt, picked_titles = [], {}, []
    for it in ranked:
        col = it["column"]
        if col_cnt.get(col, 0) >= 2:
            continue
        if any(_similar(it["title"], t) for t in picked_titles):
            continue
        picked.append(it)
        col_cnt[col] = col_cnt.get(col, 0) + 1
        picked_titles.append(it["title"])
        if len(picked) >= top_n:
            break
    return picked, ranked


def build_markdown(top):
    today = datetime.date.today().strftime("%m月%d日")
    lines = [f"#### 🌾 华南农业大学热点 TOP{len(top)} · {today}", ""]
    medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
    for i, it in enumerate(top):
        lines.append(f"**{medal[i] if i < len(medal) else i+1} [{it['column']}] {it['title']}**")
        lines.append(f"📅 {it['date']}  [👉 阅读原文]({it['url']})")
        if it.get("summary"):
            # 用引用块让摘要更醒目
            lines.append(f"> 📝 **摘要**：{it['summary']}")
        lines.append("")
    lines.append(f"*数据来源：[华南农业大学官网]({BASE}) · 自动抓取*")
    return "\n".join(lines)


def push_serverchan(sendkey: str, title: str, desp: str):
    """推送到 Server酱 → 微信"""
    api = f"https://sctapi.ftqq.com/{sendkey}.send"
    r = requests.post(api, data={"title": title, "desp": desp}, timeout=20)
    data = r.json()
    if data.get("code") == 0:
        print("✅ 推送成功，请打开微信「Server酱」服务号查看！")
    else:
        print(f"❌ 推送失败: {data}", file=sys.stderr)
        sys.exit(1)


def render_preview_html(title: str, md: str, out: str):
    """把 markdown 渲染成手机样式的 HTML 预览（模拟微信收到的效果）"""
    import html as h
    import markdown

    body = markdown.markdown(md, extensions=["tables", "nl2br"])
    today = datetime.date.today().strftime("%Y-%m-%d %H:%M")
    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{h.escape(title)}</title>
<style>
  :root {{ --green:#2e7d32; --bg:#f2f3f5; }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; padding:24px 12px; }}
  .phone {{ max-width:420px; margin:0 auto; background:#fff; border-radius:12px; overflow:hidden;
            box-shadow:0 4px 24px rgba(0,0,0,.08); }}
  .bar {{ background:var(--green); color:#fff; padding:14px 16px; display:flex; align-items:center; gap:10px; }}
  .bar .avatar {{ width:36px;height:36px;border-radius:6px;background:#fff3;display:flex;align-items:center;
                  justify-content:center;font-size:20px; }}
  .bar .name {{ font-size:15px; font-weight:600; }}
  .bar .sub {{ font-size:11px; opacity:.8; }}
  .msg {{ padding:16px; }}
  .bubble {{ background:#f7f9f7; border-radius:8px; padding:14px; font-size:14px; line-height:1.9; }}
  .bubble h4 {{ color:var(--green); font-size:16px; margin-bottom:8px; }}
  .bubble strong {{ color:#1b5e20; }}
  .bubble blockquote {{ border-left:3px solid #a5d6a7; margin:6px 0; padding:2px 10px; color:#666; font-size:13px; }}
  .bubble a {{ color:#1565c0; text-decoration:none; word-break:break-all; }}
  .bubble p {{ margin:6px 0; }}
  .foot {{ text-align:center; color:#999; font-size:12px; padding:12px; }}
</style></head>
<body>
  <div class="phone">
    <div class="bar">
      <div class="avatar">🌾</div>
      <div><div class="name">Server酱</div><div class="sub">刚才 · 推送给你</div></div>
    </div>
    <div class="msg"><div class="bubble">{body}</div></div>
    <div class="foot">预览效果 · 实际以微信「Server酱」服务号消息卡片呈现<br>{today}</div>
  </div>
</body></html>"""
    with open(out, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"📄 HTML 预览已生成: {out}")


def main():
    ap = argparse.ArgumentParser(description="华南农业大学热点资讯微信推送")
    ap.add_argument("--key", default=os.environ.get("SERVERCHAN_SENDKEY", ""),
                    help="Server酱 SendKey（https://sct.ftqq.com 扫码获取）")
    ap.add_argument("--top", type=int, default=5, help="推送条数，默认 5")
    ap.add_argument("--dry-run", action="store_true", help="只生成预览不推送")
    args = ap.parse_args()

    print("🔎 正在抓取华南农业大学官网资讯…")
    items = fetch_all()
    if not items:
        print("❌ 未抓到任何资讯，官网可能暂时无法访问", file=sys.stderr)
        sys.exit(1)
    top, rest = pick_top5(items, args.top)
    print(f"  共抓到 {len(items)} 条资讯，选出 TOP{len(top)}：")
    for i, it in enumerate(top, 1):
        print(f"  {i}. [{it['column']}] {it['title'][:40]} ({it['date']})")

    today = datetime.date.today().strftime("%m月%d日")
    title = f"🌾华农热点TOP{len(top)}｜{today}"
    desp = build_markdown(top)

    out_html = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview.html")
    render_preview_html(title, desp, out_html)

    if args.dry_run:
        print("\n💡 预览模式：未推送。获取 SendKey 后运行：")
        print("   python3 scau_news.py --key 你的SendKey")
        return

    if not args.key:
        print("❌ 缺少 SendKey：到 https://sct.ftqq.com 微信扫码登录后复制 SendKey", file=sys.stderr)
        sys.exit(1)
    push_serverchan(args.key, title, desp)


if __name__ == "__main__":
    main()
