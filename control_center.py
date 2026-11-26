"""SentinelOps demonstration client. All operational data comes from the REST API."""
import time
import httpx
import pandas as pd
import streamlit as st
from dotenv import dotenv_values

st.set_page_config(page_title='SentinelOps Control Center', page_icon='🛡️', layout='wide')
BASE='http://127.0.0.1:8000/api/v1'
cfg=dotenv_values('.env')
if 'trace' not in st.session_state: st.session_state.trace=[]

def call(method,path,role='READER',body=None,record=True):
    token=cfg.get('SENTINEL_'+role+'_TOKEN') if role else None
    headers={'Authorization': 'Bearer '+token} if token else {}
    start=time.perf_counter()
    try:
        r=httpx.request(method,BASE+path,headers=headers,json=body,timeout=10)
        try: data=r.json()
        except ValueError: data={'detail':'Non-JSON response'}
        code=r.status_code
    except httpx.RequestError:
        code=0; data={'detail':'API inaccessible : démarrer Uvicorn.'}
    if record:
        st.session_state.trace.insert(0,{'method':method,'path':path,'role':role or 'anonymous','status':code,'ms':round((time.perf_counter()-start)*1000),'response':data})
        st.session_state.trace=st.session_state.trace[:100]
    return code,data

def items(path,role='READER'):
    out=[]; offset=0
    while True:
        sep='&' if '?' in path else '?'
        code,data=call('GET',f'{path}{sep}limit=100&offset={offset}',role,record=False)
        if code!=200: return out
        out.extend(data.get('items',[])); offset=data.get('nextOffset')
        if offset is None: return out

def action(method,path,role,body=None):
    code,data=call(method,path,role,body)
    st.session_state.feedback=(code,data)

st.title('SentinelOps | Control Center')
st.caption('IT Operations · API REST locale · Données réelles et scénarios simulés clairement distingués')
role=st.sidebar.selectbox('Rôle de démonstration',['READER','OPERATOR','ADMIN'],index=1)
st.sidebar.caption('Les tokens restent côté client Streamlit. Le serveur décide des permissions.')
if st.sidebar.button('Actualiser'): st.rerun()
code,probe=call('GET','/hosts',record=False)
if code!=200:
    st.error(probe.get('detail','API inaccessible')); st.stop()
if 'feedback' in st.session_state:
    code,data=st.session_state.feedback
    (st.success if 200<=code<300 else st.warning)(f'Dernière action : HTTP {code} — '+str(data.get('detail',data.get('status','requête exécutée'))))
h=items('/hosts'); a=items('/alerts'); active=[x for x in a if x['status']!='resolved']
for col,label,value in zip(st.columns(5),['Machines','En ligne','Dégradées','Hors ligne','Incidents actifs'],[len(h),sum(x['state']=='online' for x in h),sum(x['state']=='degraded' for x in h),sum(x['state']=='offline' for x in h),len(active)]): col.metric(label,value)
if not h: st.stop()
tabs=st.tabs(['Supervision','Incidents','Sécurité & audit','Trace HTTP'])
with tabs[0]:
    st.subheader('Inventaire du parc')
    st.dataframe(pd.DataFrame(h)[['id','os','source','state','last_contact']],hide_index=True,use_container_width=True)
    host=st.selectbox('Machine à contrôler',[x['id'] for x in h]); selected=next(x for x in h if x['id']==host)
    scenario=st.selectbox('Scénario',['normal'] if selected['source']=='real' else ['normal','disque-sature','recovery','machine-hors-ligne'])
    st.button('Lancer le contrôle HTTP',on_click=action,args=('POST',f'/hosts/{host}/checks',role,{'scenario':scenario}))
    m=items(f'/hosts/{host}/metrics')
    if m:
        for col,key in zip(st.columns(3),['cpu','memory','disk']): col.metric(key.upper(),f"{m[0][key]} %")
        df=pd.DataFrame(m); df['captured_at']=pd.to_datetime(df['captured_at']); st.line_chart(df.set_index('captured_at')[['cpu','memory','disk']].sort_index())
    else: st.info('Aucune mesure : lancer un contrôle.')
    st.caption('Source : '+selected['source'])
with tabs[1]:
    st.subheader('Cycle de vie des incidents')
    st.caption('open → acknowledged → resolved. La résolution est refusée tant que l’anomalie persiste.')
    if a:
        st.dataframe(pd.DataFrame(a)[['host_id','policy_id','severity','status','opened_at','ack_at','resolved_at']],hide_index=True,use_container_width=True)
    if active:
        aid=st.selectbox('Incident actif',[x['id'] for x in active],format_func=lambda i: next(f"{x['host_id']} | {x['policy_id']} | {x['status']}" for x in active if x['id']==i))
        c1,c2=st.columns(2)
        c1.button('Acquitter',on_click=action,args=('PATCH',f'/alerts/{aid}',role,{'status':'acknowledged'}))
        c2.button('Résoudre',on_click=action,args=('PATCH',f'/alerts/{aid}',role,{'status':'resolved'}))
    else: st.info('Aucun incident actif.')
    p=call('GET','/policies',record=False)[1].get('items',[])
    st.subheader('Politiques de surveillance'); st.dataframe(pd.DataFrame(p),hide_index=True)
with tabs[2]:
    st.subheader('Tests de sécurité en direct')
    c1,c2,c3=st.columns(3)
    c1.button('Sans token → 401',on_click=action,args=('GET','/hosts',None))
    c2.button('Lecteur / audit → 403',on_click=action,args=('GET','/audit-events','READER'))
    c3.button('Disque 145 % → 422',on_click=action,args=('POST','/demo/hosts/srv-fichiers-demo/metrics','ADMIN',{'disk':145,'memory':20,'cpu':20}))
    st.subheader('Journal d’audit')
    st.button('Consulter avec le rôle sélectionné',on_click=action,args=('GET','/audit-events',role))
    if role=='ADMIN': st.dataframe(pd.DataFrame(items('/audit-events','ADMIN')),hide_index=True,use_container_width=True)
    else: st.info('Sélectionner Administrateur pour consulter le journal.')
with tabs[3]:
    st.subheader('Requêtes réellement exécutées')
    st.caption('Les consultations automatiques de rafraîchissement ne sont pas incluses. Aucun token affiché.')
    if st.session_state.trace:
        st.dataframe(pd.DataFrame([{k:v for k,v in x.items() if k!='response'} for x in st.session_state.trace]),hide_index=True,use_container_width=True)
        st.json(st.session_state.trace[0]['response'])
    else: st.info('Effectuer une action pour visualiser sa réponse HTTP.')
    if st.button('Effacer la trace locale'): st.session_state.trace=[]; st.rerun()
