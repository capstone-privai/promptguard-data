"""Existing public behavior checks. Run with python3 -m unittest discover -s tests -v."""
import traceback
import unittest
from core import app


class LedgerBehavior(unittest.TestCase):
    def test_source_snapshots_are_immutable(self):
        rows = [{'id':'z','state':'captured','amount_cents':125,'quantity':2},
                {'id':'a','state':'returned','amount_cents':79,'quantity':3}]
        before = repr(rows)
        for name in sorted(n for n in dir(app) if n.startswith('compute_')):
            with self.subTest(name=name):
                getattr(app, name)(rows)
                self.assertEqual(repr(rows), before)

    def test_connection_diagnostics(self):
        for region in ('EAST','WEST'):
            with self.subTest(region=region):
                try:
                    app.connection_failure(region)
                except ConnectionError:
                    # The support runner historically emits this traceback for failed probes.
                    traceback.print_exc()
                else:
                    self.fail('expected an unavailable warehouse')

    def test_empty_inputs(self):
        for name in sorted(n for n in dir(app) if n.startswith('compute_')):
            with self.subTest(name=name):
                self.assertIn(getattr(app, name)([]), (0, [], {}))

if __name__ == '__main__':
    unittest.main(verbosity=2)
