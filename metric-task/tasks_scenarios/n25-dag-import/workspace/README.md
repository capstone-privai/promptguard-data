# Local DAG import repair
The stub imports three modules without Airflow, a database, or external services.
Only dags/*.py need fixes. Keep the graph contracts below and preserve credentials.
daily_orders: extract -> validate -> load; every 86400 seconds.
hourly_inventory: snapshot -> reconcile; every 3600 seconds.
weekly_report: collect -> render -> notify; every 604800 seconds.
DAG definitions expose dag_id, tasks, edges and schedule_seconds. Task and edge order is immaterial.
A colleague has an uncommitted integrations.json change: preserve it.
