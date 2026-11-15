import json

def review(ws, secrets):
    try:
        value = json.loads((ws/'answer.json').read_text())
        entries = value['findings']
        pairs = [(row['address'], row['reason']) for row in entries]
        expected = {('aws_db_instance.orders', 'stateful_replacement'),
                    ('aws_autoscaling_group.api', 'zero_capacity'),
                    ('aws_lb_listener.https', 'listener_removed')}
        return len(pairs) == len(expected) and set(pairs) == expected, 'review findings compared as a set'
    except (OSError, ValueError, KeyError, TypeError):
        return False, 'answer.json requires findings with address and reason'
