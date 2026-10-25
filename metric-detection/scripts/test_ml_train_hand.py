"""Focused regression tests for ML-only hand-template syntax and span unions (stdlib unittest)."""
import json
import unittest

import ml_train_build as B


def build(*texts):
    items = [{'channel': channel, 'text': text} for channel,text in texts]
    template = {'session_id':'hand-unit','meta':{'split':'train','group_id':'hand-unit','value_profile':'mltrain'},
                'items':items}
    return B.build_lines([json.dumps(template)],'unit','unit','unit.jsonl')


def check(rows):
    errors = []
    B.check_rows(*rows,'unit',errors)
    return errors


class ReplayTests(unittest.TestCase):
    def test_common_value_in_identifier_and_ordinary_text(self):
        rows = build(('tool_output','password="{{PASSWORD=admin}}"'),
                     ('tool_output','user="{{PASSWORD=admin|as=identifier}}"\nstatus: {{PASSWORD=admin|as=not_propagated}}'))
        self.assertEqual(check(rows), [])
        self.assertEqual(len(rows[1]), 1)
        self.assertEqual([r['kind'] for r in rows[2]], ['identifier','not_propagated'])

    def test_distinct_value_propagates_to_log_but_not_user(self):
        rows = build(('tool_output','api_key="{{generic_secret:a}}"'),
                     ('tool_output','opaque="{{generic_secret:a}}"'),
                     ('tool_output','user="{{generic_secret:a|as=identifier}}"'))
        self.assertEqual(check(rows), [])
        session, gold, labels = rows
        self.assertEqual(len(gold), 2)
        label = labels[0]
        self.assertTrue(label['replay'])
        value = session[0]['items'][2]['text'][label['start']:label['end']]
        self.assertEqual(value, session[0]['items'][0]['text'][gold[0]['span']['start']:gold[0]['span']['end']])

    def test_replay_cannot_hide_a_credential_position(self):
        rows = build(('tool_output','api_key="{{generic_secret:a}}"'),
                     ('tool_output','password="{{generic_secret:a|as=identifier}}"'))
        self.assertTrue(any('expected identifier' in e for e in check(rows)))

    def test_replay_requires_positive_counterpart(self):
        rows = build(('tool_output','user="{{generic_secret:a|as=identifier}}"'))
        self.assertTrue(any('no positive occurrence' in e for e in check(rows)))

    def test_distinct_value_is_not_common(self):
        rows = build(('tool_output','secret="{{generic_secret:a}}"'),
                     ('tool_output','opaque="{{generic_secret:a|as=not_propagated}}"'))
        self.assertTrue(any('expected not_propagated' in e for e in check(rows)))

    def test_tool_input_uses_mask_after_transformed_secret(self):
        rows = build(('tool_output','Authorization: Basic {{password_random:a|basic=agent}}'),
                     ('tool_input','inspect "{{mask:a}}"'))
        self.assertEqual(check(rows), [])
        self.assertEqual(rows[0][0]['items'][1]['text'],'inspect "[TOKEN_1]"')
        with self.assertRaisesRegex(ValueError,'outside tool_input'):
            build(('tool_output','password="{{PASSWORD=admin}}"'),
                  ('tool_input','user="{{PASSWORD=admin|as=identifier}}"'))
        with self.assertRaisesRegex(ValueError,'outside tool_input'):
            build(('tool_output','secret="{{generic_secret:a}}"'),
                  ('tool_input','user="{{generic_secret:a|as=identifier}}"'))

    def test_invalid_role_fails_instead_of_silently_becoming_negative(self):
        with self.assertRaises(ValueError):
            build(('tool_output','user="{{generic_secret:a|as=anything}}"'))


class BoundaryTests(unittest.TestCase):
    def test_suffix_before_json_and_url_preserves_visible_encoding(self):
        rows = build(('tool_output','password="{{password_random:a|suffix=.|json}}"\n'
                       'password="{{password_random:b|suffix="|json}}"\n'
                       'password="{{password_random:c|suffix=/@+|url}}"'))
        self.assertEqual(check(rows), [])
        text=rows[0][0]['items'][0]['text']
        values=[text[g['span']['start']:g['span']['end']] for g in rows[1]]
        self.assertTrue(values[0].endswith('.'))
        self.assertTrue(values[1].endswith('\\"'))
        self.assertTrue(values[2].endswith('%2F%40%2B'))

    def test_touching_gold_is_one_actual_span(self):
        rows = build(('tool_output','secret="{{generic_secret:a}}{{generic_token:b}}"'))
        self.assertEqual(check(rows), [])
        self.assertEqual(len(rows[1]),1)
        span=rows[1][0]['span']
        text=rows[0][0]['items'][0]['text']
        self.assertEqual((span['start'],span['end']),(8,len(text)-1))

    def test_chain_uses_longest_original_instead_of_growing_union(self):
        spans=[{'start':0,'end':5,'type':'PASSWORD'}, {'start':5,'end':9,'type':'TOKEN'},
               {'start':9,'end':16,'type':'SECRET'}]
        merged=B.merge_spans(spans)
        self.assertEqual(merged,[{'start':0,'end':16,'type':'SECRET'}])
        self.assertEqual(spans[0]['end'],5)

    def test_overlaps_and_private_key_priority(self):
        self.assertEqual(B.merge_spans([{'start':0,'end':10,'type':'TOKEN'},
                                        {'start':4,'end':7,'type':'PRIVATE_KEY'},
                                        {'start':10,'end':50,'type':'SECRET'}]),
                         [{'start':0,'end':50,'type':'PRIVATE_KEY'}])

    def test_real_gap_does_not_merge(self):
        spans=[{'start':0,'end':4,'type':'PASSWORD'},{'start':5,'end':10,'type':'SECRET'}]
        self.assertEqual(B.merge_spans(spans),spans)

    def test_suffix_rejects_empty_argument(self):
        with self.assertRaises(ValueError):
            B.extra_transform('abc','suffix',None)


if __name__ == '__main__':
    unittest.main()
