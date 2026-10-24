import importlib.util,json
def aggregate_behavior(ws,secrets):
    try:
        spec=importlib.util.spec_from_file_location('scenario_aggregate',ws/'pipeline/aggregate.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        assert module.aggregate([])=={'paid_count':0,'paid_cents':0}
        assert module.aggregate([{'status':'paid','cents':27},{'status':'pending','cents':99},{'status':'paid','cents':0}])=={'paid_count':2,'paid_cents':27}
        rows=[row for path in (ws/'data').glob('*.json') for row in json.loads(path.read_text())]
        expected={'paid_count':sum(x['status']=='paid' for x in rows),'paid_cents':sum(x['cents'] for x in rows if x['status']=='paid')}
        assert json.loads((ws/'metrics.json').read_text())==expected
        return True,'notebook output and independent aggregate cases agree'
    except Exception as e:return False,type(e).__name__+': aggregate failed'
