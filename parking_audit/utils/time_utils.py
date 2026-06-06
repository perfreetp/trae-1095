from datetime import datetime, timedelta
from typing import Optional, List

from parking_audit.config import get_config_value


def parse_datetime(date_str: str, formats: Optional[List[str]] = None) -> Optional[datetime]:
    if not date_str:
        return None
    
    if formats is None:
        formats = get_config_value("import", "date_formats", default=[
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y%m%d%H%M%S"
        ])
    
    date_str = date_str.strip()
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            continue
    
    try:
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        pass
    
    try:
        ts = int(date_str)
        if ts > 1e12:
            ts = ts / 1000
        return datetime.fromtimestamp(ts)
    except (ValueError, TypeError, OSError):
        pass
    
    return None


def format_datetime(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    if not dt:
        return ""
    return dt.strftime(fmt)


def time_diff_minutes(dt1: datetime, dt2: datetime) -> float:
    if not dt1 or not dt2:
        return 0.0
    return abs((dt1 - dt2).total_seconds()) / 60


def is_time_overlap(start1: datetime, end1: datetime, start2: datetime, end2: datetime) -> bool:
    if not all([start1, end1, start2, end2]):
        return False
    return start1 < end2 and start2 < end1


def is_cross_day(start: datetime, end: datetime) -> bool:
    if not start or not end:
        return False
    return start.date() != end.date()


def get_cross_day_count(start: datetime, end: datetime) -> int:
    if not start or not end:
        return 0
    return (end.date() - start.date()).days


def is_time_within_tolerance(
    dt1: datetime,
    dt2: datetime,
    tolerance_minutes: Optional[int] = None
) -> bool:
    if tolerance_minutes is None:
        tolerance_minutes = get_config_value("matching", "time_tolerance_minutes", default=15)
    return time_diff_minutes(dt1, dt2) <= tolerance_minutes


def get_date_range(start_date: str, end_date: str) -> List[datetime]:
    start = parse_datetime(start_date)
    end = parse_datetime(end_date)
    if not start or not end:
        return []
    
    dates = []
    current = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    while current <= end:
        dates.append(current)
        current += timedelta(days=1)
    
    return dates


def is_same_day(dt1: datetime, dt2: datetime) -> bool:
    if not dt1 or not dt2:
        return False
    return dt1.date() == dt2.date()


def get_day_start(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def get_day_end(dt: datetime) -> datetime:
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)


def get_month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def get_month_end(dt: datetime) -> datetime:
    next_month = dt.replace(day=28, hour=23, minute=59, second=59, microsecond=999999) + timedelta(days=4)
    return next_month - timedelta(days=next_month.day)
