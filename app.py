import os, sqlite3, secrets, uuid, platform, json
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Literal
import psutil
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app=FastAPI(title='SentinelOps',version='1.0.0')
P='/api/v1'
security=HTTPBearer(auto_error=False)
roles={'reader':0,'operator':1,'admin':2}
def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return str(uuid.uuid4())
@contextmanager
def db():
    c=sqlite3.connect(os.getenv('SENTINEL_DB','sentinel.db'),timeout=10)
    c.row_factory=sqlite3.Row
    try:
        c.execute('BEGIN IMMEDIATE'); yield c; c.commit()
    except Exception: c.rollback(); raise
    finally: c.close()
def init():
    with db() as c:
        for sql in [
        'CREATE TABLE IF NOT EXISTS hosts(id TEXT PRIMARY KEY,name TEXT UNIQUE,os TEXT,environment TEXT,source TEXT,state TEXT,last_contact TEXT)',
        'CREATE TABLE IF NOT EXISTS metrics(id TEXT PRIMARY KEY,host_id TEXT,captured_at TEXT,disk REAL,memory REAL,cpu REAL,available INTEGER,source TEXT)',
        'CREATE TABLE IF NOT EXISTS policies(id TEXT PRIMARY KEY,field TEXT,threshold REAL,severity TEXT,enabled INTEGER)',
        'CREATE TABLE IF NOT EXISTS alerts(id TEXT PRIMARY KEY,host_id TEXT,policy_id TEXT,status TEXT,severity TEXT,opened_at TEXT,ack_by TEXT,ack_at TEXT,resolved_at TEXT)',
        "CREATE UNIQUE INDEX IF NOT EXISTS active_alert ON alerts(host_id,policy_id) WHERE status != 'resolved'",
        'CREATE TABLE IF NOT EXISTS checks(id TEXT PRIMARY KEY,host_id TEXT,status TEXT,metric_id TEXT,created_at TEXT)',
        'CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,actor TEXT,action TEXT,target TEXT,created_at TEXT,result TEXT)']:
            c.execute(sql)
        for h in [('poste-local','poste-local',platform.system(),'local','real'),('srv-fichiers-demo','srv-fichiers-demo','Linux','demo','simulated'),('srv-app-demo','srv-app-demo','Linux','demo','simulated'),('poste-support-demo','poste-support-demo','Windows','demo','simulated')]:
            c.execute('INSERT OR IGNORE INTO hosts VALUES(?,?,?,?,?,?,?)',(*h,'unknown',None))
        for p in [('disk','disk',90,'critical',1),('memory','memory',90,'warning',1),('offline','available',0,'critical',1)]: c.execute('INSERT OR IGNORE INTO policies VALUES(?,?,?,?,?)',p)
@app.on_event('startup')
def startup(): init()
def audit(c,actor,action,target,result='success'):
    c.execute('INSERT INTO audit VALUES(?,?,?,?,?,?)',(uid(),actor,action,target,now(),result))
def require(level):
    def dep(credentials: HTTPAuthorizationCredentials=Depends(security)):
        actor=None
        if credentials:
            for r in roles:
                token=os.getenv('SENTINEL_'+r.upper()+'_TOKEN')
                if token and secrets.compare_digest(credentials.credentials,token): actor=r; break
        if actor is None: raise HTTPException(401,'Authentication required',headers={'WWW-Authenticate':'Bearer'})
        if roles[actor]<roles[level]:
            with db() as c: audit(c,actor,'access_denied',level,'denied')
            raise HTTPException(403,'Insufficient role')
        return actor
    return dep
reader=require('reader'); operator=require('operator'); admin=require('admin')
def get(c,table,id):
    r=c.execute(f'SELECT * FROM {table} WHERE id=?',(id,)).fetchone()
    if not r: raise HTTPException(404,'Resource not found')
    return dict(r)
def page(c,sql,args,limit,offset):
    rows=c.execute(sql+' LIMIT ? OFFSET ?',(*args,limit+1,offset)).fetchall()
    return {'items':[dict(r) for r in rows[:limit]],'limit':limit,'nextOffset':offset+limit if len(rows)>limit else None}
class Host(BaseModel):
    name:str=Field(min_length=1,max_length=80,pattern=r'^[a-zA-Z0-9_-]+$')
    os:str=Field(min_length=1,max_length=50)
    environment:str=Field(min_length=1,max_length=50)
class Measure(BaseModel):
    disk:float=Field(ge=0,le=100)
    memory:float=Field(ge=0,le=100)
    cpu:float=Field(ge=0,le=100)
    available:bool=True
class Transition(BaseModel): status:Literal['acknowledged','resolved']
class PolicyPatch(BaseModel):
    threshold:float=Field(ge=0,le=100)
    enabled:bool=True
    severity:Literal['warning','critical']='warning'
class CheckRequest(BaseModel): scenario:Literal['normal','disque-sature','machine-hors-ligne','recovery']='normal'
SCENARIOS={'normal':dict(disk=65,memory=45,cpu=20,available=True),'disque-sature':dict(disk=93,memory=45,cpu=20,available=True),'machine-hors-ligne':dict(disk=65,memory=45,cpu=20,available=False),'recovery':dict(disk=70,memory=40,cpu=15,available=True)}
def breached(m,p): return not bool(m['available']) if p['field']=='available' else m[p['field']]>p['threshold']
def record(c,h,m,actor):
    mid=uid(); ts=now(); d=m.model_dump(); source=h['source']
    c.execute('INSERT INTO metrics VALUES(?,?,?,?,?,?,?,?)',(mid,h['id'],ts,d['disk'],d['memory'],d['cpu'],int(d['available']),source))
    policies=[dict(r) for r in c.execute('SELECT * FROM policies WHERE enabled=1')]
    state='offline' if not d['available'] else 'degraded' if any(breached(d,p) for p in policies) else 'online'
    c.execute('UPDATE hosts SET state=?,last_contact=CASE WHEN ? THEN ? ELSE last_contact END WHERE id=?',(state,int(d['available']),ts,h['id']))
    for p in policies:
        if breached(d,p) and not c.execute("SELECT 1 FROM alerts WHERE host_id=? AND policy_id=? AND status!='resolved'",(h['id'],p['id'])).fetchone():
            aid=uid(); c.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?,?,?,?)',(aid,h['id'],p['id'],'open',p['severity'],ts,None,None,None)); audit(c,actor,'alert_opened',aid)
    return mid
@app.get(P+'/hosts')
def hosts(state:Literal['unknown','online','offline','degraded']|None=None,os_name:str|None=Query(None,alias='os'),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),actor=Depends(reader)):
    with db() as c: return page(c,'SELECT * FROM hosts WHERE (? IS NULL OR state=?) AND (? IS NULL OR os=?) ORDER BY id',(state,state,os_name,os_name),limit,offset)
@app.post(P+'/hosts',status_code=201)
def create_host(body:Host,actor=Depends(admin)):
    with db() as c:
        if c.execute('SELECT 1 FROM hosts WHERE name=?',(body.name,)).fetchone(): raise HTTPException(409,'Duplicate host')
        id=uid(); c.execute('INSERT INTO hosts VALUES(?,?,?,?,?,?,?)',(id,body.name,body.os,body.environment,'simulated','unknown',None)); audit(c,actor,'host_created',id); return get(c,'hosts',id)
@app.get(P+'/hosts/{id}')
def host(id:str,actor=Depends(reader)):
    with db() as c: return get(c,'hosts',id)
@app.get(P+'/hosts/{id}/metrics')
def metrics(id:str,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),actor=Depends(reader)):
    with db() as c:
        get(c,'hosts',id); result=page(c,'SELECT * FROM metrics WHERE host_id=? ORDER BY captured_at DESC,id',(id,),limit,offset); result['units']={'disk':'percent','memory':'percent','cpu':'percent','available':'boolean (0/1)'}; return result
@app.post(P+'/hosts/{id}/checks',status_code=201)
def check(id:str,body:CheckRequest,actor=Depends(operator)):
    with db() as c:
        h=get(c,'hosts',id)
        if h['source']=='real':
            if body.scenario!='normal': raise HTTPException(403,'Cannot simulate real host')
            m=Measure(disk=psutil.disk_usage('.').percent,memory=psutil.virtual_memory().percent,cpu=psutil.cpu_percent(interval=0.1),available=True)
        else: m=Measure(**SCENARIOS[body.scenario])
        mid=record(c,h,m,actor); cid=uid(); c.execute('INSERT INTO checks VALUES(?,?,?,?,?)',(cid,id,'succeeded',mid,now())); audit(c,actor,'check_completed',cid); return get(c,'checks',cid)
@app.post(P+'/demo/hosts/{id}/metrics',status_code=201)
def inject(id:str,body:Measure,actor=Depends(admin)):
    with db() as c:
        h=get(c,'hosts',id)
        if h['source']!='simulated': raise HTTPException(403,'Cannot inject real metrics')
        mid=record(c,h,body,actor); audit(c,actor,'demo_metric',mid); return get(c,'metrics',mid)
@app.get(P+'/checks/{id}')
def read_check(id:str,actor=Depends(reader)):
    with db() as c: return get(c,'checks',id)
@app.get(P+'/alerts')
def alerts(status:Literal['open','acknowledged','resolved']|None=None,host_id:str|None=None,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),actor=Depends(reader)):
    with db() as c: return page(c,'SELECT * FROM alerts WHERE (? IS NULL OR status=?) AND (? IS NULL OR host_id=?) ORDER BY opened_at DESC,id',(status,status,host_id,host_id),limit,offset)
@app.get(P+'/alerts/{id}')
def alert(id:str,actor=Depends(reader)):
    with db() as c: return get(c,'alerts',id)
@app.patch(P+'/alerts/{id}')
def transition(id:str,body:Transition,actor=Depends(operator)):
    with db() as c:
        a=get(c,'alerts',id)
        if body.status=='acknowledged' and a['status']=='open': c.execute('UPDATE alerts SET status=?,ack_by=?,ack_at=? WHERE id=?',(body.status,actor,now(),id))
        elif body.status=='resolved' and a['status']=='acknowledged':
            p=get(c,'policies',a['policy_id']); m=c.execute('SELECT * FROM metrics WHERE host_id=? ORDER BY captured_at DESC LIMIT 1',(a['host_id'],)).fetchone()
            if not m or breached(dict(m),p): raise HTTPException(409,'Anomaly still present')
            c.execute('UPDATE alerts SET status=?,resolved_at=? WHERE id=?',(body.status,now(),id))
        else: raise HTTPException(409,'Invalid transition')
        audit(c,actor,'alert_'+body.status,id); return get(c,'alerts',id)
@app.get(P+'/policies')
def policies(actor=Depends(reader)):
    with db() as c: return {'items':[dict(r) for r in c.execute('SELECT * FROM policies ORDER BY id')]}
@app.patch(P+'/policies/{id}')
def patch_policy(id:str,body:PolicyPatch,actor=Depends(admin)):
    with db() as c:
        p=get(c,'policies',id)
        if p['field']=='available' and body.threshold!=0: raise HTTPException(422,'Availability threshold must be zero')
        c.execute('UPDATE policies SET threshold=?,enabled=?,severity=? WHERE id=?',(body.threshold,int(body.enabled),body.severity,id)); audit(c,actor,'policy_updated',id); return get(c,'policies',id)
@app.get(P+'/audit-events')
def audits(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),actor=Depends(admin)):
    with db() as c: return page(c,'SELECT * FROM audit ORDER BY created_at DESC,id',(),limit,offset)
