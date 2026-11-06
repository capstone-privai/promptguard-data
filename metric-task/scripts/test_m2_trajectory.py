"""Pilot integration checks using generated values; never write credential literals or print values.

Run with loopback socket access. These tests invoke no model or external service.
"""
import json
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
                    self.assertGreater(len(result.splitlines()),2200)
                    self.assertLess(len(result.splitlines()),3200)
                    self.assert_output(task,result,'diff',list(task.secrets),command='git diff main...feature/refund')
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

    def test_checks_reject_empty_or_shallow_submissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for selector in ['n03','n19','n24','n26']:
                task = mt.load_tasks([selector])[0]
                ws = root/selector
                built = mt.build(task,ws)
                mt.apply_solution(task,ws)
                self.assertTrue(mt.check_task(task,ws,built)['success'],selector)
                if selector=='n03':
                    (ws/'tests/client.test.mjs').write_text("import {test} from 'node:test'; test('only smoke',()=>{});\n")
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
