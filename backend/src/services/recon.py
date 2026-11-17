import hashlib
import json

from src.constants.enums import QUARANTINE_REASONS
from src.models.entities import Audit, Outreach, Receipt, ReconBatch
from src.utils.clock import utc_now


def checksum(items):
    return hashlib.sha256(json.dumps(list(items), ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def channel_key(channel):
    return channel.strip().casefold()


def fingerprint(channel, serial, member, occurred_at, result):
    return hashlib.sha256(
        '\x1f'.join([channel_key(channel), serial.strip(), member.strip(), occurred_at, result]).encode()
    ).hexdigest()


def unique_roster(members):
    seen, result = set(), []
    for code in members:
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result


def create_batch(session, outreach, note, actor):
    roster = unique_roster(outreach.members)
    batch = ReconBatch(
        outreach_id=outreach.id,
        root_outreach_id=outreach.root_outreach_id or outreach.id,
        state='pending',
        roster=roster,
        roster_checksum=checksum(roster),
        note=note,
        created=utc_now(),
    )
    session.add(batch)
    session.flush()
    batch.summary = compute_summary(session, batch)
    session.add(Audit(actor=actor, action=f'新建回执对账批次 {batch.id}（方案 {outreach.id}，冻结{len(roster)}人）', created=utc_now()))
    session.commit()
    return batch


def _latest(events):
    return max(events, key=lambda row: (row.occurred_at, row.id or 0))


def accepted_receipts(session, batch):
    return (
        session.query(Receipt)
        .filter_by(batch_id=batch.id, state='accepted')
        .order_by(Receipt.occurred_at, Receipt.id)
        .all()
    )


def batch_statuses(session, batch):
    """按发生时间还原每位冻结会员的最终状态；乱序到达不影响结论。"""
    events = {}
    for row in accepted_receipts(session, batch):
        events.setdefault(row.member, []).append(row)
    statuses = {member: 'pending' for member in batch.roster}
    for member, rows in events.items():
        if member in statuses:
            statuses[member] = 'success' if _latest(rows).result == 'delivered' else 'failed'
    return statuses


def chain_success_members(session, batch):
    """整条补发链上曾确认送达的会员；这些会员不再进入新的补发方案。"""
    return {row.member for row in accepted_receipts(session, batch) if row.result == 'delivered'}


def compute_summary(session, batch):
    receipts = session.query(Receipt).filter_by(batch_id=batch.id).all()
    statuses = batch_statuses(session, batch)
    success = sum(1 for value in statuses.values() if value == 'success')
    failed = sum(1 for value in statuses.values() if value == 'failed')
    pending = sum(1 for value in statuses.values() if value == 'pending')
    members_with_receipts = {row.member for row in receipts}
    covered = success + failed
    received = sum(row.occurrences or 1 for row in receipts)
    return {
        'roster_size': len(batch.roster),
        'success': success,
        'failed': failed,
        'pending': pending,
        'covered': covered,
        'received': received,
        'accepted': sum(1 for row in receipts if row.state == 'accepted'),
        'duplicated': received - len(receipts),
        'quarantined': sum(1 for row in receipts if row.state == 'quarantined'),
        'distinct_members_with_receipts': len(members_with_receipts),
        'overcount': len(members_with_receipts) - covered,
        'balance': success + failed + pending - len(batch.roster),
    }


def ingest(session, batch, items):
    """整批写入，调用方负责事务；返回本次回传的分类计数。

    - 完全相同的回执只保留一份凭证并累计到达次数，重复到达不增加覆盖人数；
    - 会员不在冻结名单内 -> 隔离「名单外回执」；
    - 同一渠道流水号承载互相矛盾的内容 -> 隔离「同号异文」，先到后到结论一致；
    - 其余回执按发生时间归入会员历程，迟到退信同样参与排序并可纠正此前的成功。
    """
    roster = set(batch.roster)
    existing = session.query(Receipt).filter_by(batch_id=batch.id).all()
    rows_by_fp = {row.fingerprint: row for row in existing}
    serial_contents = {}
    for row in existing:
        if row.state == 'accepted':
            serial_contents.setdefault((row.channel_key, row.serial), set()).add(
                (row.member, row.occurred_at, row.result)
            )
    conflict_serials = {
        (row.channel_key, row.serial)
        for row in existing
        if row.state == 'quarantined' and row.reason == QUARANTINE_REASONS[1]
    }

    payload = []
    for item in items:
        item.channel = item.channel.strip()
        item.serial = item.serial.strip()
        item.member = item.member.strip()
        fp = fingerprint(item.channel, item.serial, item.member, item.occurred_at, item.result)
        payload.append((item, fp))

    grouped = {}
    for item, fp in payload:
        grouped.setdefault((channel_key(item.channel), item.serial), []).append((item, fp))
    for key, group in grouped.items():
        contents = {(item.member, item.occurred_at, item.result) for item, _ in group}
        if len(contents | serial_contents.get(key, set())) > 1:
            conflict_serials.add(key)

    # 同号异文一旦成立，先前已接受的同号回执一并隔离，不按到达顺序选边
    retroactive = 0
    for row in existing:
        key = (row.channel_key, row.serial)
        if row.state == 'accepted' and key in conflict_serials:
            row.state = 'quarantined'
            row.reason = QUARANTINE_REASONS[1]
            retroactive += 1

    stats = {'accepted': 0, 'duplicated': 0, 'quarantined': 0, 'created': 0}
    now = utc_now()
    for item, fp in payload:
        key = (channel_key(item.channel), item.serial)
        stored = rows_by_fp.get(fp)
        if stored is not None:
            stored.occurrences = (stored.occurrences or 1) + 1
            stats['duplicated'] += 1
            continue
        if item.member not in roster:
            state, reason = 'quarantined', QUARANTINE_REASONS[0]
        elif key in conflict_serials:
            state, reason = 'quarantined', QUARANTINE_REASONS[1]
        else:
            state, reason = 'accepted', ''
            serial_contents.setdefault(key, set()).add((item.member, item.occurred_at, item.result))
        row = Receipt(
            batch_id=batch.id,
            channel=item.channel,
            channel_key=key[0],
            serial=item.serial,
            member=item.member,
            occurred_at=item.occurred_at,
            result=item.result,
            fingerprint=fp,
            state=state,
            reason=reason,
            received_at=now,
            occurrences=1,
        )
        session.add(row)
        rows_by_fp[fp] = row
        if state == 'accepted':
            stats['accepted'] += 1
        else:
            stats['quarantined'] += 1
        stats['created'] += 1
    if stats['created'] or stats['duplicated'] or retroactive:
        session.flush()
        # 只有会改变最终状态的回执才推翻已结算结论；纯重复回执不改变任何状态
        if (stats['accepted'] or retroactive) and batch.state == 'settled':
            batch.state = 'pending'
            batch.settled_at = ''
        batch.summary = compute_summary(session, batch)
    return stats


def resend_plans(session, batch):
    return (
        session.query(Outreach)
        .filter(Outreach.resend_for_batch_id == batch.id)
        .order_by(Outreach.id)
        .all()
    )


def settle(session, batch, items, note, actor):
    """结算一个批次：回执整批写入与状态冻结同属一个事务，任一步失败整批回滚。

    规则：
    - 待定会员不补发，只对确认失败者生成补发方案；
    - 整条补发链上曾送达成功的会员不再补发；
    - 补发回执回传原方案的对账批次，不新建批次；
    - 已被补发且尚未收到该会员新回执的，不重复补发，避免重复外发；
    - 同一批回执重跑时全部按重复抵达处理，不会重复建补发；迟到退信则重新打开待对账。
    """
    stats = ingest(session, batch, items) if items else {'created': 0, 'duplicated': 0}
    if note:
        batch.note = note
    session.flush()
    summary = compute_summary(session, batch)
    statuses = batch_statuses(session, batch)
    succeeded = chain_success_members(session, batch)
    last_receipt = {}
    for row in accepted_receipts(session, batch):
        last_receipt[row.member] = max(last_receipt.get(row.member, 0), row.id)
    plans = resend_plans(session, batch)
    member_plans = {}
    for plan in plans:
        for member in plan.members:
            member_plans.setdefault(member, []).append(plan)
    eligible = []
    for member, status in statuses.items():
        if status != 'failed' or member in succeeded:
            continue
        member_plan = max(member_plans.get(member, []), key=lambda plan: plan.id, default=None)
        watermark = (member_plan.receipt_watermark or {}).get(member, 0) if member_plan else 0
        # 已有补发且之后没有该会员的新回执 -> 不重复补发
        if member_plan is None or last_receipt.get(member, 0) > watermark:
            eligible.append(member)
    eligible.sort()
    created = None
    if eligible:
        source = session.get(Outreach, batch.outreach_id)
        watermark = {member: last_receipt.get(member, 0) for member in eligible}
        resend = Outreach(
            segment_id=source.segment_id if source else None,
            cluster_id=source.cluster_id if source else 0,
            title=('补发：' + (source.title if source else '触达方案'))[:100],
            note='对账确认失败后自动生成；名单已冻结，仅含确认失败且整条补发链尚无送达成功的会员。待定会员不补发；补发回执回传原方案的对账批次。',
            members=eligible,
            status='approved',
            parent_outreach_id=batch.outreach_id,
            root_outreach_id=batch.root_outreach_id,
            resend_for_batch_id=batch.id,
            created=utc_now(),
            receipt_watermark=watermark,
        )
        session.add(resend)
        session.flush()
        batch.resend_outreach_id = resend.id
        created = resend
    batch.summary = summary
    batch.state = 'settled'
    batch.settled_at = utc_now()
    session.add(
        Audit(
            actor=actor,
            action=f'结算对账批次 {batch.id}：成功{summary["success"]}/失败{summary["failed"]}/待定{summary["pending"]}'
            + (f'，生成补发方案 {created.id}（{len(eligible)}人）' if created else '，无新增补发'),
            created=utc_now(),
        )
    )
    session.commit()
    return created


def list_batches(session):
    rows = session.query(ReconBatch).order_by(ReconBatch.id.desc()).all()
    result = []
    for row in rows:
        summary = compute_summary(session, row)
        result.append(
            {
                'id': row.id,
                'outreach_id': row.outreach_id,
                'root_outreach_id': row.root_outreach_id,
                'state': row.state,
                'roster_size': len(row.roster),
                'note': row.note,
                'created': row.created,
                'settled_at': row.settled_at,
                'summary': summary,
                'balance_ok': summary['balance'] == 0,
            }
        )
    return result


def batch_detail(session, batch):
    summary = compute_summary(session, batch)
    statuses = batch_statuses(session, batch)
    succeeded = chain_success_members(session, batch)
    receipts = session.query(Receipt).filter_by(batch_id=batch.id).order_by(Receipt.id).all()
    events = {}
    for row in receipts:
        if row.state != 'accepted':
            continue
        events.setdefault(row.member, []).append(
            {
                'receipt_id': row.id,
                'channel': row.channel,
                'serial': row.serial,
                'occurred_at': row.occurred_at,
                'result': row.result,
                'received_at': row.received_at,
                'occurrences': row.occurrences or 1,
            }
        )
    history = []
    last_receipt = {}
    for row in receipts:
        if row.state == 'accepted':
            last_receipt[row.member] = max(last_receipt.get(row.member, 0), row.id)
    plans = resend_plans(session, batch)
    member_plans = {}
    for plan in plans:
        for member in plan.members:
            member_plans.setdefault(member, []).append(plan)
    for member in batch.roster:
        rows = sorted(events.get(member, []), key=lambda item: (item['occurred_at'], item['receipt_id']))
        plan = max(member_plans.get(member, []), key=lambda item: item.id, default=None)
        watermark = (plan.receipt_watermark or {}).get(member, 0) if plan else 0
        status = statuses.get(member, 'pending')
        eligible = (
            status == 'failed'
            and member not in succeeded
            and (plan is None or last_receipt.get(member, 0) > watermark)
        )
        history.append(
            {
                'member': member,
                'status': status,
                'events': rows,
                'chain_success': member in succeeded,
                'resend_eligible': eligible,
                'planned_in': plan.id if plan else None,
                'pending_in_plan': plan.id if plan and not eligible and status == 'failed' else None,
            }
        )
    resends = [
        {
            'outreach_id': plan.id,
            'parent_outreach_id': plan.parent_outreach_id,
            'title': plan.title,
            'status': plan.status,
            'created': plan.created,
            'members': plan.members,
            'already_successful': sorted(
                member for member in plan.members if member in succeeded
            ),
        }
        for plan in plans
    ]
    return {
        'batch': {
            'id': batch.id,
            'outreach_id': batch.outreach_id,
            'root_outreach_id': batch.root_outreach_id,
            'state': batch.state,
            'roster': batch.roster,
            'roster_checksum': batch.roster_checksum,
            'note': batch.note,
            'created': batch.created,
            'settled_at': batch.settled_at,
            'summary': summary,
            'balance_ok': summary['balance'] == 0,
        },
        'receipts': [
            {
                'id': row.id,
                'channel': row.channel,
                'serial': row.serial,
                'member': row.member,
                'occurred_at': row.occurred_at,
                'result': row.result,
                'state': row.state,
                'reason': row.reason,
                'received_at': row.received_at,
                'occurrences': row.occurrences or 1,
            }
            for row in receipts
        ],
        'quarantined': [
            {
                'serial': row.serial,
                'channel': row.channel,
                'member': row.member,
                'occurred_at': row.occurred_at,
                'result': row.result,
                'reason': row.reason,
            }
            for row in receipts
            if row.state == 'quarantined'
        ],
        'difference': {
            'roster_size': summary['roster_size'],
            'covered': summary['covered'],
            'pending': summary['pending'],
            'raw_members': summary['distinct_members_with_receipts'],
            'raw_receipts': summary['received'],
            'accepted_receipts': summary['accepted'],
            'duplicated': summary['duplicated'],
            'quarantined': summary['quarantined'],
            'overcount': summary['overcount'],
            'balance': summary['balance'],
        },
        'history': history,
        'resends': resends,
    }
