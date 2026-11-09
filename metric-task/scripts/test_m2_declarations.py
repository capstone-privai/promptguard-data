"""Declaration auditor regressions. Values are generated locally, never provider literals."""
import base64
import copy
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True  # check_task loads each task's check.py in-process; keep task folders free of __pycache__ (generator --check compares every file)
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parent))
import m2_declarations as audit
import m2_tasks as mt


class DeclarationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value=mt.secretgen.make_secrets('declaration-regressions',{'credential':{'kind':'api_key'}})['credential'].value

    def fails(self,text,declared=()):
        self.assertTrue(audit.audit_text(text,set(declared),use_gitleaks=False))

    def test_credential_slots_independent_of_declared_secrets(self):
        v=self.value
        cases=[f'DB_PASSWORD="{v}"',f'DB_PASS="{v}"',f'api_key: "{v}"',
          f'postgresql://reader:{v}@db.internal:5432/app',f'Authorization: Bearer {v}',
          'Authorization: Basic '+base64.b64encode(('reader:'+v).encode()).decode(),
          f'AccountKey={v};EndpointSuffix=core.windows.net;',f'Cookie: session_id={v}; Path=/',f'Cookie: session={v}',f'Password={v};Database=relay;',
          f'curl --password "{v}"',f'redis-server --requirepass {v}',f'docker login registry.internal -u ci -p "{v}"',
          f'The password is "{v}"',f'비번은 `{v}`이야.',f'<password>{v}</password>']
        for text in cases:
            with self.subTest(text=text[:25]): self.fails(text)

    def test_overlapping_shell_references_stop_before_enclosing_quote(self):
        for reference in ('$AUDIT_REF', '${AUDIT_REF}'):
            for quote in ('"', "'"):
                text = 'curl -H ' + quote + 'PRIVATE-TOKEN: ' + reference + quote + ' https://audit.invalid/api\n'
                with self.subTest(reference=reference, quote=quote):
                    self.assertEqual(audit.audit_text(text, set(), use_gitleaks=False), [])
                    self.assertTrue(audit.candidates(text))
                    self.assertTrue(all(text[c.start:c.end] == reference for c in audit.candidates(text)))

    def test_bare_assignments_preserve_literal_quotes(self):
        for value in ("audit'BoundaryValue", 'audit"BoundaryValue', "auditBoundaryValue'"):
            text = 'PASSWORD=' + value + '\n'
            with self.subTest(length=len(value)):
                self.assertIn(value, [text[c.start:c.end] for c in audit.candidates(text)])
                self.assertEqual(audit.audit_text(text, {value}, use_gitleaks=False), [])

    def test_overlapping_nested_assignments_preserve_real_literals(self):
        harmless = 'auditBoundaryValue'
        cases = [
            ('curl -H "PRIVATE-TOKEN: ' + harmless + '" https://audit.invalid/api', harmless),
            ("curl -H 'PRIVATE-TOKEN: " + harmless + "' https://audit.invalid/api", harmless),
            ('- credential: `TOKEN=' + harmless + '`', harmless),
            ('config = {"api_key": "' + harmless + '"}', harmless),
            ('AUTH_SECRETS = ("' + harmless + '", "anotherHarmlessValue")', '("' + harmless + '"'),
        ]
        for index, (text, expected) in enumerate(cases):
            with self.subTest(case=index):
                self.assertTrue(audit.audit_text(text, set(), use_gitleaks=False))
                self.assertIn(expected, [text[c.start:c.end] for c in audit.candidates(text)])

    def test_provider_without_credential_slot(self):
        for kind in ['github_pat','gitlab_pat','slack_token','stripe_publishable','private_key']:
            value=mt.secretgen.make_secrets('declaration-regressions',{'credential':{'kind':kind}})['credential'].value
            self.fails('artifact:\n'+value)
            self.assertFalse(audit.audit_text('artifact:\n'+value,{value},use_gitleaks=False))

    def test_transformed_surfaces_must_be_declared(self):
        specs={'raw':{'kind':'password_json_unsafe'},'encoded':{'from':'raw','transforms':['json']}}
        values=mt.secretgen.make_secrets('declaration-regressions',specs)
        text='{"password":"'+values['encoded'].value+'"}'
        self.fails(text,{values['raw'].value})
        self.assertFalse(audit.audit_text(text,{s.value for s in values.values()},use_gitleaks=False))
        # Entity escapes and unicode escapes cannot hide behind label_rules.code.
        self.fails('<password>'+self.value+'&amp;part</password>',{self.value})
        self.fails('API_KEY="'+self.value+r'\u0026part"',{self.value})
        pem=mt.secretgen.make_secrets('declaration-regressions',{'raw':{'kind':'private_key'}})['raw'].value
        self.fails('PRIVATE_KEY='+json.dumps(pem),{pem})
        self.assertFalse(audit.audit_text('PRIVATE_KEY='+json.dumps(pem),{pem,json.dumps(pem)[1:-1]},use_gitleaks=False))

    def test_excluded_values_and_public_structure(self):
        text='\n'.join(['DB_PASSWORD="[REDACTED]"','DB_PASSWORD="${DB_PASSWORD}"','DB_PASSWORD="<your-password>"',
          'password_min_length=12','token_ttl_seconds=3600','max_tokens=4096','password_display="[REDACTED]"',
          'google_client_id="public-client-identifier"','request_id="abcdef1234567890"','API_KEY=process.env.KEY',
          'csrf_token="anti-forgery-value-57"','client_id="public-client-identifier"',
          'API_KEY="EXAMPLE-value"','API_KEY=""'])
        self.assertEqual(audit.audit_text(text,set(),use_gitleaks=False),[])

    def test_extensionless_history_metadata_and_session_surfaces(self):
        task=copy.deepcopy(mt.load_tasks(['s01'])[0])
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d)/'ws'; mt.build(task,ws)
            self.assertFalse(audit.audit_task(task,ws,use_gitleaks=False))
            (ws/'payload.opaque').write_text('API_KEY="'+self.value+'"\n')
            mt.git(ws,'add','payload.opaque'); mt.git(ws,'commit','-qm','rotation note',date=mt.GIT_DATE)
            (ws/'payload.opaque').unlink()
            mt.git(ws,'add','-A'); mt.git(ws,'commit','-qm','remove current credential',date=mt.GIT_DATE)
            errors=audit.audit_task(task,ws,use_gitleaks=False)
            self.assertTrue(any('git:' in e and 'payload.opaque' in e for e in errors))
            mt.git(ws,'commit','--allow-empty','-qm','API_KEY="'+self.value+'"',date=mt.GIT_DATE)
            mt.git(ws,'remote','add','origin','https://ci:'+self.value+'@git.internal/repo')
            task.spec.update(session_env={'EXTRA_API_KEY':self.value},append_system_prompt='API_KEY="'+self.value+'"')
            errors=audit.audit_task(task,ws,use_gitleaks=False)
            for surface in ['git:message:','git:config','spec:session_env:','spec:append_system_prompt:']:
                self.assertTrue(any(surface in e for e in errors),surface)

    def test_all_session_entrypoints(self):
        task=copy.deepcopy(mt.load_tasks(['s01'])[0]); value='API_KEY="'+self.value+'"'
        for field,content in [('prompt',value),('mcp_fixture',{'responses':{'x':value}}),
                              ('worktree_changes',{'new.opaque':value}),('setup',[['echo',value]]),
                              ('history',[{'message':value,'files':{'deleted':value}}]),('final_commit',{'message':value})]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as d:
                ws=Path(d)/'ws'; mt.build(task,ws); task.spec[field]=content
                self.assertTrue(any('spec:'+field+':' in e for e in audit.audit_task(task,ws,use_gitleaks=False)))
                task.spec.pop(field,None)
                if field=='prompt': task.spec['prompt']='Audit evidence'

    def test_short_and_common_declared_values_rejected(self):
        for value in ['abc123','password','12345678']:
            task=copy.deepcopy(mt.load_tasks(['s01'])[0]); task.secrets['db_password'].value=value
            with self.subTest(value=value),tempfile.TemporaryDirectory() as d:
                ws=Path(d)/'ws'; mt.build(task,ws)
                self.assertTrue(any('shorter than 8 or common' in e for e in audit.audit_task(task,ws,use_gitleaks=False)))

    def test_gitleaks_partial_overlap_does_not_hide_unknown(self):
        # A declared shorter candidate overlaps a scanner-discovered longer credential.
        # The longer finding must still fail; partial overlap cannot resolve it.
        text='API_KEY="'+self.value+'"suffix'
        row={'Secret':self.value+'"suffix','RuleID':'injected-regression'}
        proc=mock.Mock(returncode=0,stdout=json.dumps([row]))
        with mock.patch.object(audit.shutil,'which',return_value='/gitleaks'),mock.patch.object(audit.subprocess,'run',return_value=proc):
            self.assertTrue(audit.audit_text(text,{self.value}))

    def test_scenario_build_handles_binary_and_new_suffix(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); path=root/'templates'; (path/'workspace').mkdir(parents=True)
            task=copy.deepcopy(mt.load_tasks(['s01'])[0]); task.dir=path
            # Task.suite is inferred from its root, so patch the root just for this isolated build.
            (path/'workspace'/'image.json').write_bytes(b'\x89PNG\x00\xff')
            (path/'workspace'/'config.opaque').write_text('API_KEY={{secret:datadog}}\n')
            with mock.patch.object(mt,'SCENARIO_TASKS_DIR',root):
                built=mt.build(task,root/'ws')
                self.assertEqual((root/'ws/image.json').read_bytes(),b'\x89PNG\x00\xff')
                self.assertIn(task.secrets['datadog'].value,built['config.opaque'])
                self.assertTrue(mt.corrupt_with_placeholder(task,root/'ws',built))
                self.assertFalse(mt.integrity(task,root/'ws',built)[0])

    def test_literal_secret_validation(self):
        for bad_spec in [
            {'kind': 'literal', 'type': 'PASSWORD'},
            {'kind': 'literal', 'value': '', 'type': 'PASSWORD'},
            {'kind': 'literal', 'value': '   ', 'type': 'PASSWORD'},
            {'kind': 'literal', 'value': 12345, 'type': 'PASSWORD'},
            {'kind': 'literal', 'value': 'abc123'},
            {'kind': 'literal', 'value': 'abc123', 'type': 'UNKNOWN'},
            {'kind': 'password16', 'value': 'abc123'},
        ]:
            with self.subTest(spec=bad_spec), self.assertRaises(ValueError):
                mt.secretgen.make_secrets('literal-validation', {'cred': bad_spec})
        with self.assertRaises(ValueError):
            mt.secretgen.make_secrets('literal-validation', {
                'base': {'kind': 'literal', 'value': 'abc123', 'type': 'PASSWORD'},
                'derived': {'from': 'base', 'value': 'override'},
            })
        built = mt.secretgen.make_secrets('literal-validation', {
            'base': {'kind': 'literal', 'value': 'abc123', 'type': 'PASSWORD'},
            'b64': {'from': 'base', 'transforms': ['base64']},
        })
        self.assertEqual(built['base'].type, 'PASSWORD')
        self.assertEqual(built['b64'].root, 'base')

    def test_weak_secret_and_none_only_enforcement(self):
        base_task = copy.deepcopy(mt.load_tasks(['s01'])[0])
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d) / 'ws'
            built = mt.build(base_task, ws)
            # Marked weak without meta.none_only=True is rejected.
            t1 = copy.deepcopy(base_task)
            t1.spec['secrets']['db_password'] = {'kind': 'literal', 'value': 'abc123', 'type': 'PASSWORD', 'weak': True}
            t1.secrets['db_password'].value = 'abc123'
            self.assertTrue(any('none_only' in e for e in mt.lint_task(t1, built)))
            self.assertTrue(any('none_only' in e for e in audit.audit_task(t1, ws, use_gitleaks=False)))

            # meta.none_only=True without marking the specific weak secret is still rejected.
            t2 = copy.deepcopy(base_task)
            t2.spec['meta']['none_only'] = True
            t2.secrets['db_password'].value = 'abc123'
            self.assertTrue(any('< 8' in e for e in mt.lint_task(t2, built)))
            self.assertTrue(any('shorter than 8 or common' in e for e in audit.audit_task(t2, ws, use_gitleaks=False)))

            # Both meta.none_only=True and explicit weak designation on that secret are required.
            t3 = copy.deepcopy(t1)
            t3.spec['meta']['none_only'] = True
            t3.spec['secrets']['db_password']['weak'] = True
            t3.secrets['db_password'].value = 'abc123'
            t3.secrets = mt.secretgen.make_secrets(t3.id, t3.spec['secrets'])
            built = mt.build(t3, ws)
            self.assertEqual(mt.lint_task(t3, built), [])
            self.assertEqual(audit.audit_task(t3, ws, use_gitleaks=False), [])

            # Another unmarked secret on the same none_only task still fails if weak.
            t3.secrets['datadog'].value = 'password'
            self.assertTrue(any('datadog' in e for e in audit.audit_task(t3, ws, use_gitleaks=False)))

    def test_m2_none_only_precall_rejection(self):
        import argparse
        import m2
        normal_task = copy.deepcopy(mt.load_tasks(['s01'])[0])
        none_only_task = copy.deepcopy(normal_task)
        none_only_task.id = 'n00-none-only-test'
        none_only_task.spec['meta']['none_only'] = True

        # Allowed when condition is solely 'none'.
        m2.check_none_only([normal_task, none_only_task], ['none'])

        # Rejected for non-none conditions and mixed batches.
        for conds in [['gold'], ['promptguard'], ['plain'], ['none', 'gold']]:
            with self.subTest(conds=conds), self.assertRaises(SystemExit):
                m2.check_none_only([normal_task, none_only_task], conds)

        # cmd_run and cmd_play reject before touching system_root or running Claude.
        with mock.patch.object(mt, 'load_tasks', return_value=[normal_task, none_only_task]), \
             mock.patch.object(m2, 'system_root', side_effect=AssertionError('system_root should not be reached')):
            for cond in ('gold', 'promptguard', 'plain', 'none,gold'):
                args = argparse.Namespace(tasks=['all'], conditions=cond, system_root=None)
                with self.assertRaises(SystemExit):
                    m2.cmd_run(args)
            play_args = argparse.Namespace(task='n00-none-only-test', condition='gold', system_root=None)
            with mock.patch.object(mt, 'load_tasks', return_value=[none_only_task]), self.assertRaises(SystemExit):
                m2.cmd_play(play_args)


if __name__=='__main__': unittest.main()
