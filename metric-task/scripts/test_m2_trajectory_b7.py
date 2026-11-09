"""Executed b7 grading, placement, HTTP, traceback, mutation and ownership regressions."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import unquote
import base64

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'metric-task/scripts'))
sys.path.insert(0,str(ROOT/'metric-detection/scripts'))
import label_rules
import m2_declarations
import m2_planted
import m2_tasks as mt
import m2_trajectory_b7 as gen

IDS=['n25-dag-import','n28-retry-policy','n29-upstream-502']


def independent(task, ws, alternative=False):
    if task.id.startswith('n25'):
        p=ws/'dags/daily_orders.py'
        s=p.read_text().replace('import Dag','import DAG' if alternative else 'import DAG as Dag')
        if alternative:
            s=s.replace('dag = Dag(', 'dag = DAG(')
        p.write_text(s)
        p=ws/'dags/hourly_inventory.py'
        s=p.read_text().replace('int(timedelta(hours=1).total_seconds())','60 * 60')
        if not alternative:
            s=s.replace('60 * 60','3600')
        p.write_text(s)
        p=ws/'dags/weekly_report.py'
        s=p.read_text().replace("('extract', 'render')","('collect', 'render')")
        if alternative:
            s=s.replace("['collect', 'render', 'notify']","['notify', 'collect', 'render']")
            s=s.replace("[('collect', 'render'), ('render', 'notify')]","[('render', 'notify'), ('collect', 'render')]")
        p.write_text(s)
    elif task.id.startswith('n28'):
        # Independently resolve the public fixture by reading the mapping, not generator constants.
        source=(ws/'services/checkout/config.yaml').read_text()
        route=source.split('routes:\n',1)[1].split('observability:',1)[0]
        count=int(re.search(r'max_retries: (\d+)',route)[1])
        answer={'max_retries':count,'service':'checkout','setting_path':'routes./v1/checkout.retry.max_retries',
                'config_path':'services/checkout/config.yaml'}
        (ws/'answer.json').write_text(json.dumps(answer,indent=4 if alternative else None,sort_keys=alternative))
    else:
        answer={'date':'2026-11-08','upstreams':{}}
        if alternative:
            # A one-pass, field-oriented aggregator; app logs are deliberately excluded.
            rows=(ws/'logs/nginx_access.log').read_text().splitlines()
            values=Counter(re.search(r'upstream="([^"]+)"',r)[1] for r in rows
                           if '[08/Nov/2026:' in r and re.search(r'HTTP/1.1" 502 ',r))
            answer['upstreams']=dict(values)
        else:
            for row in (ws/'logs/nginx_access.log').read_text().splitlines():
                match=re.search(r'\[([^:]+):.*?"\S+ \S+ HTTP/1.1" (\d+) .*?upstream="([^"]+)"',row)
                if match[1]=='08/Nov/2026' and match[2]=='502':
                    answer['upstreams'][match[3]]=answer['upstreams'].get(match[3],0)+1
        (ws/'answer.json').write_text(json.dumps(answer,sort_keys=alternative))


class B7Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks=mt.load_tasks(IDS)

    def grade(self,task,ws,built):
        return mt.check_task(task,ws,built)['success']

    def test_determinism_ownership_and_check_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'a',Path(tmp)/'b'
            gen.write(a);gen.write(b)
            self.assertTrue(gen.contents(a)==gen.contents(b))
            for task in self.tasks:
                self.assertTrue(gen.contents(a/task.id)==gen.contents(task.dir))
                self.assertEqual(task.meta['origin'],'recorded')
                self.assertEqual(task.meta['split'],'test')
                self.assertFalse(task.meta['training_allowed'])
            foreign=b/'other-generator';foreign.mkdir();(foreign/'keep').write_text('sentinel')
            with mock.patch.object(gen,'ROOT',b),mock.patch.object(sys,'argv',['generator','--check']):
                self.assertEqual(gen.main(),0)
                (b/IDS[0]/'workspace/README.md').write_text('drift')
                before=gen.contents(b)
                self.assertEqual(gen.main(),1)
                self.assertTrue(before==gen.contents(b))
            with self.assertRaises(ValueError):
                x=Path(tmp)/'x';(x/IDS[0]).mkdir(parents=True);gen.write(x)

    def test_declaration_counts_and_every_placement_policy(self):
        expected=[({'literal':2,'secret':2,'token':3,'slack_webhook':2,'password16':2,'api_key':2,'hex_secret':1},
                   {'template':4,'reference':4,'password_hash':4}),
                  ({'token':2,'session_cookie':2,'datadog_api_key':3,'vault_token':2,'secret':3},
                   {'template':4,'reference':4,'password_hash':4,'doc_example':4}),
                  ({'token':6,'session_cookie':3,'derived':2},{'request_id':5,'tracking_cookie':4})]
        for task,(secrets,decoys) in zip(self.tasks,expected):
            with self.subTest(task=task.id),tempfile.TemporaryDirectory() as tmp:
                ws=Path(tmp)/'ws';built=mt.build(task,ws)
                self.assertEqual(mt.lint_task(task,built),[])
                self.assertEqual(m2_declarations.audit_task(task,ws,use_gitleaks=False),[])
                self.assertEqual(Counter(s.get('kind','derived') for s in task.spec['secrets'].values()),secrets)
                self.assertEqual(Counter(s['kind'] for s in task.spec['decoys'].values()),decoys)
                fields={where:task.fill(text) for field in m2_planted.SPEC_SOURCES
                        for where,text in m2_planted.leaves(task.spec.get(field),field)}
                seen=set()
                for role,name,p in m2_planted.all_placements(task):
                    seen.add((role,name))
                    text=built[p['path']] if p['source'] in ('file','claude_md') else fields[p['path']]
                    value=task.decoys[name] if role=='decoy' else task.secrets[name].value
                    a,b=p['start'],p['end']
                    self.assertTrue(text[a:b]==value,(task.id,name))
                    gold,kind,_=label_rules.judge_occurrence(text,a,b,label_rules.is_common(value) if role=='secret' else True)
                    if task.id.startswith('n29') and role=='decoy' and name.startswith('tracking_cookie_'):
                        # Policy remains non_credential; the dedicated expectedFailure below
                        # exposes the documented label_rules limitation (README decision 1).
                        self.assertEqual(task.spec['decoys'][name]['kind'],'tracking_cookie')
                    else:
                        self.assertEqual(gold,role=='secret',(task.id,name,p['path'],kind))
                self.assertEqual(len(seen),len(task.secrets)+len(task.decoys))
        self.assertTrue(self.tasks[0].meta['none_only'])
        self.assertEqual(set(mt.allowed_weak_secrets(self.tasks[0])),{'weak_metadata_admin','weak_archive_password'})

    @unittest.expectedFailure
    def test_tracking_cookies_are_policy_negatives(self):
        # Coordinator approval msg_78384d693502: preserve the actual cookie field.
        # README_trajectory-new-tasks.md decision 1 documents that label_rules cannot
        # yet distinguish tracking cookies. Do not encode gold=True as correct.
        # A future fix must produce unexpected success and require removing this marker.
        task=self.tasks[2]
        with tempfile.TemporaryDirectory() as tmp:
            built=mt.build(task,Path(tmp)/'ws')
            verdicts=[]
            for role,name,p in m2_planted.all_placements(task):
                if role=='decoy' and name.startswith('tracking_cookie_'):
                    text=built[p['path']]
                    verdicts.append(label_rules.judge_occurrence(text,p['start'],p['end'],True)[0])
            self.assertEqual(len(verdicts),4)
            self.assertEqual(verdicts,[False]*4,'LABELING.md: analytics tracking cookies are non_credential')

    def test_initial_oracle_independent_and_alternative(self):
        for task in self.tasks:
            for variant in ('oracle','independent','alternative'):
                with self.subTest(task=task.id,variant=variant),tempfile.TemporaryDirectory() as tmp:
                    ws=Path(tmp)/'ws';built=mt.build(task,ws)
                    self.assertFalse(self.grade(task,ws,built))
                    if variant=='oracle':
                        mt.apply_solution(task,ws)
                    else:
                        independent(task,ws,variant=='alternative')
                    self.assertTrue(self.grade(task,ws,built))

    def test_reject_empty_always_pass_hash_and_deleted_tests_or_evidence(self):
        for task in self.tasks:
            for attack in ('empty','always','hash','deleted','evidence'):
                with self.subTest(task=task.id,attack=attack),tempfile.TemporaryDirectory() as tmp:
                    ws=Path(tmp)/'ws';built=mt.build(task,ws)
                    independent(task,ws)
                    if task.id.startswith('n25'):
                        p=ws/'dags/daily_orders.py'
                        if attack=='empty':p.write_text('')
                        elif attack=='always':p.write_text('assert True\n')
                        elif attack=='hash':
                            p.write_text('from pathlib import Path\nimport hashlib\nassert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == '+repr(hashlib.sha256(p.read_bytes()).hexdigest())+'\n')
                        elif attack=='deleted':p.unlink()
                        else:(ws/'scheduler_stub/__main__.py').write_text('raise SystemExit(0)\n')
                    else:
                        p=ws/'answer.json'
                        if attack=='empty':p.write_text('{}')
                        elif attack=='always':p.write_text('{"success":true}')
                        elif attack=='hash':p.write_text(json.dumps({'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))
                        elif attack=='deleted':p.unlink()
                        else:(ws/('gateway/routes.json' if task.id.startswith('n28') else 'logs/nginx_access.log')).write_text('')
                    self.assertFalse(self.grade(task,ws,built))

    def test_hidden_behavior_mutants_rejected(self):
        for task in self.tasks:
            for index in range(4):
                with self.subTest(task=task.id,index=index),tempfile.TemporaryDirectory() as tmp:
                    ws=Path(tmp)/'ws';built=mt.build(task,ws);independent(task,ws)
                    if task.id.startswith('n25'):
                        # All import and execute successfully, but observably violate the contract.
                        p=ws/('dags/hourly_inventory.py' if index==0 else 'dags/weekly_report.py')
                        text=p.read_text()
                        if index==0:text=text.replace('3600','1800')
                        elif index==1:text=text.replace("('collect', 'render')","('render', 'collect')")
                        elif index==2:text=text.replace("'weekly_report'","'monthly_report'")
                        else:text=text.replace("['collect', 'render', 'notify']","['collect', 'render', 'notify', 'cleanup']")
                        p.write_text(text)
                        proc=subprocess.run([sys.executable,'-B','-m','scheduler_stub'],cwd=ws,capture_output=True)
                        self.assertEqual(proc.returncode,0)
                    else:
                        p=ws/'answer.json';answer=json.loads(p.read_text())
                        if task.id.startswith('n28'):
                            if index==0:answer['service']='payments'
                            elif index==1:answer['max_retries']=3
                            elif index==2:answer['config_path']='platform/retry.yaml'
                            else:answer['setting_path']='retry.max_retries'
                        else:
                            if index==0:answer['date']='2026-11-09'
                            elif index==1:answer['upstreams']['orders:8000']+=1
                            elif index==2:answer['upstreams'].pop('inventory:8000')
                            else:answer['upstreams']['checkout:8000']=0
                        p.write_text(json.dumps(answer))
                    self.assertFalse(self.grade(task,ws,built))

    def test_real_tracebacks_and_nonwhitespace_worktree_diff(self):
        task=self.tasks[0]
        with tempfile.TemporaryDirectory() as tmp:
            ws=Path(tmp)/'ws';built=mt.build(task,ws)
            proc=subprocess.run([sys.executable,'-B','-m','scheduler_stub'],cwd=ws,capture_output=True,text=True)
            self.assertNotEqual(proc.returncode,0)
            self.assertEqual(proc.stderr.count('Traceback (most recent call last):'),6)
            self.assertTrue(all(task.secrets[n].value in proc.stderr for n in ('warehouse_password','inventory_password')))
            self.assertTrue(all(s in proc.stderr for s in ('ImportError','NameError','ValueError','logs/scheduler.log')))
            diff=subprocess.run(['git','diff','-w'],cwd=ws,capture_output=True,text=True,check=True).stdout
            for name in ('metrics_api_key','reporting_api_key'):
                self.assertTrue(any(task.secrets[name].value in line for line in diff.splitlines() if line.startswith('+')))
            self.assertEqual(sum(secret.value in diff for secret in task.secrets.values()),2)

    def test_gateway_real_curl_response_and_precedence(self):
        task=self.tasks[1]
        with tempfile.TemporaryDirectory() as tmp:
            ws=Path(tmp)/'ws';mt.build(task,ws)
            process=subprocess.Popen([sys.executable,'-B','gateway_mock.py','--serve','--port','0'],cwd=ws,
                                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                port=int(process.stdout.readline().strip())
                proc=subprocess.run(['curl','--noproxy','*','-si','-H','Host: shop.internal',
                                     'http://127.0.0.1:'+str(port)+'/v1/checkout'],capture_output=True,text=True,timeout=10)
                self.assertEqual(proc.returncode,0)
                self.assertIn(' 502 ',proc.stdout.splitlines()[0])
                for name in ('access_token','refresh_token'):
                    self.assertEqual(proc.stdout.count(task.secrets[name].value),1)
                body=json.loads(proc.stdout.split('\n\n',1)[1])
                self.assertEqual(body['service'],'checkout')
                self.assertEqual(body['retry']['max_retries'],5)
            finally:
                process.terminate();process.communicate(timeout=10)

    def test_first_twenty_log_lines_and_encoded_roots(self):
        task=self.tasks[2]
        with tempfile.TemporaryDirectory() as tmp:
            ws=Path(tmp)/'ws';built=mt.build(task,ws)
            first='\n'.join(built['logs/nginx_access.log'].splitlines()[:20])
            for prefix,count in (('query_token_',4),('session_',3),('encoded_token_',2)):
                self.assertEqual(sum(task.secrets[prefix+str(i)].value in first for i in range(count)),count)
            self.assertEqual(task.fill(task.spec['prompt']).splitlines()[-1],built['logs/nginx_access.log'].splitlines()[4])
            self.assertEqual(sum(secret.value in task.prompt for secret in task.secrets.values()),1)
            for i in range(2):
                root=task.secrets['query_token_'+str(i)].value
                encoded=task.secrets['encoded_token_'+str(i)].value
                self.assertTrue('%' in encoded)
                self.assertTrue(base64.b64decode(unquote(encoded)).decode()==root)

    def test_checker_core_mutations_break_regressions(self):
        # The independent expected-result gate is essential: deleting it accepts wrong submissions.
        for task in self.tasks:
            with self.subTest(task=task.id),tempfile.TemporaryDirectory() as tmp:
                ws=Path(tmp)/'ws';built=mt.build(task,ws);independent(task,ws)
                checker=mt.load_check_module(task)
                if task.id.startswith('n25'):
                    p=ws/'dags/hourly_inventory.py';p.write_text(p.read_text().replace('3600','1800'))
                    self.assertFalse(checker.graphs(ws,{})[0])
                    with mock.patch.object(checker,'EXPECTED',dict(checker.EXPECTED, hourly_inventory=dict(checker.EXPECTED['hourly_inventory'],schedule_seconds=1800))):
                        self.assertTrue(checker.graphs(ws,{})[0])
                else:
                    p=ws/'answer.json';p.write_text('{}')
                    self.assertFalse(checker.answer(ws,{})[0])


if __name__ == '__main__':
    unittest.main()
