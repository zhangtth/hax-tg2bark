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


class TelegramMonitorError(Exception):
    pass


class BarkNotificationError(Exception):
    pass


def recovery_notify_after():
    try:
        return max(1, int(os.getenv("RECOVERY_NOTIFY_AFTER", "1")))
    except ValueError:
        return 1


def bark(title, body, level="active"):
    payload = {"title": title, "body": body, "group": "hax", "level": level}
    if level == "critical":
        payload["volume"] = 8
    req = urllib.request.Request(
        f"https://api.day.app/{BARK_KEY}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def safe_bark(title, body, level="active"):
    try:
        bark(title, body, level)
        return True
    except Exception as exc:
        print(f"Failed to send Bark notification: {exc}")
        return False


def classify(text):
    low = text.lower()
    if "will be removed" in low:
        return "HAX VPS 续签提醒", "critical"
    if "has been removed" in low:
        return "HAX VPS 已被删除", "critical"
    if "is ready" in low:
        return "HAX VPS 已就绪", "active"
    return "HAX 通知", "active"


def load_state():
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    state.setdefault("last_id", 0)
    state.setdefault("consecutive_failures", 0)
    state.setdefault("failure_notified", False)
    return state


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


async def fetch_messages(last_id):
    client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise TelegramMonitorError("Telegram session 已失效，需要重新登录生成 StringSession")
        return [m async for m in client.iter_messages(BOT, min_id=last_id) if m.text]
    except TelegramMonitorError:
        raise
    except Exception as exc:
        raise TelegramMonitorError(f"Telegram 连接或读取失败：{exc}") from exc
    finally:
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception as exc:
            print(f"Failed to disconnect Telegram client: {exc}")


async def main():
    state = load_state()
    last_id = state["last_id"]

    msgs = await fetch_messages(last_id)

    previous_failures = state.get("consecutive_failures", 0)
    if previous_failures >= recovery_notify_after():
        if not safe_bark(
            "HAX 监控已恢复",
            f"GitHub Actions 连续失败 {previous_failures} 次后已恢复连接。",
        ):
            raise BarkNotificationError("Bark recovery notification failed")

    for m in reversed(msgs):
        title, level = classify(m.text)
        if not safe_bark(title, m.text, level):
            state["last_id"] = last_id
            save_state(state)
            raise BarkNotificationError(f"Bark notification failed for Telegram message id {m.id}")
        last_id = max(last_id, m.id)

    state["last_id"] = last_id
    state["consecutive_failures"] = 0
    state["failure_notified"] = False
    save_state(state)
    print(f"done: {len(msgs)} new message(s), last_id={last_id}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except TelegramMonitorError as e:
        state = load_state()
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        if not state.get("failure_notified", False):
            state["failure_notified"] = safe_bark(
                "HAX 监控失效",
                f"GitHub Actions 暂时无法连接 Telegram，已记录失败次数：{state['consecutive_failures']}。错误：{e}",
                "critical",
            )
        save_state(state)
        print(
            "telegram monitor failed but suppressed workflow failure:",
            f"consecutive_failures={state['consecutive_failures']}",
            f"error={e}",
        )
    except BarkNotificationError as e:
        print("bark notification failed; state preserved for retry:", e)
