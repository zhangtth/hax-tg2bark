#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def bark_notify(base: str, key: str, title: str, body: str, group: str) -> None:
    url = f"{base.rstrip('/')}/{key}"
    payload = {"title": title, "body": body, "group": group, "level": "passive"}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        text = response.read().decode("utf-8", errors="replace")
        print(f"Bark response: HTTP {response.status} {text[:200]}")


def load_timezone(name: str):
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        if name == "Asia/Shanghai":
            return timezone(timedelta(hours=8), name="Asia/Shanghai")
        raise


def check_due_day_interval(now: datetime, start_date: date):
    interval_days = int(os.getenv("INTERVAL_DAYS", "4"))
    if interval_days <= 0:
        raise ValueError("INTERVAL_DAYS must be positive")

    elapsed_days = (now.date() - start_date).days
    is_due_day = elapsed_days >= 0 and elapsed_days % interval_days == 0
    details = {
        "elapsed_days": elapsed_days,
        "interval_days": interval_days,
    }
    return is_due_day, details


def check_due_month_interval(now: datetime, start_date: date):
    interval_months = int(os.getenv("INTERVAL_MONTHS", "5"))
    if interval_months <= 0:
        raise ValueError("INTERVAL_MONTHS must be positive")

    elapsed_months = (now.year - start_date.year) * 12 + now.month - start_date.month
    is_due_month = elapsed_months >= 0 and elapsed_months % interval_months == 0
    is_due_day = now.day == start_date.day
    details = {
        "elapsed_months": elapsed_months,
        "interval_months": interval_months,
        "target_day": start_date.day,
    }
    return is_due_month and is_due_day, details


def main() -> int:
    tz = load_timezone(os.getenv("TIMEZONE", "Asia/Shanghai"))
    now_override = os.getenv("NOW")
    if now_override:
        now = datetime.fromisoformat(now_override)
        if now.tzinfo is None:
            now = now.replace(tzinfo=tz)
        else:
            now = now.astimezone(tz)
    else:
        now = datetime.now(tz)

    start_date = date.fromisoformat(os.getenv("START_DATE", "2026-06-08"))
    schedule_type = os.getenv("SCHEDULE_TYPE", "day_interval")
    if schedule_type == "day_interval":
        is_due_day, details = check_due_day_interval(now, start_date)
    elif schedule_type == "month_interval":
        is_due_day, details = check_due_month_interval(now, start_date)
    else:
        raise ValueError(f"Unsupported SCHEDULE_TYPE: {schedule_type}")

    force_send = env_bool("FORCE_SEND")

    print(
        "Schedule check:",
        f"now={now:%Y-%m-%d %H:%M:%S %Z}",
        f"start={start_date}",
        f"schedule_type={schedule_type}",
        *[f"{key}={value}" for key, value in details.items()],
        f"is_due_day={is_due_day}",
        f"force_send={force_send}",
    )

    if not is_due_day and not force_send:
        print("Not a reminder day. Skip.")
        return 0

    if env_bool("DRY_RUN"):
        print("DRY_RUN is enabled. Skip sending Bark notification.")
        return 0

    bark_key = os.getenv("BARK_KEY", "").strip()
    if not bark_key:
        print("BARK_KEY secret is missing.", file=sys.stderr)
        return 2

    title = os.getenv("BARK_TITLE", "Hax VPS 续签提醒")
    group = os.getenv("BARK_GROUP", "hax-vps")
    base = os.getenv("BARK_BASE", "https://api.day.app")

    if force_send and not is_due_day:
        title = f"[测试] {title}"

    body_template = os.getenv(
        "BARK_BODY",
        "今天是 Hax VPS 续签提醒日。请登录 hax 完成续签。当前北京时间：{now}。",
    )
    body = body_template.replace("{now}", f"{now:%Y-%m-%d %H:%M}")

    try:
        bark_notify(base, bark_key, title, body, group)
    except urllib.error.URLError as exc:
        print(f"Failed to send Bark notification: {exc}", file=sys.stderr)
        return 1

    print("Reminder sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
