# SentinelOps — Intelligent IT Monitoring & Incident Analytics

API REST locale de supervision, avec une machine réelle et trois cibles logiques simulées. Aucun accès distant, shell arbitraire ni privilège administrateur. Python 3.10+.

## Installation
Windows PowerShell:
```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_demo.py
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --env-file .env
```
macOS:
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python setup_demo.py
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000 --env-file .env
```
Ouvrir http://127.0.0.1:8000/docs ; Authorize avec le token du rôle choisi dans .env. Les secrets sont locaux et ne doivent jamais être commités. Les trois comptes de démonstration sont identifiés par leur rôle. API réservée à localhost.

## Recette
Dans un deuxième terminal, avec le même interpréteur virtuel, exécuter `python demo.py` sur une base de démonstration fraîche. Pour les tests indépendants : `python -m pytest -q`. Le script vérifie la collecte réelle, saturation répétée, acquittement, refus de résolution prématurée, retour à 70 %, résolution, indisponibilité, refus 401/403/422 et audit. Les tests utilisent une base temporaire. Pour recommencer la recette, arrêter le serveur et déplacer la base sentinel.db de démonstration, puis relancer.

## Conception
Six ressources : hosts, metrics, policies, alerts, checks, audit-events. Contrat interactif /docs et /openapi.json. Pagination offset/limit (1–100), tri déterministe, filtres par état/OS ou statut/host. Les contrôles sont synchrones (201 après création effective). Les mesures CPU, disque et mémoire sont en pourcentage ; available est 0/1. Le disque mesuré est celui du répertoire de travail. Un poste local dont le processus API répond est considéré disponible ; aucune mesure distante n'est revendiquée.

Le poste-local utilise psutil ; les trois cibles logiques sont srv-fichiers-demo, srv-app-demo et poste-support-demo. Les scénarios normal, disque-sature, machine-hors-ligne et recovery sont définis dans app.py. Un opérateur peut les déclencher uniquement sur des cibles simulées ; l'injection de valeurs personnalisées est réservée à l'administrateur. Les nouvelles machines créées sont toujours simulées. Les seuils sont strictement dépassés pour disque/mémoire ; disponibilité fausse déclenche une alerte. État inconnu avant collecte, offline si indisponible, degraded si règle active franchie, online sinon. Le dernier contact n'avance que lors d'un contrôle disponible.

Cycle : open → acknowledged → resolved (seulement après retour à une mesure conforme à la politique actuelle). La résolution est manuelle. Une règle active par machine ne peut produire qu'une alerte non résolue : index unique partiel et transactions BEGIN IMMEDIATE. Une nouvelle anomalie après résolution ouvre un nouvel incident. Toutes les mutations réussies sont auditées, ainsi que les refus de rôle. Aucun token n'est stocké dans l'audit. Les identifiants sont des UUID sauf les cibles et politiques initiales prédéfinies. Les lecteurs consultent, les opérateurs contrôlent et gèrent les alertes, les administrateurs enregistrent des cibles, modifient les politiques et consultent l'audit.

## Extensions facultatives
`python -m pip install -r requirements-analytics.txt`, puis `python analytics.py` ou `python -m streamlit run dashboard.py`. Le dashboard lit SQLite localement et sépare réel/simulé. MTTA et MTTR en minutes ; disponibilité observée par contrôle, pas SLA temporel. Isolation Forest exploratoire par machine/source à partir de 30 mesures, non validé comme modèle prédictif, sans effet sur les alertes obligatoires. Ne pas exposer le dashboard sur un réseau public.

## Limites et vérifications
Tests exécutés dans l'environnement Linux de développement, pas sur Windows/macOS. Les instructions de lancement pour ces deux OS sont fournies sans prétendre qu'elles ont été testées. Dashboard optionnel non testé en exécution si Streamlit absent. Authentification par tokens statiques de démonstration, pas un système d'identité de production. Pas de collecte périodique automatique : les contrôles sont déclenchés via API.
