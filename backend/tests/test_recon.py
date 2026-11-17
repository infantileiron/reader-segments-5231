from conftest import login, make_outreach, start_batch, receipt, settle


def test_batch_starts_pending_and_balances_roster(client):
    login(client)
    outreach = make_outreach(client, ['SL-001', 'SL-002', 'SL-003'])
    batch_id = start_batch(client, outreach)
    detail = client.get(f'/recon/batches/{batch_id}').json()
    assert detail['batch']['state'] == 'pending'
    assert detail['batch']['summary']['roster_size'] == 3
    assert detail['batch']['summary']['pending'] == 3
    assert detail['batch']['summary']['balance'] == 0
    assert detail['batch']['balance_ok'] is True


def test_out_of_order_receipts_restore_history_and_late_bounce_corrects_success(client):
    login(client)
    outreach = make_outreach(client, ['SL-001', 'SL-002'])
    batch_id = start_batch(client, outreach)
    # SL-001 先到退信，后到（更早发生）的送达；SL-002 先到送达，后到（更晚发生）的退信
    detail = settle(
        client,
        batch_id,
        [
            receipt('S-2', 'SL-001', 'bounced', '2026-11-10T10:00:00Z'),
            receipt('S-3', 'SL-002', 'delivered', '2026-11-10T09:00:00Z'),
            receipt('S-1', 'SL-001', 'delivered', '2026-11-10T08:00:00Z'),
            receipt('S-4', 'SL-002', 'bounced', '2026-11-10T11:00:00Z'),
        ],
    )
    history = {row['member']: row for row in detail['history']}
    assert [event['serial'] for event in history['SL-001']['events']] == ['S-1', 'S-2']
    assert [event['serial'] for event in history['SL-002']['events']] == ['S-3', 'S-4']
    assert history['SL-001']['status'] == 'failed'
    assert history['SL-002']['status'] == 'failed'
    summary = detail['batch']['summary']
    assert (summary['success'], summary['failed'], summary['pending']) == (0, 2, 0)
    assert summary['balance'] == 0


def test_duplicates_do_not_inflate_covered_members_and_are_visible(client):
    login(client)
    outreach = make_outreach(client, ['SL-001', 'SL-002'])
    batch_id = start_batch(client, outreach)
    first = settle(client, batch_id, [receipt('S-1', 'SL-001', 'delivered', '2026-11-10T09:00:00Z')])
    assert first['batch']['summary']['covered'] == 1
    assert first['batch']['summary']['overcount'] == 0
    # 同一回执重复回传：只记凭证，不重复计数
    again = settle(
        client,
        batch_id,
        [
            receipt('S-1', 'SL-001', 'delivered', '2026-11-10T09:00:00Z'),
            receipt('S-1', 'SL-001', 'delivered', '2026-11-10T09:00:00Z'),
        ],
    )
    summary = again['batch']['summary']
    assert summary['covered'] == 1
    assert summary['success'] == 1
    assert summary['pending'] == 1
    assert summary['balance'] == 0
    assert summary['received'] == 3
    assert summary['duplicated'] == 2


def test_quarantine_unknown_member_and_same_serial_conflict(client):
    login(client)
    outreach = make_outreach(client, ['SL-001'])
    batch_id = start_batch(client, outreach)
    detail = settle(
        client,
        batch_id,
        [
            receipt('S-9', 'SL-999', 'delivered', '2026-11-10T09:00:00Z'),
            receipt('S-1', 'SL-001', 'delivered', '2026-11-10T10:00:00Z'),
            receipt('S-1', 'SL-001', 'bounced', '2026-11-10T10:00:00Z'),
        ],
    )
    assert sorted(item['reason'] for item in detail['quarantined']) == sorted(['名单外回执', '同号异文', '同号异文'])
    assert detail['batch']['summary']['covered'] == 0
    assert detail['history'][0]['status'] == 'pending'


def test_late_same_serial_conflict_retroactively_quarantines_earlier_receipt(client):
    login(client)
    outreach = make_outreach(client, ['SL-001'])
    batch_id = start_batch(client, outreach)
    settle(client, batch_id, [receipt('S-1', 'SL-001', 'delivered', '2026-11-10T09:00:00Z')])
    detail = settle(client, batch_id, [receipt('S-1', 'SL-001', 'bounced', '2026-11-10T10:00:00Z')])
    assert detail['batch']['summary']['covered'] == 0
    assert detail['history'][0]['status'] == 'pending'
    assert all(item['reason'] == '同号异文' for item in detail['quarantined'])
    assert len(detail['quarantined']) == 2


def test_settle_without_receipts_keeps_pending_and_creates_no_plan(client):
    login(client)
    outreach = make_outreach(client, ['SL-001'])
    batch_id = start_batch(client, outreach)
    detail = settle(client, batch_id, [])
    assert detail['batch']['state'] == 'settled'
    assert detail['batch']['summary']['pending'] == 1
    assert detail['batch']['summary']['balance'] == 0
    assert detail['resends'] == []


def test_channel_name_is_case_insensitive_for_dedupe_and_conflict(client):
    login(client)
    outreach = make_outreach(client, ['SL-001'])
    batch_id = start_batch(client, outreach)
    detail = settle(
        client,
        batch_id,
        [
            receipt('S-1', 'SL-001', 'delivered', '2026-11-10T09:00:00Z', channel='SMS'),
            receipt('S-1', 'SL-001', 'delivered', '2026-11-10T09:00:00Z', channel='sms'),
        ],
    )
    assert detail['batch']['summary']['duplicated'] == 1
    assert detail['batch']['summary']['covered'] == 1


def test_batch_list_exposes_balance_and_summary(client):
    login(client)
    outreach = make_outreach(client, ['SL-001', 'SL-002'])
    batch_id = start_batch(client, outreach)
    settle(client, batch_id, [receipt('S-1', 'SL-001', 'delivered', '2026-11-10T09:00:00Z')])
    rows = client.get('/recon/batches').json()
    row = next(item for item in rows if item['id'] == batch_id)
    assert row['summary']['success'] == 1
    assert row['summary']['pending'] == 1
    assert row['balance_ok'] is True
    assert row['state'] == 'settled'


def test_only_confirmed_failures_get_resend_and_pending_does_not(client):
    login(client)
    outreach = make_outreach(client, ['SL-001', 'SL-002', 'SL-003'])
    batch_id = start_batch(client, outreach)
    detail = settle(
        client,
        batch_id,
        [
            receipt('S-1', 'SL-001', 'delivered', '2026-11-10T09:00:00Z'),
            receipt('S-2', 'SL-002', 'bounced', '2026-11-10T09:30:00Z'),
        ],
    )
    summary = detail['batch']['summary']
    assert (summary['success'], summary['failed'], summary['pending']) == (1, 1, 1)
    assert summary['balance'] == 0
    assert len(detail['resends']) == 1
    plan = detail['resends'][0]
    assert plan['members'] == ['SL-002']
    assert plan['status'] == 'approved'
    assert plan['already_successful'] == []


def test_resend_receipts_return_to_original_batch_and_chain_success_blocks_resend(client):
    login(client)
    outreach = make_outreach(client, ['SL-001', 'SL-002'])
    batch_id = start_batch(client, outreach)
    first = settle(client, batch_id, [receipt('S-1', 'SL-001', 'bounced', '2026-11-10T09:00:00Z')])
    plan_id = first['resends'][0]['outreach_id']
    # 补发回执仍然回传原批次；同一渠道换新流水号
    second = settle(client, batch_id, [receipt('S-2', 'SL-001', 'delivered', '2026-11-11T09:00:00Z')])
    assert second['batch']['state'] == 'settled'
    assert second['batch']['summary']['success'] == 1
    # 已成功的会员不再补发
    assert second['resends'][0]['outreach_id'] == plan_id
    assert second['history'][0]['chain_success'] is True
    assert second['history'][0]['resend_eligible'] is False


def test_late_bounce_after_resend_success_creates_no_new_plan(client):
    login(client)
    outreach = make_outreach(client, ['SL-001'])
    batch_id = start_batch(client, outreach)
    settle(client, batch_id, [receipt('S-1', 'SL-001', 'bounced', '2026-11-10T09:00:00Z')])
    settle(client, batch_id, [receipt('S-2', 'SL-001', 'delivered', '2026-11-11T09:00:00Z')])
    # 更晚发生的退信（迟到）纠正为失败，但整条链已有成功，故不再补发
    late = settle(client, batch_id, [receipt('S-3', 'SL-001', 'bounced', '2026-11-12T09:00:00Z')])
    assert late['history'][0]['status'] == 'failed'
    assert late['history'][0]['chain_success'] is True
    assert len(late['resends']) == 1


def test_late_success_after_resend_bounce_blocks_further_resend(client):
    login(client)
    outreach = make_outreach(client, ['SL-001'])
    batch_id = start_batch(client, outreach)
    first = settle(client, batch_id, [receipt('S-1', 'SL-001', 'bounced', '2026-11-10T09:00:00Z')])
    plan_id = first['resends'][0]['outreach_id']
    # 补发退信后，再迟到一条更早发生的送达：按发生时间应还原为成功
    second = settle(
        client,
        batch_id,
        [
            receipt('S-2', 'SL-001', 'delivered', '2026-11-11T09:00:00Z'),
            receipt('S-3', 'SL-001', 'bounced', '2026-11-12T09:00:00Z'),
        ],
    )
    assert second['history'][0]['status'] == 'failed'
    third = settle(client, batch_id, [receipt('S-4', 'SL-001', 'delivered', '2026-11-11T12:00:00Z')])
    # 最晚一条事件是 11/12 的退信，故仍为失败；但链上已有 11/11 的成功，不再补发
    assert third['history'][0]['status'] == 'failed'
    assert third['history'][0]['chain_success'] is True
    assert len(third['resends']) == 1
    assert third['resends'][0]['outreach_id'] == plan_id


def test_resend_outreach_cannot_open_its_own_batch(client):
    login(client)
    outreach = make_outreach(client, ['SL-001'])
    batch_id = start_batch(client, outreach)
    detail = settle(client, batch_id, [receipt('S-1', 'SL-001', 'bounced', '2026-11-10T09:00:00Z')])
    plan_id = detail['resends'][0]['outreach_id']
    response = client.post('/recon/batches', json={'outreach_id': plan_id, 'note': '错误地给补发建批次'})
    assert response.status_code == 409


def test_unapproved_outreach_cannot_open_batch(client):
    from src.config.database import Session
    from src.models.entities import Outreach

    login(client)
    with Session() as session:
        draft = Outreach(segment_id=None, cluster_id=0, title='未签核方案', note='说明足够长测试用', members=['SL-001'], status='draft')
        session.add(draft)
        session.flush()
        draft.root_outreach_id = draft.id
        session.commit()
        draft_id = draft.id
    response = client.post('/recon/batches', json={'outreach_id': draft_id, 'note': ''})
    assert response.status_code == 409


def test_second_bounce_after_resend_opens_next_cycle_but_replay_does_not(client):
    login(client)
    outreach = make_outreach(client, ['SL-002'])
    batch_id = start_batch(client, outreach)
    first = settle(client, batch_id, [receipt('S-1', 'SL-002', 'bounced', '2026-11-10T09:00:00Z')])
    assert [row['members'] for row in first['resends']] == [['SL-002']]
    # 补发再次退信（新回执）-> 进入下一轮补发
    second = settle(client, batch_id, [receipt('S-2', 'SL-002', 'bounced', '2026-11-11T09:00:00Z')])
    assert [row['members'] for row in second['resends']] == [['SL-002'], ['SL-002']]
    # 重放同一批 -> 不新增
    replay = settle(client, batch_id, [receipt('S-2', 'SL-002', 'bounced', '2026-11-11T09:00:00Z')])
    assert len(replay['resends']) == 2
    # 补发成功（迟到、发生时间更早）-> 终态为成功，链上已成功
    third = settle(client, batch_id, [receipt('S-3', 'SL-002', 'delivered', '2026-11-11T08:00:00Z')])
    assert third['history'][0]['status'] == 'failed'  # 最晚事件仍是 11/11 09:00 的退信
    settle(client, batch_id, [receipt('S-4', 'SL-002', 'delivered', '2026-11-12T09:00:00Z')])
    late = settle(client, batch_id, [receipt('S-5', 'SL-002', 'delivered', '2026-11-12T08:00:00Z')])
    assert late['history'][0]['chain_success'] is True
    assert len(late['resends']) == 2


def test_replaying_same_settlement_is_idempotent(client):
    login(client)
    outreach = make_outreach(client, ['SL-001', 'SL-002'])
    batch_id = start_batch(client, outreach)
    payload = [
        receipt('S-1', 'SL-001', 'bounced', '2026-11-10T09:00:00Z'),
        receipt('S-2', 'SL-002', 'delivered', '2026-11-10T09:00:00Z'),
    ]
    first = settle(client, batch_id, payload)
    second = settle(client, batch_id, payload)
    assert len(first['resends']) == 1
    assert len(second['resends']) == 1
    assert second['batch']['summary']['covered'] == 2
    assert second['batch']['summary']['duplicated'] == 2


def test_invalid_item_rejects_whole_batch(client):
    login(client)
    outreach = make_outreach(client, ['SL-001'])
    batch_id = start_batch(client, outreach)
    response = client.post(
        f'/recon/batches/{batch_id}/settle',
        json={
            'receipts': [
                receipt('S-1', 'SL-001', 'delivered', '2026-11-10T09:00:00Z'),
                {'channel': 'sms', 'serial': 'S-2', 'member': 'SL-001', 'occurred_at': 'not-a-date', 'result': 'delivered'},
            ]
        },
    )
    assert response.status_code == 422
    detail = client.get(f'/recon/batches/{batch_id}').json()
    assert detail['receipts'] == []
    assert detail['batch']['state'] == 'pending'
    assert detail['batch']['summary']['covered'] == 0


def test_viewer_cannot_settle_but_can_read(client):
    login(client)
    outreach = make_outreach(client, ['SL-001'])
    batch_id = start_batch(client, outreach)
    login(client, 'viewer')
    assert client.get(f'/recon/batches/{batch_id}').status_code == 200
    response = client.post(f'/recon/batches/{batch_id}/settle', json={'receipts': []})
    assert response.status_code == 403
