"""核心时间窗口解析，不绑定任何数据源。"""

import re
import time
from datetime import datetime


def _parse_datetime_token(token: str) -> int:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return int(time.mktime(datetime.strptime(token, fmt).timetuple()))
        except ValueError:
            continue
    raise ValueError(f"invalid datetime '{token}'; use 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DD'")


def parse_time_range(value: str = "24h") -> tuple:
    value = value or "24h"
    match = re.fullmatch(r"(\d+)([mhd])", value)
    if match:
        amount = int(match.group(1))
        seconds = {"m": 60, "h": 3600, "d": 86400}[match.group(2)]
        now = int(time.time())
        return now - amount * seconds, now
    if "," in value:
        parts = [item.strip() for item in value.split(",")]
        if len(parts) != 2 or not all(parts):
            raise ValueError("range must contain exactly two non-empty bounds")
        bounds = [int(item) if item.isdigit() else _parse_datetime_token(item) for item in parts]
        if bounds[0] > bounds[1]:
            raise ValueError("time range start must be earlier than or equal to end")
        return tuple(bounds)
    raise ValueError(
        f"invalid time range '{value}'; use '24h', '7d', 'from,to', or 'YYYY-MM-DD HH:MM:SS,YYYY-MM-DD HH:MM:SS'"
    )
