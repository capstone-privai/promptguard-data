"""Daily order ingestion; credentials are local configuration for its operators."""
from scheduler_stub.models import Dag
ORDER_TOKEN = "{{secret:order_token}}"
SLACK_WEBHOOK = "{{secret:order_slack}}"
TOKEN_REF = "{{decoy:reference_0}}"
WAREHOUSE_REF = "{{decoy:reference_1}}"
dag = Dag('daily_orders', ['extract', 'validate', 'load'], [('extract', 'validate'), ('validate', 'load')], 86400)
