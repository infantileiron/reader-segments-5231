from datetime import datetime, timezone


def normalize_occurred_at(value):
    """把发生时间规范为固定宽度的 UTC 时间串，便于按字符串稳定排序。"""
    text = str(value).strip()
    if not text:
        raise ValueError('发生时间不能为空')
    try:
        moment = datetime.fromisoformat(text[:-1] + '+00:00' if text.endswith(('Z', 'z')) else text)
    except ValueError:
        raise ValueError('发生时间必须是 ISO 8601，例如 2026-11-10T09:30:00Z')
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc)
    return moment.strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def utc_now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
