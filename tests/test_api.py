import pytest
from fastapi.testclient import TestClient
from app import app, P
from concurrent.futures import ThreadPoolExecutor
@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('SENTINEL_DB',str(tmp_path/'test.db'))
    for role in ('reader','operator','admin'): monkeypatch.setenv('SENTINEL_'+role.upper()+'_TOKEN',role+'-test-secret')
    with TestClient(app) as c: yield c

def auth(role='operator'): return {'Authorization':'Bearer '+role+'-test-secret'}
def check(c,host='srv-fichiers-demo',scenario='disque-sature'): return c.post(P+'/hosts/'+host+'/checks',json={'scenario':scenario},headers=auth())
def test_real(client):
    assert check(client,'poste-local','normal').status_code==201
    r=client.get(P+'/hosts/poste-local/metrics',headers=auth('reader')).json()['items'][0]
    assert r['source']=='real' and 0<=r['disk']<=100
    assert check(client,'poste-local').status_code==403

def test_lifecycle(client):
    assert check(client).status_code==201
    assert check(client).status_code==201
    alerts=client.get(P+'/alerts',headers=auth()).json()['items']; assert len(alerts)==1
    url=P+'/alerts/'+alerts[0]['id']
    assert client.patch(url,json={'status':'resolved'},headers=auth()).status_code==409
    assert client.patch(url,json={'status':'acknowledged'},headers=auth()).json()['status']=='acknowledged'
    assert client.patch(url,json={'status':'resolved'},headers=auth()).status_code==409
    assert check(client,scenario='recovery').status_code==201
    assert client.patch(url,json={'status':'resolved'},headers=auth()).json()['status']=='resolved'
    assert check(client).status_code==201
    assert len(client.get(P+'/alerts?status=open',headers=auth()).json()['items'])==1

def test_concurrent(client):
    with ThreadPoolExecutor(4) as pool: results=list(pool.map(lambda _:check(client).status_code,range(4)))
    assert results==[201]*4
    assert len(client.get(P+'/alerts',headers=auth()).json()['items'])==1

def test_permissions(client):
    assert client.get(P+'/hosts').status_code==401
    assert client.get(P+'/audit-events',headers=auth('reader')).status_code==403
    assert client.patch(P+'/policies/disk',json={'threshold':80},headers=auth()).status_code==403
    assert client.get(P+'/hosts/absent',headers=auth()).status_code==404
    assert client.get(P+'/hosts?limit=101',headers=auth()).status_code==422
    assert client.post(P+'/demo/hosts/poste-local/metrics',json={'disk':80,'cpu':5,'memory':5},headers=auth('admin')).status_code==403
    assert client.post(P+'/demo/hosts/srv-fichiers-demo/metrics',json={'disk':145,'cpu':5,'memory':5},headers=auth('admin')).status_code==422

def test_offline(client):
    assert check(client,'srv-app-demo','machine-hors-ligne').status_code==201
    assert client.get(P+'/hosts/srv-app-demo',headers=auth()).json()['state']=='offline'
    assert len(client.get(P+'/hosts?state=offline',headers=auth()).json()['items'])==1

def test_inventory_policy_audit(client):
    h={'name':'demo-new','os':'Linux','environment':'demo'}
    assert client.post(P+'/hosts',json=h,headers=auth('admin')).status_code==201
    assert client.post(P+'/hosts',json=h,headers=auth('admin')).status_code==409
    assert client.patch(P+'/policies/disk',json={'threshold':80,'severity':'critical'},headers=auth('admin')).status_code==200
    assert client.get(P+'/hosts?limit=2',headers=auth()).json()['nextOffset']==2
    assert len(client.get(P+'/audit-events',headers=auth('admin')).json()['items'])==2
