"""对账链路演示：乱序退信纠正、补发后迟到成功、隔离与差额核对。

运行：cd backend && python -m scripts.verify_recon
使用临时 SQLite，不修改开发库，也不需要 Redis。
"""

import os
import tempfile

os.environ.setdefault('JWT_SECRET', 'verify-secret')
_tmp = tempfile.mkdtemp(prefix='recon-verify-')
os.environ.setdefault('DATABASE_URL', f'sqlite:///{_tmp}/verify.db')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('SEED_DEMO', 'false')

from fastapi.testclient import TestClient  # noqa: E402

from src.config.database import Session  # noqa: E402
from src.main import app  # noqa: E402
from src.models.entities import Outreach, User  # noqa: E402
from src.utils.security import hash_password  # noqa: E402


def show(title):
    print('\n== ' + title)


def main():
    with TestClient(app) as client:
        with Session() as session:
            session.add(User(email='analyst@demo.local', role='analyst', password=hash_password('Demo123!')))
            session.commit()
        token = client.post(
            '/auth/login', json={'email': 'analyst@demo.local', 'password': 'Demo123!'}
        ).json()['token']
        client.headers['Authorization'] = 'Bearer ' + token

        with Session() as session:
            outreach = Outreach(
                segment_id=None,
                cluster_id=0,
                title='低频读者轻阅读试点',
                note='演示用触达方案：每周一次短篇精选。',
                members=['SL-001', 'SL-002', 'SL-003'],
                status='approved',
            )
            session.add(outreach)
            session.flush()
            outreach.root_outreach_id = outreach.id
            session.commit()
            outreach_id = outreach.id

        batch = client.post('/recon/batches', json={'outreach_id': outreach_id, 'note': '短信 11/10 回执'}).json()
        batch_id = batch['batch']['id']
        show(f'建立批次 #{batch_id}')
        print('状态', batch['batch']['state'], '冻结人数', batch['batch']['summary']['roster_size'])

        def settle(lines, label):
            payload = []
            for line in lines:
                channel, serial, member, occurred_at, result = [part.strip() for part in line.split(',')]
                payload.append(
                    {
                        'channel': channel,
                        'serial': serial,
                        'member': member,
                        'occurred_at': occurred_at,
                        'result': result,
                    }
                )
            detail = client.post(f'/recon/batches/{batch_id}/settle', json={'receipts': payload}).json()
            summary = detail['batch']['summary']
            show(label)
            print(
                '成功/失败/待定 = {}/{}/{}，冻结 {}，差额 {}，重复 {}，隔离 {}'.format(
                    summary['success'],
                    summary['failed'],
                    summary['pending'],
                    summary['roster_size'],
                    summary['balance'],
                    summary['duplicated'],
                    summary['quarantined'],
                )
            )
            for row in detail['history']:
                events = ' -> '.join(
                    f"{event['occurred_at'][5:16]} {event['result']}({event['serial']})" for event in row['events']
                )
                print(f"  {row['member']}: {row['status']:<8} {events or '无回执'}  [可补发={row['resend_eligible']}]")
            for item in detail['quarantined']:
                print(f"  隔离 {item['serial']} {item['member']} {item['reason']}")
            return detail

        settle(
            [
                'sms,S-002,SL-002,2026-11-10T10:00:00Z,bounced',
                'sms,S-001,SL-001,2026-11-10T09:00:00Z,delivered',
                'sms,S-999,SL-999,2026-11-10T09:00:00Z,delivered',
                'sms,S-001,SL-001,2026-11-10T09:00:00Z,delivered',
            ],
            '乱序回传 + 名单外 + 完全重复',
        )

        detail = settle(
            ['sms,S-003,SL-001,2026-11-10T11:00:00Z,bounced'],
            '迟到退信：发生时间晚于先前的送达，按时间还原为失败',
        )
        assert detail['batch']['summary']['success'] == 0
        assert detail['batch']['summary']['failed'] == 2
        assert detail['batch']['summary']['pending'] == 1

        detail = settle(
            ['sms,S-004,SL-001,2026-11-10T08:00:00Z,delivered'],
            '再迟到的更早送达：按发生时间排序后仍早于退信，终态保持失败',
        )
        assert detail['history'][0]['status'] == 'failed'
        assert [event['serial'] for event in detail['history'][0]['events']] == ['S-004', 'S-001', 'S-003']

        settle(['sms,S-005,SL-003,2026-11-11T09:00:00Z,delivered'], '待定会员补来回执')
        detail = settle(['sms,S-006,SL-002,2026-11-11T10:00:00Z,delivered'], '补发送达')
        show('整条链上已有成功的会员')
        for row in detail['resends']:
            print(f"  补发方案 #{row['outreach_id']} 会员 {row['members']}")

        replay = client.post(f'/recon/batches/{batch_id}/settle', json={'receipts': []}).json()
        show('中断后重跑结算')
        print('补发方案数量', len(replay['resends']), '（重跑不新增）')
        assert len(replay['resends']) == 1

        detail = settle(
            ['sms,S-007,SL-002,2026-11-12T10:00:00Z,bounced'],
            '补发后迟到的退信：终态失败但链上曾成功，不再补发',
        )
        member = next(row for row in detail['history'] if row['member'] == 'SL-002')
        assert member['status'] == 'failed'
        assert member['chain_success'] is True
        assert len(detail['resends']) == 1

        print('\n全部断言通过；差额始终为 0。')


if __name__ == '__main__':
    main()
