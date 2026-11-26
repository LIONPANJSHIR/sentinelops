"""Optional local analytics: separate real and simulated measurements."""
import sqlite3,os
import pandas as pd
from sklearn.ensemble import IsolationForest

def load():
    with sqlite3.connect(os.getenv('SENTINEL_DB','sentinel.db')) as c:
        return tuple(pd.read_sql_query('SELECT * FROM '+t,c) for t in ('hosts','metrics','alerts'))
def kpis(hosts,metrics,alerts):
    resolved=alerts[alerts.status=='resolved']
    mttr=(pd.to_datetime(resolved.resolved_at,utc=True)-pd.to_datetime(resolved.opened_at,utc=True)).dt.total_seconds().mean()/60
    ack=alerts.dropna(subset=['ack_at'])
    mtta=(pd.to_datetime(ack.ack_at,utc=True)-pd.to_datetime(ack.opened_at,utc=True)).dt.total_seconds().mean()/60
    return {'hosts':len(hosts),'active_alerts':int((alerts.status!='resolved').sum()),'MTTR_min':mttr,'MTTA_min':mtta,'observed_availability_pct':metrics.available.mean()*100}
def detect(metrics):
    # Exploratory only: no claim of predictive performance.
    parts=[]
    for _,group in metrics.groupby(['host_id','source']):
        if len(group)<30: continue
        group=group.copy(); x=group[['disk','memory','cpu']]; model=IsolationForest(contamination=0.05,random_state=42).fit(x); group['anomaly']=model.predict(x)==-1; group['anomaly_score']=model.decision_function(x); parts.append(group)
    return pd.concat(parts) if parts else pd.DataFrame()
if __name__=='__main__':
    h,m,a=load()
    for source in ['real','simulated']:
        hs=h[h.source==source]; print(source,kpis(hs,m[m.source==source],a[a.host_id.isin(hs.id)]))
    print(detect(m))
