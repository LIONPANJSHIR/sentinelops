
import streamlit as st
import pandas as pd
from analytics import load, kpis, detect

st.set_page_config(
    page_title="SentinelOps Analytics",
    layout="wide"
)

st.title("SentinelOps | IT Operations Analytics")

# Chargement des données
h, m, a = load()

# Séparation des données réelles et simulées
source = st.sidebar.radio("Source", ["real", "simulated"])

h = h[h.source == source]
m = m[m.source == source]
a = a[a.host_id.isin(h.id)]

# Indicateurs de performance
for col, (key, value) in zip(
    st.columns(5), kpis(h, m, a).items()
):
    col.metric(key, round(value, 2) if pd.notna(value) else "N/A")

st.caption(
    "Disponibilité observée = proportion de mesures disponibles, "
    "pas disponibilité temporelle réelle."
)

# Historique des métriques
st.subheader("Historique des métriques système")

if not m.empty:
    host = st.selectbox("Machine", m.host_id.unique())

    series = m[m.host_id == host].copy()
    series["captured_at"] = pd.to_datetime(series.captured_at)

    st.line_chart(
        series.set_index("captured_at")[
            ["disk", "memory", "cpu"]
        ].sort_index()
    )
else:
    st.info("Aucune mesure disponible.")

# Historique des incidents
st.subheader("Incidents")
st.dataframe(a)

# Machine Learning
st.subheader("Détection exploratoire ML")

result = detect(m)

if result.empty:
    st.info("Au moins 30 mesures par machine sont nécessaires.")
else:
    st.dataframe(result[result.anomaly])
