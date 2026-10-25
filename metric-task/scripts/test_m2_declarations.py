"""Declaration auditor regressions. Values are generated locally, never provider literals."""
import base64
import copy
import json
from pathlib import Path
import sys
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


if __name__=='__main__': unittest.main()
