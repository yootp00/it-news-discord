"""IT 뉴스 / 장애 / 릴리즈 소식을 RSS·Atom 피드에서 모아 디스코드 웹훅으로 보낸다.

사용법:
    python news_bot.py            # 새 글만 디스코드로 전송
    python news_bot.py --dry-run  # 전송 없이 콘솔에만 출력 (상태 저장 안 함)

웹훅 주소는 config.json 또는 환경변수 DISCORD_WEBHOOK_URL 로 지정한다.
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATE_FILE = BASE / "state.json"
MAX_ITEMS_PER_FEED = 100  # 피드 상단(최신) 몇 개만 본다. MAX_SEEN 보다 작아야 옛 글이 재전송되지 않음
MAX_SEEN_PER_FEED = 300
MAX_POSTS_PER_RUN = 20

CATEGORY_STYLE = {
    "outage":  {"color": 0xE53935, "label": "🚨 장애"},
    "security": {"color": 0xFB8C00, "label": "🔐 보안"},
    "release": {"color": 0x1E88E5, "label": "🚀 릴리즈"},
    "ai":      {"color": 0x8E24AA, "label": "🤖 AI"},
    "news":    {"color": 0x43A047, "label": "📰 IT 뉴스"},
}

ATOM = "{http://www.w3.org/2005/Atom}"


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "it-news-discord/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def strip_html(text, limit=300):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def parse_apple_status(text):
    """Apple 시스템 상태(jsonCallback({...})) 를 이벤트 목록으로 변환. 진행 중/해결을 따로 알린다."""
    data = json.loads(text[text.index("(") + 1:text.rindex(")")])
    status_ko = {"ongoing": "진행 중", "resolved": "해결됨", "upcoming": "예정"}
    items = []
    for service in data.get("services", []):
        for e in service.get("events", []):
            state = e.get("eventStatus", "")
            items.append({
                "id": f"{e.get('messageId')}:{state}",
                "title": f"[{e.get('statusType', '')}] {service['serviceName'].strip()} - {status_ko.get(state, state)}",
                "link": "https://developer.apple.com/system-status/",
                "summary": f"{e.get('message', '')} ({e.get('startDate', '')} ~ {e.get('endDate') or '진행 중'})",
                "_ts": e.get("epochStartDate") or 0,
            })
    return sorted(items, key=lambda i: i["_ts"], reverse=True)


def parse_feed(raw):
    """RSS 2.0 과 Atom 을 모두 처리해 (id, title, link, summary) 목록을 최신순으로 반환."""
    text = raw.decode("utf-8", errors="replace").lstrip()
    if text.startswith("jsonCallback("):
        return parse_apple_status(text)
    root = ET.fromstring(raw)
    items = []
    if root.tag == f"{ATOM}feed":
        for e in root.findall(f"{ATOM}entry"):
            link_el = e.find(f"{ATOM}link[@rel='alternate']")
            if link_el is None:
                link_el = e.find(f"{ATOM}link")
            link = link_el.get("href") if link_el is not None else ""
            items.append({
                "id": e.findtext(f"{ATOM}id") or link,
                "title": (e.findtext(f"{ATOM}title") or "").strip(),
                "link": link,
                "summary": strip_html(e.findtext(f"{ATOM}summary") or e.findtext(f"{ATOM}content")),
            })
    else:
        for e in root.iter("item"):
            link = (e.findtext("link") or "").strip()
            items.append({
                "id": e.findtext("guid") or link or e.findtext("title"),
                "title": (e.findtext("title") or "").strip(),
                "link": link,
                "summary": strip_html(e.findtext("description")),
            })
    return items


def matches(feed, item):
    """feeds.json 의 include / exclude 정규식으로 제목+요약을 거른다."""
    text = f"{item['title']} {item['summary']}"
    if feed.get("include") and not re.search(feed["include"], text):
        return False
    if feed.get("exclude") and re.search(feed["exclude"], text):
        return False
    return True


def post_discord(webhook, feed, item):
    style = CATEGORY_STYLE.get(feed["category"], CATEGORY_STYLE["news"])
    embed = {
        "title": item["title"][:256] or "(제목 없음)",
        "color": style["color"],
        "footer": {"text": f"{style['label']} · {feed['name']}"},
    }
    if item["link"]:
        embed["url"] = item["link"]
    if item["summary"]:
        embed["description"] = item["summary"]
    payload = {"username": "IT News Bot", "embeds": [embed]}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook, data=data,
        headers={"Content-Type": "application/json", "User-Agent": "it-news-discord/1.0"},
    )
    for _ in range(3):
        try:
            urllib.request.urlopen(req, timeout=20)
            time.sleep(1)  # 디스코드 웹훅 rate limit 여유
            return True
        except urllib.error.HTTPError as err:
            if err.code == 429:
                time.sleep(float(err.headers.get("Retry-After", "2")))
                continue
            print(f"  ! 디스코드 전송 실패 {err.code}: {err.read()[:200]}", file=sys.stderr)
            return False
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test", action="store_true", help="웹훅 연결 확인용 메시지를 보낸다")
    args = parser.parse_args()

    config = load_json(BASE / "config.json", {})
    webhooks = config.get("webhooks", {})
    for category in CATEGORY_STYLE:  # GitHub Secrets 용: DISCORD_WEBHOOK_OUTAGE 등
        env_hook = os.environ.get(f"DISCORD_WEBHOOK_{category.upper()}")
        if env_hook:
            webhooks[category] = env_hook
    default_hook = os.environ.get("DISCORD_WEBHOOK_URL") or webhooks.get("default")
    # 종류별 웹훅이 다 있으면 기본 웹훅은 없어도 된다. 갈 곳 없는 종류만 건너뛴다.
    unrouted = [c for c in CATEGORY_STYLE if not (webhooks.get(c) or default_hook)]
    if not args.dry_run:
        if len(unrouted) == len(CATEGORY_STYLE):
            sys.exit("웹훅이 없습니다. DISCORD_WEBHOOK_URL 또는 DISCORD_WEBHOOK_<종류> 를 설정하세요.")
        if unrouted:
            print(f"[경고] 웹훅이 없어 건너뛰는 종류: {', '.join(unrouted)}")

    if args.test:
        test_item = {"title": "✅ IT News Bot 연결 테스트", "link": "",
                     "summary": "이 메시지가 보이면 웹훅이 정상입니다. 이제 새 소식이 생기면 여기로 옵니다."}
        targets = {c: webhooks[c] for c in CATEGORY_STYLE if webhooks.get(c)}
        if default_hook and len(targets) < len(CATEGORY_STYLE):
            targets.setdefault("news", default_hook)  # 기본 채널도 쓰이면 함께 확인
        for category, hook in targets.items():
            if hook:
                ok = post_discord(hook, {"name": "테스트", "category": category}, test_item)
                print(f"[테스트] {category}: {'성공' if ok else '실패'}")
                if not ok:
                    sys.exit(1)
        return

    feeds = load_json(BASE / "feeds.json", [])
    state = load_json(STATE_FILE, {})
    posted = 0
    cache = {}  # 같은 URL 을 필터만 달리 쓰는 피드는 한 번만 받아온다

    for feed in feeds:
        try:
            if feed["url"] not in cache:
                cache[feed["url"]] = parse_feed(fetch(feed["url"]))[:MAX_ITEMS_PER_FEED]
            items = cache[feed["url"]]
        except Exception as err:
            print(f"[실패] {feed['name']}: {err}", file=sys.stderr)
            continue

        key = f"{feed['name']}|{feed['url']}"  # 같은 URL 을 다른 필터로 쓰는 피드 구분
        first_run = key not in state
        seen = state.get(key, [])
        new_items = [i for i in items if i["id"] not in seen and matches(feed, i)]
        print(f"[{feed['name']}] 전체 {len(items)} / 새 글 {len(new_items)}" + (" (첫 실행: 전송 생략)" if first_run else ""))

        if args.dry_run:
            for item in new_items[:3]:
                print(f"    - {item['title']}  {item['link']}")
            continue

        # 첫 실행에는 기존 글을 '본 것'으로만 기록해 도배를 막는다
        if not first_run:
            hook = webhooks.get(feed["category"]) or default_hook
            for item in reversed(new_items if hook else []):  # 오래된 것부터 전송
                if posted >= MAX_POSTS_PER_RUN:
                    break
                if post_discord(hook, feed, item):
                    seen.append(item["id"])
                    posted += 1
        else:
            seen.extend(i["id"] for i in new_items)

        state[key] = seen[-MAX_SEEN_PER_FEED:]

    if not args.dry_run:
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"전송 {posted}건")


if __name__ == "__main__":
    main()
