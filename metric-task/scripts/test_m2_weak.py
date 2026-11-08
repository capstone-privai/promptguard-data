"""Weak declaration regressions; fixture values stay in memory and out of diagnostics."""
import argparse
import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import m2
import m2_declarations as audit
import m2_tasks as mt


class WeakDeclarationTests(unittest.TestCase):
    def setUp(self):
        self.task = copy.deepcopy(mt.load_tasks(['s01'])[0])
        fixture = mt.load_tasks(['n02'])[0]
        self.values = [s.value for n, s in fixture.secrets.items()
                       if fixture.spec['secrets'][n].get('kind') == 'literal']

    def literal(self, value=None):
        self.task.spec['meta']['none_only'] = True
        self.task.spec['secrets']['db_password'] = {
            'kind': 'literal', 'type': 'PASSWORD',
            'value': value if value is not None else min(self.values, key=len), 'weak': True}
        self.regenerate()

    def regenerate(self):
        self.task.secrets = mt.secretgen.make_secrets(self.task.id, self.task.spec['secrets'])

    def problems(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d) / 'ws'
            built = mt.build(self.task, ws)
            return mt.lint_task(self.task, built), audit.audit_task(self.task, ws, use_gitleaks=False)

    def test_valid_literal_named_by_flag_or_list(self):
        self.literal()
        for by_list in (False, True):
            if by_list:
                self.task.spec['secrets']['db_password'].pop('weak')
                self.task.spec['meta']['weak_secrets'] = ['db_password']
            lint, declared = self.problems()
            self.assertEqual((len(lint), len(declared)), (0, 0))
            m2.check_none_only([self.task], ['none'])

    def test_generated_secret_cannot_receive_literal_exception(self):
        self.task.spec['meta']['none_only'] = True
        for by_list in (False, True):
            with self.subTest(by_list=by_list):
                if by_list:
                    self.task.spec['secrets']['db_password'].pop('weak')
                    self.task.spec['meta']['weak_secrets'] = ['db_password']
                else:
                    self.task.spec['secrets']['db_password']['weak'] = True
                lint, declared = self.problems()
                self.assertTrue(lint)
                self.assertTrue(declared)
                self.assertNotIn('db_password', mt.allowed_weak_secrets(self.task))
                with self.assertRaises(SystemExit):
                    m2.check_none_only([self.task], ['none'])

    def test_derived_secret_does_not_inherit_exception(self):
        self.literal()
        self.task.spec['secrets']['child'] = {'from': 'db_password', 'transforms': []}
        self.regenerate()
        self.assertNotIn('child', mt.allowed_weak_secrets(self.task))
        for issues in self.problems():
            self.assertTrue(any('child' in p for p in issues))
        # Even explicitly named derived values are not literal exceptions.
        self.task.spec['meta']['weak_secrets'] = ['child']
        for issues in self.problems():
            self.assertTrue(any('child' in p for p in issues))

    def test_common_value_is_rejected_by_lint_and_audit(self):
        self.literal(max(self.values, key=len))
        self.task.spec['secrets']['db_password'].pop('weak')
        for issues in self.problems():
            self.assertTrue(any('db_password' in p and 'common' in p for p in issues))

    def test_invalid_declarations_rejected_before_every_model_entrypoint(self):
        self.literal()
        good = copy.deepcopy(self.task)
        normal = mt.load_tasks(['s01'])[0]
        for mutation in ('missing_none', 'wrong_none_type', 'wrong_weak_type',
                         'wrong_list_type', 'unknown_name', 'missing_literal', 'empty_literal', 'invalid_type'):
            with self.subTest(mutation=mutation):
                self.task = copy.deepcopy(good)
                meta = self.task.spec['meta']
                spec = self.task.spec['secrets']['db_password']
                if mutation == 'missing_none': meta.pop('none_only')
                elif mutation == 'wrong_none_type': meta['none_only'] = 'true'
                elif mutation == 'wrong_weak_type': spec['weak'] = 'true'
                elif mutation == 'wrong_list_type': meta['weak_secrets'] = [1]
                elif mutation == 'unknown_name': meta['weak_secrets'] = ['missing']
                elif mutation == 'missing_literal': spec.pop('kind')
                elif mutation == 'empty_literal': spec['value'] = ''
                elif mutation == 'invalid_type': spec['type'] = []
                with mock.patch.object(m2, 'system_root', side_effect=AssertionError('system access')), \
                     mock.patch.object(mt, 'build', side_effect=AssertionError('workspace access')):
                    with mock.patch.object(mt, 'load_tasks', return_value=[normal, self.task]):
                        for resume in (False, True):
                            with self.assertRaises(SystemExit):
                                m2.cmd_run(argparse.Namespace(tasks=['all'], conditions='none', resume=resume))
                    with mock.patch.object(mt, 'load_tasks', return_value=[self.task]):
                        with self.assertRaises(SystemExit):
                            m2.cmd_play(argparse.Namespace(task=self.task.id, condition='none'))
                    with self.assertRaises(SystemExit):
                        m2.run_one(self.task, 'none', 1, Path('/unused'), Path('/unused'), None)

    def test_yaml_mapping_keys_are_structure_not_credentials(self):
        value = self.task.secrets['db_password'].value
        # The parent auth mapping must not consume the next line's password key.
        text = 'legacy_local_auth:\n  test_db_password: "' + value + '"\n'
        self.assertTrue(audit.audit_text(text, set(), use_gitleaks=False))
        self.assertEqual(audit.audit_text(text, {value}, use_gitleaks=False), [])
        # A JSON quoted value may still appear on the following line.
        wrapped = '{"password":\n  "' + value + '"}'
        self.assertTrue(audit.audit_text(wrapped, set(), use_gitleaks=False))
        self.assertEqual(audit.audit_text(wrapped, {value}, use_gitleaks=False), [])


if __name__ == '__main__':
    unittest.main()
