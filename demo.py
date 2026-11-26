"""Reproducible HTTP acceptance scenario. Start server first; use a fresh demo DB."""
import httpx
from dotenv import dotenv_values
cfg=dotenv_values('.env'); base='http://127.0.0.1:8000/api/v1'
with httpx.Client(base_url=base,timeout=15) as c:
    def call(method,path,role='OPERATOR',expected=200,**kwargs):
        headers={'Authorization':'Bearer '+cfg['SENTINEL_'+role+'_TOKEN']} if role else {}
        r=c.request(method,path,headers=headers,**kwargs); assert r.status_code==expected,(r.status_code,r.text); print(method,path,r.status_code); return r.json()
    call('GET','/hosts','READER')
    call('POST','/hosts/poste-local/checks',expected=201,json={'scenario':'normal'})
    print(call('GET','/hosts/poste-local/metrics','READER'))
    for _ in range(2): call('POST','/hosts/srv-fichiers-demo/checks',expected=201,json={'scenario':'disque-sature'})
    alerts=call('GET','/alerts?host_id=srv-fichiers-demo&status=open')['items']; assert len(alerts)==1
    path='/alerts/'+alerts[0]['id']; call('PATCH',path,json={'status':'acknowledged'})
    call('PATCH',path,expected=409,json={'status':'resolved'})
    call('POST','/hosts/srv-fichiers-demo/checks',expected=201,json={'scenario':'recovery'})
    call('PATCH',path,json={'status':'resolved'})
    call('POST','/hosts/srv-app-demo/checks',expected=201,json={'scenario':'machine-hors-ligne'})
    call('GET','/hosts',None,401); call('GET','/audit-events','READER',403)
    call('POST','/demo/hosts/srv-fichiers-demo/metrics','ADMIN',422,json={'disk':145,'memory':20,'cpu':20})
    call('GET','/audit-events','ADMIN'); print('Acceptance scenario passed.')
