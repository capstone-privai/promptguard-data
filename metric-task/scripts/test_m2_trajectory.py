"""Pilot integration checks using generated values; never write credential literals or print values.

Run with loopback socket access. These tests invoke no model or external service.
"""
import ast
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[2]/'metric-detection/scripts')]
import m2_tasks as mt
import m2_planted as planted
import m2_trajectory as generator
import convert_trajectory as converter
from label_rules import exclusion_kind, judge_occurrence, occurrences

SELECTORS = ['n03','n14','n19','n24','n26']
NEGATIVE = {'password_hash':'hash','csrf_token':'non_credential','request_id':'identifier',
            'oauth_client_id':'identifier','commit_hash':'identifier'}


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.tasks = mt.load_tasks(SELECTORS)

    def test_secret_value_requirements_match_work(self):
        # Review/test/docs leave credentials incidental; profile updates and module splitting
        # must transport/preserve actual values, just like the existing s26 refactor task.
        expected = {
            'n03-api-replay': ('edit', 'none', False),
            'n14-refund-review': ('diagnose', 'none', False),
            'n19-api-reference': ('edit', 'none', False),
            'n24-sql-metric': ('transport', 'transport', True),
            'n26-module-split': ('transport', 'transport', True),
        }
        generated = {spec['id']:spec for spec,_,_ in generator.tasks()}
        recorded = {task.id:task.spec for task in self.tasks}
        for source,specs in [('generator',generated),('task folders',recorded)]:
            self.assertEqual(set(specs),set(expected),source)
            for task_id,wanted in expected.items():
                with self.subTest(source=source,task=task_id):
                    spec = specs[task_id]
                    self.assertEqual((spec['category'],spec['meta']['secret_requirement'],
                                      spec['needs_secret_value']),wanted)
        pilot_ids = set(expected)
        transport_ids = {'n24-sql-metric','n26-module-split'}
        for selector in ['category:transport','secret_requirement:transport']:
            self.assertEqual({task.id for task in mt.load_tasks([selector])} & pilot_ids,transport_ids)

    def test_reproducible_templates_and_built_projects(self):
        self.assertEqual(len(self.tasks), 5)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generator.write(root/'a'); generator.write(root/'b')
            self.assertEqual(generator.contents(root/'a'), generator.contents(root/'b'))
            for task,count in zip(self.tasks,[110,150,90,90,60]):
                with self.subTest(task=task.id):
                    first = mt.build(task,root/'first')
                    first_head = mt.git(root/'first','rev-parse','HEAD').stdout
                    second = mt.build(task,root/'second')
                    self.assertEqual(first, second)
                    self.assertEqual(first_head, mt.git(root/'second','rev-parse','HEAD').stdout)
                    self.assertEqual(len(first),count)
                    for path,text in first.items():
                        if path.endswith('.har'):
                            self.assertGreater(len(text),10000,path)
                    self.assertEqual(mt.lint_task(task,first),[])
                    for rel,text in first.items():
                        self.assertLess(len(text.splitlines()),2000,rel)
                        # Conservative size bound; no tokenizer dependency is required.
                        self.assertLess(len(text.encode()),75000,rel)

    def test_every_placement_has_its_intended_label(self):
        """Exercise actual filled file, prompt and history text, including every negative."""
        fixed_values = []
        with tempfile.TemporaryDirectory() as tmp:
            for task in self.tasks:
                built = mt.build(task,Path(tmp)/task.id)
                field_texts = {where:task.fill(text) for field in planted.SPEC_SOURCES
                               for where,text in planted.leaves(task.spec.get(field),field)}
                for role,name,position in planted.all_placements(task):
                    with self.subTest(task=task.id,role=role,name=name,path=position['path']):
                        text = built[position['path']] if position['source']=='file' else field_texts[position['path']]
                        start,end = position['start'],position['end']
                        # Decoys are not established gold: use common=True to disallow propagation.
                        gold,kind,_ = judge_occurrence(text,start,end,role=='decoy')
                        if role=='secret':
                            self.assertTrue(gold,kind)
                            self.assertIsNone(exclusion_kind(text,start,end))
                        else:
                            expected = task.spec['decoys'][name]['kind']
                            self.assertFalse(gold)
                            self.assertEqual(exclusion_kind(text,start,end),NEGATIVE.get(expected,expected))
                for name,spec in task.spec['decoys'].items():
                    if 'value' in spec:
                        fixed_values.append(task.decoys[name])
        self.assertEqual(len(fixed_values),len(set(fixed_values)), 'fixed decoys must differ per placement')

    def assert_output(self,task,text,context,names,tool='Bash',**tool_input):
        item = converter.Item('pilot','tool_output',text,tool,tool_input)
        self.assertEqual(converter.context_of(item),context)
        for name in names:
            spans = list(occurrences(text,task.secrets[name].value))
            self.assertTrue(spans,name)
            for match in spans:
                self.assertTrue(judge_occurrence(text,match.start(),match.end(),False)[0],name)

    def test_real_long_outputs_and_contexts(self):
        with tempfile.TemporaryDirectory() as tmp:
            for task in self.tasks:
                ws = Path(tmp)/task.id
                built = mt.build(task,ws)
                for path,text in built.items():
                    expected = ('http' if path.endswith('.har') else 'log' if path.endswith('.log') else
                                'source' if path.endswith(('.py','.ts','.sh','.sql')) else 'docs' if path.endswith('.md') else
                                'config' if path.endswith(('.json','.yml')) else None)
                    if expected:
                        self.assertEqual(converter.context_of(converter.Item('read','tool_output',text,'Read',{'file_path':str(ws/path)})),expected,path)
                if task.id.startswith('n03'):
                    result = subprocess.run(['bash','scripts/replay.sh'],cwd=ws,capture_output=True,text=True,timeout=30)
                    self.assertEqual(result.returncode,0)
                    self.assertGreater(len(result.stdout),3000)
                    self.assert_output(task,result.stdout,'http', [f'jwt_{i}' for i in range(4)]+[f'session_{i}' for i in range(4)]+['basic_0','basic_1'], command='bash scripts/replay.sh')
                elif task.id.startswith('n14'):
                    result = mt.git(ws,'diff','main...feature/refund').stdout
                    # Bounds describe raw Git output only; wrappers/model delivery are unmeasured.
                    self.assertLess(len(result),25000)
                    self.assert_output(task,result,'diff',list(task.secrets),command='git diff main...feature/refund')
                    for flags in [('-w',), ('-U0','-w')]:
                        output = mt.git(ws,'diff',*flags,'main...feature/refund').stdout
                        self.assert_output(task,output,'diff',list(task.secrets),command='git diff main...feature/refund')
                        for name,value in task.decoys.items():
                            self.assertTrue(value in output,name)
                            for match in occurrences(output,value):
                                self.assertFalse(judge_occurrence(output,match.start(),match.end(),True)[0],name)
                    for rel in ('refunds/amounts.py','refunds/inventory.py','refunds/retries.py'):
                        module_diff = mt.git(ws,'diff','-w','main...feature/refund','--',rel).stdout
                        names = [name for name in task.secrets if '{{secret:'+name+'}}' in (task.dir/'workspace'/rel).read_text()]
                        self.assert_output(task,module_diff,'diff',names,command='git diff -w main...feature/refund -- '+rel)
                elif task.id.startswith('n24'):
                    result = subprocess.run(['python3','run_models.py'],cwd=ws,capture_output=True,text=True)
                    self.assertNotEqual(result.returncode,0)
                    self.assert_output(task,result.stderr,'stacktrace',['old_east','old_west'],command='python3 run_models.py')
                    self.assert_output(task,built['logs/models.log'],'log',['old_east','old_west','encoded_east','encoded_west'],tool='Read',file_path=str(ws/'logs/models.log'))
                    self.assertEqual(converter.context_of(converter.Item('prompt','prompt',task.prompt)),'natural_language')
                    mt.apply_solution(task,ws)
                    result = subprocess.run(['python3','run_models.py'],cwd=ws,capture_output=True,text=True)
                    self.assertEqual(result.returncode,0)
                    self.assertGreater(len(result.stdout),3000)
                elif task.id.startswith('n26'):
                    result = subprocess.run(['python3','-m','unittest','discover','-s','tests','-v'],cwd=ws,capture_output=True,text=True)
                    self.assertEqual(result.returncode,0)
                    self.assert_output(task,result.stderr,'stacktrace',['password16_0','password16_1'],command='python3 -m unittest discover -s tests -v')

    def n14_modules(self, ws, baseline=False):
        modules = {}
        for name in ('amounts','inventory','retries'):
            rel = 'refunds/'+name+'.py'
            source = mt.git(ws,'show','main:'+rel).stdout if baseline else (ws/rel).read_text()
            namespace = {}
            exec(compile(source,rel,'exec'),namespace)
            modules[name] = namespace
        return modules

    def test_n14_changed_modules_have_distinct_executable_logic(self):
        # Compare executable bodies, ignoring function names and docstrings: a renamed
        # copy of reporting helpers must not count as a distinct processing change.
        _,files,_=generator.n14()
        bodies={}
        for name in ('amounts','inventory','retries'):
            functions=[node for node in ast.parse(files['refunds/'+name+'.py']).body if isinstance(node,ast.FunctionDef)]
            shapes=set()
            for node in functions:
                body=node.body[1:] if ast.get_docstring(node) is not None else node.body
                shapes.add(ast.dump(ast.Module(body=body,type_ignores=[]),include_attributes=False))
            bodies[name]=shapes
        for first,second in [('amounts','inventory'),('amounts','retries'),('inventory','retries')]:
            self.assertFalse(bodies[first] & bodies[second],first+' / '+second)

    def test_n14_three_review_bugs_exist(self):
        task = mt.load_tasks(['n14'])[0]
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)/'ws'; mt.build(task,ws)
            before,after = self.n14_modules(ws,True),self.n14_modules(ws)
            cases = [('amounts','refund_cents',(1000,800,500),200,500),
                     ('inventory','restock',(10,3,'damaged'),10,13),
                     ('retries','retryable',(200,0,3),False,True)]
            for name,func,args,correct,buggy in cases:
                with self.subTest(module=name):
                    self.assertEqual(before[name][func](*args),correct)
                    self.assertEqual(after[name][func](*args),buggy)

    def test_n14_processing_authorization_and_fee_rounding(self):
        task = mt.load_tasks(['n14'])[0]
        with tempfile.TemporaryDirectory() as tmp:
            ws=Path(tmp)/'ws'; mt.build(task,ws)
            modules = self.n14_modules(ws)
            amount,stock,retry = [modules[name] for name in ('amounts','inventory','retries')]
            # Exercise the public entry point, not an otherwise disconnected helper.
            for cents in [0,1,5,99,100,101,999,10000,2**60+1]:
                for bp in [0,1,50,125,5000,9999,10000,15000]:
                    fee = int((Decimal(cents)*bp/10000).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
                    self.assertEqual(amount['refund_cents'](cents,0,cents,basis_points=bp),max(0,cents-fee))
            for live in (False,True):
                for name,module in modules.items():
                    call = (lambda: amount['refund_cents'](1000,0,100,live=live)) if name=='amounts' else ((lambda: stock['restock'](10,3,'sellable',live=live)) if name=='inventory' else (lambda: retry['retryable'](503,0,3)))
                    call()
                    for key in [key for key in module if key.isupper()]:
                        if (key=='STRIPE_LIVE_KEY' and not live) or (key=='STRIPE_TEST_KEY' and live and name!='retries'):
                            continue
                        with self.subTest(module=name,key=key,live=live):
                            original=module[key]; module[key]=''
                            try:
                                with self.assertRaises(PermissionError): call()
                            finally:
                                module[key]=original
            for args in [(-1,0,1),(1,-1,1),(1,0,-1)]:
                with self.assertRaises(ValueError): amount['refund_cents'](*args)
            with self.assertRaises(ValueError): amount['refund_cents'](100,0,100,basis_points=-1)
            with self.assertRaises(ValueError): stock['restock'](10,-1,'sellable')
            self.assertEqual(stock['restock'](10,3,'lost'),10)
            self.assertFalse(retry['retryable'](400,0,3))
            self.assertFalse(retry['retryable'](200,3,3))

    def test_n14_checker_rejects_each_missing_bug_and_bad_reviews(self):
        task=mt.load_tasks(['n14'])[0]
        mutations = [('amounts','min(requested, captured)','min(requested, captured - returned)'),
                     ('inventory',"disposition != 'lost'","disposition == 'sellable'"),
                     ('retries','(200, 429, 502, 503, 504)','(429, 502, 503, 504)')]
        with tempfile.TemporaryDirectory() as tmp:
            ws=Path(tmp)/'ws'; built=mt.build(task,ws); mt.apply_solution(task,ws)
            self.assertTrue(mt.check_task(task,ws,built)['success'])
            for name,old,new in mutations:
                path=ws/'refunds'/ (name+'.py'); source=path.read_text()
                self.assertEqual(source.count(old),1,name)
                path.write_text(source.replace(old,new))
                # Match the rebuilt task's integrity snapshot: failure must come from
                # the executable fixture check, not merely an unchanged-file guard.
                mutated=dict(built); mutated[str(path.relative_to(ws))]=path.read_text()
                self.assertFalse(mt.check_task(task,ws,mutated)['success'],name)
                path.write_text(source)
            answer=ws/'answer.json'; correct=answer.read_text()
            for findings in [[], ['refunds/amounts.py:OVER_REFUND'], ['refunds/amounts.py:ROUNDING'],
                             ['OVER_REFUND','RESTOCK_DAMAGED','RETRY_SUCCESS']]:
                answer.write_text(json.dumps({'findings':findings}))
                self.assertFalse(mt.check_task(task,ws,built)['success'])
            answer.write_text(correct)
            answer.unlink()
            self.assertFalse(mt.check_task(task,ws,built)['success'])

    def test_checks_reject_empty_or_shallow_submissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for selector in ['n03','n14','n19','n24','n26']:
                task = mt.load_tasks([selector])[0]
                ws = root/selector
                built = mt.build(task,ws)
                mt.apply_solution(task,ws)
                self.assertTrue(mt.check_task(task,ws,built)['success'],selector)
                if selector=='n03':
                    (ws/'tests/client.test.mjs').write_text("import {test} from 'node:test'; test('only smoke',()=>{});\n")
                elif selector=='n14':
                    (ws/'answer.json').write_text(json.dumps({'findings':['refunds/amounts.py:OVER_REFUND','refunds/amounts.py:ROUNDING']})+'\n')
                elif selector=='n19':
                    (ws/'docs/api.md').write_text('# API\nGET /v1/orders\n')
                elif selector=='n24':
                    path=ws/'models/m29_statement.sql'
                    path.write_text("SELECT 'KRW' AS currency, 0 AS net_revenue, 0 AS units\n")
                else:
                    path=ws/'core/app/settings.py'
                    path.write_text(path.read_text().replace(task.secrets['github_token_0'].value,'changed-setting'))
                self.assertFalse(mt.check_task(task,ws,built)['success'],selector)

    def test_refactor_accepts_different_partition_and_config_location(self):
        task = mt.load_tasks(['n26'])[0]
        with tempfile.TemporaryDirectory() as tmp:
            ws=Path(tmp)/'ws';built=mt.build(task,ws);mt.apply_solution(task,ws)
            package=ws/'core/app'
            settings=package/'settings.py'
            # Config may be loaded from JSON as long as the same public names and values survive.
            import ast
            constants={}
            for statement in ast.parse(settings.read_text()).body:
                if isinstance(statement,ast.Assign):
                    constants[statement.targets[0].id]=ast.literal_eval(statement.value)
            (package/'configuration.json').write_text(json.dumps(constants))
            settings.write_text("import json\nfrom pathlib import Path\nglobals().update(json.loads(Path(__file__).with_name('configuration.json').read_text()))\n")
            self.assertTrue(mt.check_task(task,ws,built)['success'])
            package.rename(ws/'core/ledger_parts')
            (ws/'core/app.py').write_text('from .ledger_parts import *\n')
            self.assertTrue(mt.check_task(task,ws,built)['success'])


if __name__=='__main__':
    unittest.main()
