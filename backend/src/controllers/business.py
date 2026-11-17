from fastapi import HTTPException
from src.models.entities import Segment, Outreach, ReconBatch


def ensure_segment(s, i):
    row = s.get(Segment, i)
    if not row:
        raise HTTPException(404, '分群版本不存在')
    return row


def ensure_outreach(s, i):
    row = s.get(Outreach, i)
    if not row:
        raise HTTPException(404, '触达方案不存在')
    return row


def ensure_batch(s, i, lock=False):
    query = s.query(ReconBatch)
    if lock:
        query = query.with_for_update().populate_existing()
    row = query.filter_by(id=i).first()
    if not row:
        raise HTTPException(404, '对账批次不存在')
    return row
