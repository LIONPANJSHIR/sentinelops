import streamlit as st
import pandas as pd
from analytics import load,kpis,detect
st.set_page_config(page_title='SentinelOps Analytics',layout='wide')
st.title('SentinelOps | IT Operations Analytics')
h,m,a=load(); source=st.sidebar.radio('Source',['real','simulated']); h=h[h.source==source]; m=m[m.source==source]; a=a[a.host_id.isin(h.id)]
for col,(key,value) in zip(st.columns(5),kpis(h,m,a).items()): col.metric(key,round(value,2) if pd.notna(value) else 'N/A')
st.caption('Disponibilité observée = proportion de contrôles disponibles, pas disponibilité temporelle réelle.')
if not m.empty:
    host=st.selectbox('Machine',m.host_id.unique()); series=m[m.host_id==host].copy(); series['captured_at']=pd.to_datetime(series.captured_at); st.line_chart(series.set_index('captured_at')[['disk','memory','cpu']].sort_index())
st.subheader('Incidents'); st.dataframe(a)
st.subheader('Détection exploratoire ML'); result=detect(m)
if result.empty: st.info('Au moins 30 mesures par machine nécessaires pour cette démonstration exploratoire.')
else: st.dataframe(result[result.anomaly])
