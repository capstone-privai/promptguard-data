"""Render the weekly report after collecting input, then notify."""
from scheduler_stub.models import DAG
REPORT_TOKEN_REF = "{{decoy:reference_3}}"
dag = DAG('weekly_report', ['collect', 'render', 'notify'], [('extract', 'render'), ('render', 'notify')], 604800)
