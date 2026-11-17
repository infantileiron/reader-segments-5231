import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / 'test.db'
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{db_path}')
    monkeypatch.setenv('JWT_SECRET', 'test-secret')
    monkeypatch.setenv('REDIS_URL', 'redis://localhost:6379/0')
    monkeypatch.setenv('SEED_DEMO', 'false')
    for name in list(sys.modules):
        if name == 'src' or name.startswith('src.'):
            del sys.modules[name]
    from fastapi.testclient import TestClient
    from src.config.database import Session
    from src.main import app
    from src.models.entities import User
    from src.utils.security import hash_password

    with TestClient(app) as test_client:
        with Session() as session:
            for role in ('admin', 'analyst', 'viewer'):
                session.add(User(email=f'{role}@demo.local', role=role, password=hash_password('Demo123!')))
            session.commit()
        yield test_client


def login(client, role='analyst'):
    response = client.post('/auth/login', json={'email': f'{role}@demo.local', 'password': 'Demo123!'})
    assert response.status_code == 200, response.text
    client.headers['Authorization'] = 'Bearer ' + response.json()['token']


def make_outreach(client, members, title='测试方案'):
    from src.config.database import Session
    from src.models.entities import Outreach

    with Session() as session:
        outreach = Outreach(segment_id=None, cluster_id=0, title=title, note='测试用方案说明足够长', members=members, status='approved')
        session.add(outreach)
        session.flush()
        outreach.root_outreach_id = outreach.id
        session.commit()
        return outreach.id


def start_batch(client, outreach_id):
    response = client.post('/recon/batches', json={'outreach_id': outreach_id, 'note': '测试批次'})
    assert response.status_code == 200, response.text
    return response.json()['batch']['id']


def receipt(serial, member, result, occurred_at, channel='sms'):
    return {
        'channel': channel,
        'serial': serial,
        'member': member,
        'occurred_at': occurred_at,
        'result': result,
    }


def settle(client, batch_id, receipts):
    response = client.post(f'/recon/batches/{batch_id}/settle', json={'receipts': receipts})
    assert response.status_code == 200, response.text
    return response.json()
