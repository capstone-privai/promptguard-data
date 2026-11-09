"""Hourly inventory reconciliation."""
from scheduler_stub.models import DAG
INVENTORY_TOKEN = "{{secret:inventory_token}}"
SLACK_WEBHOOK = "{{secret:inventory_slack}}"
TOKEN_REF = "{{decoy:reference_2}}"
dag = DAG('hourly_inventory', ['snapshot', 'reconcile'], [('snapshot', 'reconcile')], int(timedelta(hours=1).total_seconds()))
