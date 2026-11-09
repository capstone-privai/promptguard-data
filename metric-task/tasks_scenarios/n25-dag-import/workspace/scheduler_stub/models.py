"""Small offline Airflow-style graph model; no network or database driver."""
class DAG:
    def __init__(self, dag_id, tasks, edges, schedule_seconds):
        self.dag_id = dag_id
        self.tasks = list(tasks)
        self.edges = [tuple(edge) for edge in edges]
        self.schedule_seconds = schedule_seconds
        if len(set(self.tasks)) != len(self.tasks):
            raise ValueError('duplicate task id')
        if any(a not in self.tasks or b not in self.tasks for a, b in self.edges):
            raise ValueError('unknown dependency endpoint')
        remaining = set(self.tasks)
        while remaining:
            ready = {node for node in remaining if not any(b == node and a in remaining for a, b in self.edges)}
            if not ready:
                raise ValueError('cyclic graph')
            remaining -= ready
        if not isinstance(schedule_seconds, int) or schedule_seconds <= 0:
            raise ValueError('positive integer schedule required')
