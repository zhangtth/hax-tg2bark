import asyncio
import json
import os
import urllib.request

from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION = os.environ["TG_SESSION"]
BARK_KEY = os.environ["BARK_KEY"]
BOT = "HaxTG_bot"
STATE_FILE = "state.json"


def bark(title, body, level="active"):
    payload = {"title": title, "body": body, "group": "hax", "level": level}
    if level == "critical":
        payload["volume"] = 8
    req = urllib.request.Request(
        f"https://api.day.app/{BARK_KEY}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def classify(text):
    low = text.lower()
    if "will be removed" in low:
        return "HAX VPS 续签提醒", "critical"
    if "has been removed" in low:
        return "HAX VPS 已被删除", "critical"
    if "is ready" in low:
        return "HAX VPS 已就绪", "active"
    return "HAX 通知", "active"


async def main():
    with open(STATE_FILE) as f:
        state = json.load(f)
    last_id = state["last_id"]

    client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError("Telegram session 已失效，需要重新登录生成 StringSession")
    msgs = [m async for m in client.iter_messages(BOT, min_id=last_id) if m.text]
    await client.disconnect()

    for m in reversed(msgs):
        title, level = classify(m.text)
        bark(title, m.text, level)
        last_id = max(last_id, m.id)

    state["last_id"] = last_id
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
    print(f"done: {len(msgs)} new message(s), last_id={last_id}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        try:
            bark("HAX 监控失效", f"GitHub Actions 出错，请检查：{e}", "critical")
        except Exception:
            pass
        raise
