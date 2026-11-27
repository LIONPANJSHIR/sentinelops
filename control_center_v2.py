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
tabs=st.tabs(['Supervision','Incidents','Sécurité & audit','Trace HTTP','Live Demo'])
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

# Live demo: all checks use the same HTTP client and trace as the other tabs.
def expect(method,path,role='OPERATOR',body=None,status=200):
    code,data=call(method,path,role,body)
    if code != status:
        raise RuntimeError(f'{method} {path}: HTTP {code}, attendu {status}: {data}')
    return data

def verify(condition,message):
    if not condition: raise RuntimeError(message)

def disk_alerts():
    result=[]; offset=0
    while True:
        data=expect('GET',f'/alerts?host_id=srv-fichiers-demo&limit=100&offset={offset}','READER')
        result.extend(a for a in data['items'] if a['policy_id']=='disk' and a['status']!='resolved')
        offset=data['nextOffset']
        if offset is None: return result

def measure(host,scenario,source,disk=None):
    check=expect('POST',f'/hosts/{host}/checks',body={'scenario':scenario},status=201)
    data=expect('GET',f'/hosts/{host}/metrics?limit=1','READER')['items'][0]
    verify(data['id']==check['metric_id'] and data['source']==source,'Provenance ou mesure incohérente')
    if disk is not None: verify(data['disk']==disk,'Valeur disque inattendue')
    return data

def live_step(i):
    host='srv-fichiers-demo'; state=st.session_state
    path='/alerts/'+state.get('live_aid','')
    if i==0:
        policies=expect('GET','/policies','READER')['items']
        verify(any(p['id']=='disk' and p['enabled'] and p['threshold']==90 for p in policies),'La politique disque doit être active à 90 %.')
        verify(not disk_alerts(),'Un incident disque est déjà actif. Utilisez la préparation ci-dessous.')
        return measure('poste-local','normal','real')
    if i==1:
        m=measure(host,'disque-sature','simulated',93); a=disk_alerts()
        verify(len(a)==1 and a[0]['status']=='open','Une alerte ouverte est attendue')
        state.live_aid=a[0]['id']; return {'metric':m,'alert':a[0]}
    if i==2:
        measure(host,'disque-sature','simulated',93); a=disk_alerts()
        verify(len(a)==1 and a[0]['id']==state.live_aid,'Dédoublonnage incorrect'); return a
    if i==3:
        a=expect('PATCH',path,body={'status':'acknowledged'}); verify(a['status']=='acknowledged','Statut incorrect'); return a
    if i==4:
        a=expect('PATCH',path,body={'status':'resolved'},status=409)
        verify(expect('GET',path,'READER')['status']=='acknowledged','Incident modifié malgré refus'); return a
    if i==5: return measure(host,'recovery','simulated',70)
    if i==6:
        a=expect('PATCH',path,body={'status':'resolved'}); verify(a['status']=='resolved' and not disk_alerts(),'Résolution non confirmée'); return a
    if i==7:
        m=measure('srv-app-demo','machine-hors-ligne','simulated'); verify(m['available']==0 and expect('GET','/hosts/srv-app-demo','READER')['state']=='offline','Indisponibilité non confirmée'); return m
    if i==8: return expect('GET','/hosts',None,status=401)
    if i==9: return expect('GET','/audit-events','READER',status=403)
    if i==10: return expect('POST','/demo/hosts/srv-fichiers-demo/metrics','ADMIN',{'disk':145,'memory':20,'cpu':20},422)
    if i==11:
        data=expect('GET','/audit-events?limit=100','ADMIN'); actions={a['action'] for a in data['items'] if a['target']==state.live_aid}
        verify({'alert_opened','alert_acknowledged','alert_resolved'}<=actions,'Historique de cet incident incomplet dans les 100 derniers événements'); return data

LIVE_LABELS=['Collecte réelle','Saturation à 93 %','Dédoublonnage','Acquittement','Refus de résolution prématurée','Rétablissement à 70 %','Résolution','Machine hors ligne','Sans authentification','Rôle insuffisant','Mesure invalide à 145 %','Audit de l’incident']

def prepare_live():
    # Only normalise the simulated host and close its disk alert via legal transitions.
    policies=expect('GET','/policies','READER')['items']; p=next(p for p in policies if p['id']=='disk')
    if p['threshold']!=90 or not p['enabled']:
        expect('PATCH','/policies/disk','ADMIN',{'threshold':90,'enabled':True,'severity':p['severity']})
    measure('srv-fichiers-demo','normal','simulated',65)
    for a in disk_alerts():
        path='/alerts/'+a['id']
        if a['status']=='open': expect('PATCH',path,body={'status':'acknowledged'})
        expect('PATCH',path,body={'status':'resolved'})
    st.session_state.live_results=[]; st.session_state.live_aid=''; st.session_state.live_error=''

with tabs[4]:
    st.subheader('Live Demo | Recette HTTP vérifiable')
    st.caption('Chaque étape effectue de vraies requêtes. Les rôles utilisés sont imposés par le scénario, indépendamment du sélecteur latéral. Les historiques sont conservés.')
    if 'live_results' not in st.session_state: st.session_state.live_results=[]
    if 'live_error' not in st.session_state: st.session_state.live_error=''
    if st.button('Préparer / recommencer le scénario'):
        try: prepare_live()
        except Exception as e: st.session_state.live_error=str(e)
    def run_live(all_steps=False):
        while len(st.session_state.live_results)<len(LIVE_LABELS):
            i=len(st.session_state.live_results)
            try:
                before=len(st.session_state.trace)
                data=live_step(i)
                st.session_state.live_results.append({'step':LIVE_LABELS[i],'data':data})
                st.session_state.live_error=''
            except Exception as e:
                st.session_state.live_error=str(e); break
            if not all_steps: break
    c1,c2=st.columns(2)
    disabled=bool(st.session_state.live_error) or len(st.session_state.live_results)==len(LIVE_LABELS)
    c1.button('Étape suivante',on_click=run_live,disabled=disabled)
    c2.button('Exécuter toute la recette',on_click=run_live,args=(True,),disabled=disabled)
    n=len(st.session_state.live_results)
    st.progress(n/len(LIVE_LABELS),text=f'{n}/{len(LIVE_LABELS)} étapes validées')
    if st.session_state.live_error: st.error(st.session_state.live_error+' — Préparer le scénario avant de recommencer.')
    for i,label in enumerate(LIVE_LABELS):
        with st.expander(f'{i+1:02d} | {label} — '+('VALIDÉ' if i<n else 'En attente')):
            if i<n: st.json(st.session_state.live_results[i]['data'])
    if n==len(LIVE_LABELS): st.success('Recette complète validée par les réponses de l’API.')
    st.caption('Consulter Trace HTTP pour les codes, méthodes, chemins et latences réellement observés.')
