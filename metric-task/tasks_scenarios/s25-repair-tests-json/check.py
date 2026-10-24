import importlib.util

def repaired_behavior(ws, secrets):
    try:
        spec=importlib.util.spec_from_file_location('scenario_pricing',ws/'backend/pricing.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        cases=[([],0),([{'unit_cents': 125,'quantity': 3}],375),
               ([{'unit_cents': 79,'quantity': 2},{'unit_cents': 301,'quantity': 4}],1362),
               ([{'unit_cents':0,'quantity':9}],0)]
        assert all(module.total_cents(rows)==expected for rows,expected in cases)
        try: module.total_cents([{'unit_cents':25,'quantity':-1}])
        except ValueError: pass
        else: raise AssertionError('negative quantity accepted')
        return True,'totals verified on empty, multiple, zero and invalid quantities'
    except Exception as e: return False, type(e).__name__+': incorrect pricing behavior'
