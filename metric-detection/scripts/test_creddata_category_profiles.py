"""Empirical profile contracts and train fidelity; no credential fixtures.

python3 -B -m unittest discover -s metric-detection/scripts -p test_creddata_category_profiles.py -v
python3 -B metric-detection/scripts/test_creddata_category_profiles.py --report runs/creddata-source-fullfile/category_profiles_v2_review.md

Source-dependent checks skip when the ignored inputs are absent. Every category
with >=30 distinct session/value pairs gets 3,000 draws, full CDF/shape/class/run
checks, including shape-conditional checks where >=30 distinct values exist.
Every free-form category also gets 20,000 draws checked against ALL split gold
values using the sampler's analytic probability and a family-wise chance bound.
"""
from collections import Counter
from functools import lru_cache
import io
import json
import math
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import creddata_category_profiles as p
from value_gen import Draw

INPUTS = (p.DEFAULT_SESSIONS, p.DEFAULT_LABELS, p.DEFAULT_TRAIN, p.DEFAULT_CATEGORIES)
HAS_INPUTS = all(path.is_file() for path in INPUTS)
DRAWS = 3000
COLLISION_DRAWS = 20_000


@lru_cache(maxsize=1)
def training():
    return p.load_training_values()


@lru_cache(maxsize=1)
def document():
    return p.build_document(training())


@lru_cache(maxsize=None)
def generated(category, count=DRAWS):
    model = document()["profiles"]["category:" + category]
    return Counter(p.generate_from_profile(model, Draw(f"empirical-v2:{category}:{i}")) for i in range(count))


@lru_cache(maxsize=None)
def uniform_reference(category):
    """Independent sampler from source pairs for the uniform-shape contract.

    Hex/digit shapes retain public counting, repetition and leading-zero structure.
    Compare run positions with a separate random.Random implementation so that
    the allowed train/reference difference is measured, rather than guessed or
    hidden in an arbitrary tolerance. Class masks preserve their exact order.
    """
    rng = random.Random("source-reference:" + category)
    source = p.values_for_profile(training(), "category:" + category)
    population = sorted(v for v in source if any(c.isalnum() for c in v))
    selected = rng.choices(population, weights=[source[v] for v in population], k=8000)
    result = Counter()
    def uniform(n, alphabet):
        return "".join(rng.choice(alphabet) for _ in range(n))
    def structured(n, alphabet, spec):
        require_letter=spec.get("alphabet", "").startswith("hex_")
        if spec.get("repeat"):
            k = spec["repeat"]
            block = uniform(k, alphabet)
            while (any(k % j == 0 and block == block[:j] * (k//j) for j in range(1,k)) or
                   (require_letter and block.isdigit())):
                block = uniform(k, alphabet)
            return block * (n//k)
        if spec.get("sequence"):
            start = rng.randrange(10)
            return "".join(str((start+i*spec["sequence"]) % 10) for i in range(n))
        zeros = spec.get("leading_zeros", 0)
        tail=uniform(n-zeros,alphabet)
        while require_letter and tail.isdigit():tail=uniform(n-zeros,alphabet)
        return "0"*zeros + tail
    for original in selected:
        skeleton = p.skeleton_of(original)
        if skeleton["kind"] == "uniform":
            padding = skeleton["padding"]
            value = structured(skeleton["length"]-padding, p.ALPHABETS[skeleton["alphabet"]], skeleton) + "="*padding
        else:
            chunks = []
            for token in skeleton["tokens"]:
                kind = token["kind"]
                if kind == "letters":
                    pattern = token["case"]
                    choices = p.WORDS_BY_LENGTH.get(len(pattern), ())
                    word = (rng.choices([w for w,_ in choices], weights=[n for _,n in choices])[0]
                            if token["dictionary"] and choices else uniform(len(pattern), p.LOWER))
                    chunks.append("".join(c.upper() if m == "A" else c for c,m in zip(word,pattern)))
                elif kind == "digits":
                    chunks.append(structured(token["length"], p.DIGITS, token))
                elif kind == "unicode":
                    chunks.append(uniform(1,p.unicode_alphabet(**{k:v for k,v in token.items() if k != "kind"})))
                elif kind == "escape":
                    chunks.append("%"+"".join(uniform(1,p.DIGITS if c == "0" else "ABCDEF" if c == "A" else "abcdef") for c in token["case"]))
                else:
                    chunks.append(token["text"])
            value = "".join(chunks)
        result[value] += 1
    return result


def share(values, predicate):
    return sum(w for v, w in values.items() if predicate(v)) / sum(values.values())


def distribution(values, feature):
    counts = Counter()
    for v, w in values.items():
        counts[feature(v)] += w
    total = sum(counts.values())
    return {k: w / total for k, w in sorted(counts.items())}


def longest_position(value):
    runs = p.runs_of(value)
    index = max(range(len(runs)), key=lambda i: runs[i][1])
    return index / max(1, len(runs) - 1)


def rigid_cvc(value):
    runs = re.findall(r"[a-z]{4,}", value)
    return bool(runs) and all(all((c in p.VOWELS) == (i % 3 == 1)
                                 for i, c in enumerate(run)) for run in runs)


def rigid_all_lower(value):
    runs = re.findall(r"[a-z]+", value)
    return bool(runs) and all(all((c in p.VOWELS) == (i % 3 == 1)
                                 for i, c in enumerate(run)) for run in runs)


def padding_invalid(value):
    match = re.fullmatch(r"(?:[A-Za-z0-9+/]+|[A-Za-z0-9_-]+)(=+)", value)
    return bool(match and (len(match[1]) not in (1, 2) or len(value) % 4 != 0))


def metrics(values):
    unicode_counts = Counter()
    for value, weight in values.items():
        for char in value:
            if not char.isascii():
                unicode_counts[char] += weight
    return dict(length=distribution(values, len), shape=distribution(values, p.shape_of),
                classes={c: share(values, lambda v, c=c: c in p.character_classes(v)) for c in p.CLASS_NAMES},
                longest_position=distribution(values, longest_position),
                longest_first=share(values, lambda v: longest_position(v) == 0),
                starts_5_digits=share(values, lambda v: re.match(r"[0-9]{5}", v) is not None),
                rigid_cvc=share(values, rigid_cvc), rigid_all_lower=share(values, rigid_all_lower),
                padding=share(values, lambda v: v.endswith("=")),
                invalid_padding=share(values, padding_invalid),
                unicode_characters=distribution(unicode_counts, lambda c: ord(c)) if unicode_counts else {})


def comparison(source, sampled):
    a, b = metrics(source), metrics(sampled)
    return a, b, dict(length_cdf=p.cdf_gap(a["length"], b["length"]),
                     longest_cdf=p.cdf_gap(a["longest_position"], b["longest_position"]))


def by_shape(values, shape):
    return Counter({v: w for v, w in values.items() if p.shape_of(v) == shape})


def detailed_metrics(values):
    """Independent audit features; denominators are included in the report."""
    letters, runs, double = Counter(), 0, 0
    for value, weight in values.items():
        for run in re.findall(r"[A-Za-z]{4,}", value):
            for char in run.lower(): letters[char] += weight
            runs += weight
            double += weight * bool(re.search(r"[aeiou]{2}",run.lower()))
    n = sum(letters.values())
    freq = {c:letters[c]/n if n else 0. for c in p.LOWER}
    digit_values = Counter({v:w for v,w in values.items() if re.fullmatch(r"[0-9]+",v)})
    hex_values = Counter({v:w for v,w in values.items() if re.fullmatch(r"[0-9A-F]+",v) and not v.isdigit()})
    percent_values = Counter({v:w for v,w in values.items() if "%" in v})
    def conditional(pool, predicate):
        return share(pool,predicate) if pool else 0.
    sequence = lambda v: len(v)>=3 and any(all((int(b)-int(a))%10 == d for a,b in zip(v,v[1:])) for d in (1,9))
    return dict(vowel=sum(freq[c] for c in "aeiou"), double_vowel=double/runs if runs else 0.,
        letter_frequency=freq, letter_tv_uniform=sum(abs(freq[c]-1/26) for c in p.LOWER)/2 if n else 0.,
        dictionary=share(values,lambda v:v.isascii() and v.isalpha() and v.lower() in p.PUBLIC_WORDS),
        digit_sequence=conditional(digit_values,sequence), digit_repeated=conditional(digit_values,lambda v:len(set(v))==1),
        hex_block4=conditional(hex_values,lambda v:re.search(r"(.{4})\1",v) is not None),
        hex_leading00=conditional(hex_values,lambda v:v.startswith("00")),
        invalid_percent=conditional(percent_values,lambda v:re.search(r"%(?![a-fA-F0-9]{2})",v) is not None),
        separator_end=share(values,lambda v:v.endswith(("-","_"))),
        double_separator=share(values,lambda v:re.search(r"[-_]{2}",v) is not None),
        counts=dict(values=sum(values.values()),letter_runs=runs,letters=n,digits=sum(digit_values.values()),
                    upper_hex=sum(hex_values.values()),percent=sum(percent_values.values())))


def plain_generated(category,count=DRAWS):
    model=document()["profiles"]["category:"+category]
    return Counter(p.generate_from_profile(model,Draw(f"empirical-v2:{category}:{i}"),True) for i in range(count))


@lru_cache(maxsize=1)
def gold_unicode_positions():
    positions={}
    for gold in training().all_gold_values:
        for i,c in enumerate(gold):
            if not c.isascii() and c.isalpha(): positions.setdefault(i,set()).add(c)
    return positions


def positional_unicode_hits(values):
    positions=gold_unicode_positions()
    return sum(w for v,w in values.items() if any(c in positions.get(i,()) for i,c in enumerate(v)))


def word_probability(run):
    candidates = p.WORDS_BY_LENGTH.get(len(run), ())
    if not candidates:
        return 26. ** -len(run) if set(run.lower()) <= set(p.LOWER) else 0.
    return sum(w for word,w in candidates if word == run.lower()) / sum(w for _,w in candidates)


def structured_probability(spec, value, alphabet):
    if not set(value) <= set(alphabet):
        return 0.
    n, k = len(value), spec.get("repeat", 0)
    require_letter=spec.get("alphabet", "").startswith("hex_")
    if require_letter and value.isdigit():return 0.
    if k:
        if value != value[:k]*(n//k) or p.repeated_block(value[:k]):
            return 0.
        # Number of primitive blocks (Möbius inversion for k <=4).
        q = len(alphabet)
        total = {1:q, 2:q*q-q, 3:q**3-q, 4:q**4-q*q}[k]
        if require_letter:total -= {1:10,2:90,3:990,4:9900}[k]
        return 1/total
    if spec.get("sequence"):
        return .1 if all((int(b)-int(a))%10 == spec["sequence"]%10 for a,b in zip(value,value[1:])) else 0.
    zeros = spec.get("leading_zeros", 0)
    if not value.startswith("0"*zeros):
        return 0.
    denominator=len(alphabet)**(n-zeros)-(10**(n-zeros) if require_letter else 0)
    return 1/denominator


def skeleton_probability(skeleton, value):
    if skeleton["kind"] == "uniform":
        padding = skeleton["padding"]
        if len(value) != skeleton["length"] or (padding and not value.endswith("=" * padding)):
            return 0.
        body = value[:-padding] if padding else value
        return structured_probability(skeleton, body, p.ALPHABETS[skeleton["alphabet"]])
    probability, pos = 1., 0
    for token in skeleton["tokens"]:
        kind = token["kind"]
        length = len(token["case"]) if kind == "letters" else token["length"] if kind == "digits" else len(token["text"]) if kind == "literal" else 3 if kind == "escape" else 1
        run = value[pos:pos+length]
        if len(run) != length:
            return 0.
        if kind == "letters":
            if any(c not in (p.UPPER if case == "A" else p.LOWER) for c,case in zip(run,token["case"])):
                return 0.
            probability *= word_probability(run) if token["dictionary"] else 26. ** -length
        elif kind == "digits":
            probability *= structured_probability(token, run, p.DIGITS)
        elif kind == "unicode":
            alphabet = p.unicode_alphabet(**{k:v for k,v in token.items() if k != "kind"})
            if run not in alphabet: return 0.
            probability /= len(alphabet)
        elif kind == "escape":
            if run[0] != "%": return 0.
            for c,case in zip(run[1:],token["case"]):
                alphabet = p.DIGITS if case == "0" else "ABCDEF" if case == "A" else "abcdef"
                if c not in alphabet: return 0.
                probability /= len(alphabet)
        elif run != token["text"]:
            return 0.
        pos += length
    return probability if pos == len(value) else 0.


def value_probability(model, value):
    return sum(s["weight"] * skeleton_probability(s, value) for s in model["skeletons"]) / model["session_values"]


@lru_cache(maxsize=1)
def collision_audit():
    gold = {v for v in training().all_gold_values if len(v) >= 6}
    models = document()["profiles"]
    log_alpha = math.log(.001 / (len(gold) * len(models)))
    rows, failures = [], []
    for key, model in sorted(models.items()):
        category = key.split(":", 1)[1]
        sampled = generated(category, COLLISION_DRAWS)
        hits = {v: n for v, n in sampled.items() if v in gold}
        worst_log_tail = 0.
        for value, count in hits.items():
            probability = value_probability(model, value)
            expected = COLLISION_DRAWS * probability
            # The binomial Chernoff bound is valid for all p, unlike a normal
            # approximation at tiny collision probabilities; apply a Bonferroni
            # correction over all split values AND all category profiles.
            log_tail = (-expected + count * (1 + math.log(expected / count))) if 0 < expected < count else (0. if expected else -math.inf)
            worst_log_tail = min(worst_log_tail, log_tail)
            if log_tail < log_alpha:
                failures.append((category, count, expected, log_tail, log_alpha))
        rows.append((category, len(hits), sum(hits.values()), worst_log_tail))
    return rows, failures


class ContractTests(unittest.TestCase):
    def test_default_ignored_path_missing_error_and_old_profile_deleted(self):
        self.assertEqual(p.DEFAULT_OUTPUT.relative_to(p.ROOT).as_posix(),
                         "runs/creddata-source-fullfile/category_profiles_v2.json")
        self.assertFalse((p.ROOT / "metric-detection/templates/creddata_tasks/category_profiles_v1.json").exists())
        with tempfile.TemporaryDirectory() as directory, patch.object(p, "DEFAULT_OUTPUT", Path(directory) / "missing.json"):
            for action in (lambda: p.profile_for("Password"), lambda: p.generate("Password", Draw("absent"))):
                p._document.cache_clear()
                with self.assertRaisesRegex(FileNotFoundError, re.escape(p.BUILD_COMMAND)):
                    action()
        p._document.cache_clear()

    def test_skeletons_preserve_every_class_position_and_literal(self):
        value = "x" * 5 + "_" + "A" * 2 + " 3!\n" + chr(0x3a8) + chr(0x4e00)
        skeleton = p.skeleton_of(value)
        self.assertEqual(skeleton["kind"], "classes")
        self.assertNotIn("x"*5, json.dumps(skeleton))
        for i in range(100):
            result = p.generate_from_skeleton(skeleton, Draw(f"literal:{i}"))
            self.assertEqual(len(result), len(value))
            for a, b in zip(value, result):
                if a.isalnum():
                    self.assertEqual(p._class(a), p._class(b))
                else:
                    self.assertEqual(a, b)

    def test_pairs_are_uniform_and_lengths_and_rare_shapes_are_exact(self):
        values = Counter({"x" * 7: 1, "A" * 11: 3, "7" * 17: 2, "x" * 3 + " ": 1})
        model = p.make_profile(values, "fixture", "Password")
        sampled = Counter(p.generate_from_profile(model, Draw(f"pair:{i}")) for i in range(3000))
        self.assertLess(p.cdf_gap(p.length_counts(values), p.length_counts(sampled)), .035)
        self.assertLess(abs(share(sampled, lambda v: " " in v) - 1/7), .03)
        self.assertEqual(model["session_values"], 7)
        self.assertEqual(sum(s["weight"] for s in model["skeletons"]), 7)

    def test_uniform_hex_has_no_source_run_order_or_fixed_vowels(self):
        model = p.make_profile(Counter({"7" * 20 + "a" * 12: 1}), "fixture", "Key")
        self.assertEqual(model["skeletons"][0]["kind"], "uniform")
        sample = Counter(p.generate_from_profile(model, Draw(f"hex:{i}")) for i in range(3000))
        self.assertLess(share(sample, lambda v: re.match(r"[0-9]{5}", v) is not None), .14)
        self.assertLess(share(sample, lambda v: longest_position(v) == 0), .22)
        uniform = p.make_profile(Counter({"z" * 12: 1}), "fixture", "Password")
        sampled = Counter(p.generate_from_profile(uniform, Draw(f"vowels:{i}")) for i in range(1000))
        self.assertGreater(share(sampled, lambda v: any(c in p.VOWELS for c in v)), .85)
        self.assertLess(share(sampled, rigid_cvc), .01)
        # Use a public generated pronounceable run outside hex.
        wordlike = p.make_profile(Counter({"om" * 6: 1}), "fixture", "Password")
        sampled = Counter(p.generate_from_profile(wordlike, Draw(f"syllable:{i}")) for i in range(1000))
        self.assertLess(share(sampled, rigid_cvc), .05)
        self.assertGreater(len({tuple(c in p.VOWELS for c in v) for v in sampled}), 100)

    def test_uniform_alphabets_and_padding_repairs(self):
        for alphabet in ("base64", "base64url"):
            for padding in (0, 1, 2):
                for length in (12, 16, 64):
                    skeleton = dict(kind="uniform", alphabet=alphabet, length=length, padding=padding)
                    for i in range(10):
                        value = p.generate_from_skeleton(skeleton, Draw(f"encoding:{alphabet}:{padding}:{length}:{i}"))
                        self.assertEqual(len(value), length)
                        self.assertEqual(len(value) - len(value.rstrip("=")), padding)
                        self.assertEqual(len(value) % 4, 0)
                        self.assertTrue(set(value.rstrip("=")) <= set(p.ALPHABETS[alphabet]))
        for length in range(7, 12):
            skeleton = p.skeleton_of("x" * (length - 1) + "=")
            self.assertEqual(skeleton["length"] % 4, 0)
            self.assertEqual(skeleton["padding"], 1)
            self.assertLess(skeleton["length"] - length, 4)

    def test_unicode_letters_are_script_case_markers_and_fresh_draws(self):
        import unicodedata
        for codepoint in (0x3A8, 0x4E00, 0xE9, 0x41F, 0x30AB, 0x1F31F):
            char = chr(codepoint)
            skeleton = p.skeleton_of("x"*6 + char + "!")
            if char.isalpha():
                self.assertNotIn(char,json.dumps(skeleton,ensure_ascii=False))
                sampled = [p.generate_from_skeleton(skeleton,Draw(f"unicode:{codepoint}:{i}")) for i in range(200)]
                self.assertGreater(len({v[6] for v in sampled}),8)
                self.assertTrue(all(v[6] != char and unicodedata.category(v[6]) == unicodedata.category(char) for v in sampled))
            else:
                self.assertTrue(all(p.generate_from_skeleton(skeleton,Draw(str(i)))[6] == char for i in range(10)))

    def test_plain_single_line_same_length_and_never_starts_with_dash(self):
        model = p.make_profile(Counter({"-" + "x" * 8 + " !\n" + chr(0x3a8): 1}), "fixture", "Password")
        for i in range(3000):
            seed = f"plain:{i}"
            raw = p.generate_from_profile(model, Draw(seed))
            plain = p.generate_from_profile(model, Draw(seed), plain=True)
            self.assertEqual(len(raw), len(plain))
            self.assertTrue(set(plain) <= set(p.PLAIN_ALPHABET))
            self.assertFalse(plain.startswith("-"))

    def test_gold_source_train_filter_canonical_pairs_and_fixed_exclusion(self):
        texts = {"train-a": "x" * 8 + "y" * 8, "train-b": "x" * 8,
                 "validation": "v" * 8, "test": "t" * 8}
        def row(session, category=None, start=0, **kwargs):
            return dict(session_id=session, item_id=0, start=start, end=start + 8,
                        category=category, **kwargs)
        gold = [row("train-a", "Secret:Key"), row("train-a", "Key:Secret"),
                row("train-b", "Key:Secret"), row("train-a", "Auth:Basic Authorization", start=8),
                row("train-a", "Password", start=8, dropped=True),
                row("train-a", "Password", start=8, dropped=False), row("validation", "Password")]
        files = {"sessions": "".join(json.dumps(dict(session_id=s, items=[dict(item_id=0, text=t)])) + "\n"
                                    for s, t in texts.items()),
                 "labels": "".join(json.dumps(row(s, "Password", gold=True)) + "\n" for s in texts),
                 "categories": "".join(json.dumps(r) + "\n" for r in gold)}
        with patch.object(Path, "read_text", return_value="train-a\ntrain-b\n"), \
                patch.object(Path, "open", lambda path, **kwargs: io.StringIO(files[str(path)])):
            data = p.load_training_values("sessions", "labels", "train", "categories")
        self.assertEqual(data.full["Key:Secret"], Counter({"x" * 8: 2}))
        self.assertEqual(data.atoms["Key"], Counter({"x" * 8: 2}))
        self.assertNotIn("Auth", data.atoms)
        self.assertNotIn("Password", data.full)
        self.assertIn("v" * 8, data.all_gold_values)
        self.assertIn("t" * 8, data.all_gold_values)

    def test_probability_oracle_normalizes_public_dictionary_and_structures(self):
        for n in (1,2,4,8):
            self.assertAlmostEqual(sum(word_probability(w) for w,_ in p.WORDS_BY_LENGTH[n]), 1.)
        skeleton = p.skeleton_of("xx_77")
        self.assertAlmostEqual(skeleton_probability(skeleton,"xy_77"), 26**-2 * .1)
        self.assertEqual(skeleton_probability(skeleton,"xy_78"),0.)
        for text in ("123456", "AB"*8, "00AB1234"):
            skeleton = p.skeleton_of(text)
            for i in range(10):
                self.assertGreater(skeleton_probability(skeleton,p.generate_from_skeleton(skeleton,Draw(f"prob:{text}:{i}"))),0.)

    def test_exact_dictionary_matching_case_and_short_letters_are_not_hex(self):
        for word in ("dead", "BeEf", "FaCe", "secret", "PaSsWoRd"):
            skeleton = p.skeleton_of(word)
            self.assertEqual(skeleton["kind"],"classes")
            for i in range(50):
                value = p.generate_from_skeleton(skeleton,Draw(f"dictionary:{word}:{i}"))
                self.assertTrue(value.isalpha())
                self.assertIn(value.lower(),p.PUBLIC_WORDS)
                self.assertEqual([c.isupper() for c in value],[c.isupper() for c in word])
        self.assertFalse(p.skeleton_of("abucadev")["tokens"][0]["dictionary"])
        letters = "".join(p.generate_from_skeleton(p.skeleton_of("abucadev"),Draw(f"uniform:{i}")) for i in range(4000))
        self.assertLess(abs(sum(c in p.VOWELS for c in letters)/len(letters)-5/26),.01)
        counts=Counter(letters)
        self.assertLess(sum(abs(counts[c]/len(letters)-1/26) for c in p.LOWER)/2,.025)
        # The removed syllable grammar passed the old rigid-CVC tests; it must
        # fail this independent letter-frequency / vowel regression.

    def test_structured_digit_runs_repeated_blocks_and_leading_zeros(self):
        for original in ("1234567","987654","555555","24"*16,"AB"*16,"A1B2"*8,"00AB12FF"):
            skeleton=p.skeleton_of(original)
            values=[p.generate_from_skeleton(skeleton,Draw(f"structure:{original}:{i}")) for i in range(100)]
            self.assertGreater(len(set(values)),5)
            if len(set(original)) == 1:
                self.assertTrue(all(len(set(v)) == 1 for v in values))
            elif original.isdigit() and p.digit_sequence(original):
                self.assertTrue(all(p.digit_sequence(v) for v in values))
            elif p.repeated_block(original):
                self.assertTrue(all(p.repeated_block(v) == p.repeated_block(original) for v in values))
            else:
                self.assertTrue(all(v.startswith("00") for v in values))
        skeleton=p.skeleton_of("test_123456_5555")
        for i in range(100):
            _,sequence,repeated=p.generate_from_skeleton(skeleton,Draw(f"runs:{i}")).split("_")
            self.assertTrue(p.digit_sequence(sequence))
            self.assertEqual(len(set(repeated)),1)

    def test_percent_escapes_plain_padding_and_drop_symbol_only_skeletons(self):
        model=p.make_profile(Counter({"ab%2F%3a_77":1,"!"*17:2}),"fixture","Password")
        self.assertEqual(model["dropped_symbol_values"],2)
        self.assertEqual(model["session_values"],1)
        for i in range(300):
            value=p.generate_from_profile(model,Draw(f"escapes:{i}"))
            self.assertFalse(re.search(r"%(?![0-9A-Fa-f]{2})",value))
        with self.assertRaises(ValueError):p.make_profile(Counter({"!@#$":1}),"fixture","Salt:Token")
        for original in ("xxxxxx==","xxxxxxx=","a!!\n?","777!!"):
            model=p.make_profile(Counter({original:1}),"fixture","Auth")
            for i in range(100):
                raw=p.generate_from_profile(model,Draw(f"plain-neighbour:{i}"))
                plain=p.generate_from_profile(model,Draw(f"plain-neighbour:{i}"),True)
                self.assertEqual(len(raw),len(plain))
                self.assertTrue(plain.isalnum())
                self.assertEqual(p._class(plain[-1]),p._class(plain[-2]))

    def test_avoid_resamples_deterministically_and_has_bounded_failure(self):
        model=p.make_profile(Counter({'"'+'x'*8:3,"x"*8:1,"x"*8+"\\":1}),"fixture","Password")
        with patch.object(p,"_document",return_value={"profiles":{"category:Password":model}}):
            for plain in (False,True):
                for i in range(100):
                    seed=f"avoid:{plain}:{i}"
                    a=p.generate("Password",Draw(seed),plain,avoid='"\\ \t\n')
                    self.assertEqual(a,p.generate("Password",Draw(seed),plain,avoid='"\\ \t\n'))
                    self.assertFalse(set(a)&set('"\\ \t\n'))
            with self.assertRaisesRegex(ValueError,"128 attempts"):
                p.generate("Password",Draw("impossible"),avoid=p.PLAIN_ALPHABET)
        constant=p.make_profile(Counter({'"'+'x'*8:1}),"fixture","Password")
        with self.assertRaisesRegex(ValueError,"128 attempts"):
            p.generate_from_profile(constant,Draw("literal-impossible"),avoid='"')


@unittest.skipUnless(HAS_INPUTS, "Ignored CredData sources absent; build with " + p.BUILD_COMMAND)
class SourceTests(unittest.TestCase):
    def test_rebuild_equality_and_profile_schema_has_only_skeletons(self):
        built = p.serialize_document(document())
        self.assertEqual(built, p.serialize_document(p.build_document(training())))
        if p.DEFAULT_OUTPUT.exists():
            self.assertEqual(p.DEFAULT_OUTPUT.read_text(encoding="utf-8"), built)
        self.assertEqual(subprocess.check_output(["git", "check-ignore", str(p.DEFAULT_OUTPUT)], cwd=p.ROOT, text=True).strip(), str(p.DEFAULT_OUTPUT))
        for key, model in document()["profiles"].items():
            source = p.values_for_profile(training(), key)
            self.assertEqual(model["session_values"] + model["dropped_symbol_values"], sum(source.values()))
            rebuilt = p.make_profile(source, model["source"], model["category"])
            self.assertEqual(model, rebuilt)
            for skeleton in model["skeletons"]:
                if skeleton["kind"] == "classes":
                    for token in skeleton["tokens"]:
                        if token["kind"] == "literal":
                            self.assertFalse(any(c.isalnum() for c in token["text"]))
                        self.assertFalse(any(not c.isascii() and c.isalpha() for c in json.dumps(token,ensure_ascii=False)))
                else:
                    self.assertNotIn("tokens", skeleton)

    def test_canonical_resolution_own_small_profiles_and_closest_pool(self):
        doc, data = document(), training()
        for category in data.categories:
            if not p.is_free(category):
                with self.assertRaises(KeyError): p._resolve(category, doc)
                continue
            canonical = p.canonical_category(category)
            for ordering in (category, ":".join(category.split(":")[::-1])):
                self.assertEqual(p._resolve(ordering, doc), "category:" + canonical)
            values = data.full[canonical]
            model = doc["profiles"]["category:" + canonical]
            if len(values) >= 2:
                self.assertEqual(model["source"], "full_category")
                self.assertEqual(model["distinct_values"], len(values))
            else:
                fallback = doc["fallbacks"][canonical]
                self.assertEqual(fallback["distance"], min(fallback["candidates"].values()))
                self.assertEqual(model["source"], "pooled_singleton")
        for category in ("API:Key:Token", "Auth:Key:Token", "Other"):
            self.assertEqual(doc["profiles"]["category:" + category]["source"], "full_category")
        for category in ("Password:Salt", "API:Key:Secret"):
            self.assertIn(category, doc["fallbacks"])

    def test_full_length_distribution_for_every_category_including_bearer(self):
        for key, model in document()["profiles"].items():
            category = key.split(":", 1)[1]
            source = Counter({v:w for v,w in p.values_for_profile(training(),key).items() if any(c.isalnum() for c in v)})
            sampled = generated(category)
            gap = p.cdf_gap(p.length_counts(source), p.length_counts(sampled))
            self.assertLessEqual(gap, .045, category + ": length CDF")
            if not model["padding_repairs"]:
                self.assertLessEqual(set(map(len, sampled)), set(map(len, source)))
        bearer_lengths = p.length_counts(generated("Bearer Authorization"))
        self.assertGreater(len(bearer_lengths), 1)

    def assert_composition(self, category, source, sampled, tolerance=.055, reference=None):
        a, b, gaps = comparison(source, sampled)
        expected = metrics(reference) if reference is not None else a
        for feature in set(a["shape"]) | set(b["shape"]):
            self.assertLessEqual(abs(a["shape"].get(feature, 0) - b["shape"].get(feature, 0)), tolerance,
                                 f"{category}: shape/{feature}")
        for feature in p.CLASS_NAMES:
            unavoidable = abs(a["classes"][feature] - expected["classes"][feature])
            self.assertLessEqual(abs(a["classes"][feature] - b["classes"][feature]), unavoidable + tolerance,
                                 f"{category}: classes/{feature} vs train")
            self.assertLessEqual(abs(expected["classes"][feature] - b["classes"][feature]), tolerance,
                                 f"{category}: classes/{feature} vs independent uniform reference")
        for feature in ("padding",):
            self.assertLessEqual(abs(a[feature] - b[feature]), tolerance, f"{category}: {feature} {a[feature]:.3f}/{b[feature]:.3f}")
        for feature in ("longest_first", "starts_5_digits"):
            unavoidable = abs(a[feature] - expected[feature])
            self.assertLessEqual(abs(a[feature] - b[feature]), unavoidable + tolerance,
                                 f"{category}: {feature} train/reference/draw {a[feature]:.3f}/{expected[feature]:.3f}/{b[feature]:.3f}")
            self.assertLessEqual(abs(expected[feature] - b[feature]), tolerance,
                                 f"{category}: {feature} independent uniform reference")
        # Natural source words can happen to follow CVC. The regression is an
        # imposed positional pattern, so reject excess CVC, not its removal.
        for feature in ("rigid_cvc", "rigid_all_lower"):
            self.assertLessEqual(b[feature], a[feature] + tolerance,
                                 f"{category}: excess {feature} {a[feature]:.3f}/{b[feature]:.3f}")
        unavoidable = p.cdf_gap(a["longest_position"], expected["longest_position"])
        self.assertLessEqual(gaps["longest_cdf"], unavoidable + tolerance,
                             f"{category}: longest run position CDF {gaps['longest_cdf']:.3f}")
        self.assertLessEqual(p.cdf_gap(expected["longest_position"], b["longest_position"]), tolerance,
                             f"{category}: longest run position CDF vs independent uniform reference")
        self.assertEqual(b["invalid_padding"], 0., category + ": invalid base64 padding")

    def test_per_category_shapes_classes_run_positions_prefixes_and_rigid_pattern(self):
        for category, source in sorted(training().full.items()):
            if not p.is_free(category) or sum(source.values()) < 30:
                continue
            with self.subTest(category=category):
                self.assert_composition(category, source, generated(category), reference=uniform_reference(category))

    def test_shape_conditional_run_positions_and_rigid_patterns(self):
        for category, source in sorted(training().full.items()):
            if not p.is_free(category): continue
            sampled = generated(category)
            for shape in p.SHAPES:
                a, b = by_shape(source, shape), by_shape(sampled, shape)
                if len(a) < 30: continue
                with self.subTest(category=category, shape=shape):
                    self.assertTrue(b, category + ": missing shape " + shape)
                    tolerance = .045 + 3 * math.sqrt(.25 / sum(b.values()))
                    reference = by_shape(uniform_reference(category), shape)
                    self.assert_composition(category + "/" + shape, a, b, tolerance, reference=reference)

    def test_review3_direct_regressions_reject_syllables_and_lost_structure(self):
        for category in ("Password","Token","URL Credentials","CMD Password","Key","Secret","Auth"):
            a,b=map(detailed_metrics,(training().full[category],generated(category)))
            with self.subTest(category=category,metric="vowel"):
                self.assertLessEqual(abs(a["vowel"]-b["vowel"]),.045)
            with self.subTest(category=category,metric="dictionary"):
                self.assertLessEqual(abs(a["dictionary"]-b["dictionary"]),.03)
            with self.subTest(category=category,metric="percent"):
                if a["invalid_percent"] == 0.:
                    self.assertEqual(b["invalid_percent"],0.)
            with self.subTest(category=category,metric="unicode"):
                self.assertEqual(positional_unicode_hits(generated(category)),0)
            plain=detailed_metrics(plain_generated(category))
            for feature in ("separator_end","double_separator"):
                with self.subTest(category=category,metric="plain/"+feature):
                    self.assertLessEqual(plain[feature],a[feature]+.03)
        a,b=map(detailed_metrics,(training().full["Password"],generated("Password")))
        with self.subTest(category="Password",metric="double_vowel"):
            self.assertLessEqual(abs(a["double_vowel"]-b["double_vowel"]),.075)
        with self.subTest(category="Password",metric="digit_sequence"):
            self.assertLessEqual(abs(a["digit_sequence"]-b["digit_sequence"]),.10)
        a,b=map(detailed_metrics,(training().full["Key"],generated("Key",20_000)))
        for feature,tolerance in (("digit_repeated",.12),("hex_block4",.04),("hex_leading00",.04)):
            with self.subTest(category="Key",metric=feature):
                self.assertLessEqual(abs(a[feature]-b[feature]),tolerance)

    def test_per_category_letter_statistics_and_public_dictionary_share(self):
        for category,source in sorted(training().full.items()):
            if not p.is_free(category) or sum(source.values())<30:continue
            with self.subTest(category=category):
                a,b,r=map(detailed_metrics,(source,generated(category),uniform_reference(category)))
                # Genuine source words / repeated obfuscation characters give
                # small categories substantial sampling uncertainty. Large
                # categories still reject the old 0.35 vowel / 0.37 VV rates.
                source_n=max(1,len(source))
                vowel_tolerance=.025+1.5/math.sqrt(source_n)
                double_tolerance=.045+1.5/math.sqrt(source_n)
                self.assertLessEqual(abs(a["vowel"]-b["vowel"]),vowel_tolerance)
                self.assertLessEqual(abs(a["double_vowel"]-b["double_vowel"]),double_tolerance)
                distance=lambda x,y:sum(abs(x[c]-y[c]) for c in p.LOWER)/2
                tv=distance(a["letter_frequency"],b["letter_frequency"])
                reference_tv=distance(a["letter_frequency"],r["letter_frequency"])
                self.assertLessEqual(tv,reference_tv+.025)
                self.assertLessEqual(distance(r["letter_frequency"],b["letter_frequency"]),.04)
                self.assertLessEqual(abs(a["dictionary"]-b["dictionary"]),.025)
        # Explicit thresholds preserve the review's high-power Password check;
        # they are direct train comparisons, independent of the reference.
        a,b=map(detailed_metrics,(training().full["Password"],generated("Password")))
        self.assertLess(abs(a["vowel"]-b["vowel"]),.04)
        self.assertLess(abs(a["double_vowel"]-b["double_vowel"]),.075)
        self.assertLess(sum(abs(a["letter_frequency"][c]-b["letter_frequency"][c]) for c in p.LOWER)/2,.13)
        self.assertGreater(b["dictionary"],a["dictionary"]-.025)

    def test_per_category_digit_and_hex_structures_and_percent_validity(self):
        for category,source in sorted(training().full.items()):
            if not p.is_free(category) or sum(source.values())<30:continue
            with self.subTest(category=category):
                a,b,r=map(detailed_metrics,(source,generated(category),uniform_reference(category)))
                for feature,denominator in (("digit_sequence","digits"),("digit_repeated","digits"),
                                             ("hex_block4","upper_hex"),("hex_leading00","upper_hex")):
                    if not a["counts"][denominator] or not b["counts"][denominator]:continue
                    n=b["counts"][denominator]
                    # Conditional draws can be scarce even for a large category.
                    tolerance=.035+2/math.sqrt(n)
                    self.assertLessEqual(abs(a[feature]-b[feature]),abs(a[feature]-r[feature])+tolerance,feature)
                if a["invalid_percent"] == 0.:
                    self.assertEqual(b["invalid_percent"],0.)
        # Frequent train structures need stronger direct comparisons.
        a,b=map(detailed_metrics,(training().full["Password"],generated("Password")))
        self.assertLess(abs(a["digit_sequence"]-b["digit_sequence"]),.10)
        a,b=map(detailed_metrics,(training().full["Key"],generated("Key",20_000)))
        self.assertLess(abs(a["digit_repeated"]-b["digit_repeated"]),.12)
        for metric in ("hex_block4","hex_leading00"):
            self.assertLess(abs(a[metric]-b[metric]),.04,metric)

    def test_per_category_unicode_positions_plain_artifacts_and_avoid(self):
        for category,source in sorted(training().full.items()):
            if not p.is_free(category) or sum(source.values())<30:continue
            with self.subTest(category=category):
                values=generated(category,COLLISION_DRAWS)
                self.assertEqual(positional_unicode_hits(values),0,"same-position all-split Unicode letter")
                a,b=map(detailed_metrics,(source,plain_generated(category)))
                for metric in ("separator_end","double_separator"):
                    self.assertLessEqual(b[metric],a[metric]+.025,metric)
                model=document()["profiles"]["category:"+category]
                with patch.object(p,"_document",return_value=document()):
                    for i in range(30):
                        seed=f"avoid-category:{category}:{i}"
                        avoid='"\\ \t\r\n'
                        value=p.generate(category,Draw(seed),avoid=avoid)
                        self.assertFalse(set(value)&set(avoid))
                        self.assertEqual(value,p.generate(category,Draw(seed),avoid=avoid))

    def test_plain_all_categories_and_padding(self):
        for key, model in document()["profiles"].items():
            for i in range(1000):
                seed = f"all-plain:{key}:{i}"
                raw = p.generate_from_profile(model, Draw(seed))
                plain = p.generate_from_profile(model, Draw(seed), True)
                self.assertEqual(len(raw), len(plain), key)
                self.assertTrue(plain and set(plain) <= set(p.PLAIN_ALPHABET), key)
                self.assertFalse(plain.startswith("-"), key)
                self.assertFalse(padding_invalid(raw), key)

    def test_determinism_across_processes_and_hash_seeds(self):
        payload = p.serialize_document(document())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(payload, encoding="utf-8")
            code = ("import json,sys; from value_gen import Draw; import creddata_category_profiles as p; "
                    "d=json.load(open(sys.argv[1])); "
                    "print(json.dumps([p.generate_from_profile(m,Draw('process:'+k+str(i)),plain) "
                    "for k,m in sorted(d['profiles'].items()) for i in range(10) for plain in (False,True)]))")
            outputs = [subprocess.check_output([sys.executable, "-B", "-c", code, str(path)],
                        env=dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=str(Path(p.__file__).parent)))
                       for seed in ("1", "1729")]
        self.assertEqual(outputs[0], outputs[1])

    def test_no_all_split_gold_value_is_reproduced_more_often_than_chance_20k(self):
        _, failures = collision_audit()
        # Only category/count/probability appear on failure, never gold values.
        self.assertEqual(failures, [])


def review3_tables():
    categories=("Password","Token","URL Credentials","CMD Password","Key","Secret","Auth")
    rows={}
    # 20k draws keep scarce conditional digit/upper-hex metrics inspectable.
    for category in categories:
        source=training().full[category]
        values=generated(category,COLLISION_DRAWS)
        rows[category]=dict(train=detailed_metrics(source),generated=detailed_metrics(values),
                            plain=detailed_metrics(plain_generated(category,COLLISION_DRAWS)),
                            unicode_same_position=positional_unicode_hits(values))
    def pct(a,b):return f"{100*a:.2f}/{100*b:.2f}"
    lines=["", "## Third review: direct train/generated comparisons", "",
        "20,000 seeded draws per requested category, using distinct (session,value) weights. All cells are train/generated percentages unless labelled otherwise. Letter statistics use ASCII letter runs of length >=4; VV is the share of those runs with consecutive vowels. Dictionary share uses the fixed repo public lexicon, so it differs from the review's external dictionary. Public words are length- and case-matched with modest frequency weights; source vocabulary and source word frequencies are never retained.", "",
        "| Category | Vowels | VV runs | Letter TV to uniform | Letter TV train/generated | Dictionary values |", "|---|---:|---:|---:|---:|---:|"]
    for category,row in rows.items():
        a,b=row["train"],row["generated"]
        tv=sum(abs(a["letter_frequency"][c]-b["letter_frequency"][c]) for c in p.LOWER)/2
        lines.append(f"| {category} | {pct(a['vowel'],b['vowel'])} | {pct(a['double_vowel'],b['double_vowel'])} | {pct(a['letter_tv_uniform'],b['letter_tv_uniform'])} | {100*tv:.2f}% | {pct(a['dictionary'],b['dictionary'])} |")
    lines.extend(["", "Digit and upper-hex columns are conditional on digits-only and uppercase-hex-with-a-letter values, respectively. Counting includes ascending/descending modulo-10 walks of length >=3. Repeated digit includes single-character values. Block4 means an adjacent repeated 4-character block anywhere (including repetitions with a smaller primitive period); this matches the review's 13.8% upper-hex Key statistic. Leading00 means at least two initial zeros.", "",
        "| Category | Digit n T/G | Counting digits | One repeated digit | Upper hex n T/G | Repeated block4 | Leading00 |", "|---|---:|---:|---:|---:|---:|---:|"])
    for category,row in rows.items():
        a,b=row["train"],row["generated"]
        lines.append(f"| {category} | {a['counts']['digits']}/{b['counts']['digits']} | {pct(a['digit_sequence'],b['digit_sequence'])} | {pct(a['digit_repeated'],b['digit_repeated'])} | {a['counts']['upper_hex']}/{b['counts']['upper_hex']} | {pct(a['hex_block4'],b['hex_block4'])} | {pct(a['hex_leading00'],b['hex_leading00'])} |")
    lines.extend(["", "Percent errors are conditional on values with a percent sign. Plain-mode columns compare raw train to generated plain values: dropped punctuation/padding now becomes neighbouring-class letters/digits, while existing dash/underscore positions remain. Unicode hits count any generated non-ASCII letter equal to a letter from ANY split's gold value at the same position; all-split gold is used only by this audit, never by fitting or generation.", "",
        "| Category | Percent n T/G | Invalid escapes | Same-position gold Unicode hits / draws | Plain ending -/_ T/G | Plain doubled separator T/G |", "|---|---:|---:|---:|---:|---:|"])
    for category,row in rows.items():
        a,b,plain=row["train"],row["generated"],row["plain"]
        lines.append(f"| {category} | {a['counts']['percent']}/{b['counts']['percent']} | {pct(a['invalid_percent'],b['invalid_percent'])} | {row['unicode_same_position']}/{COLLISION_DRAWS} | {pct(a['separator_end'],plain['separator_end'])} | {pct(a['double_separator'],plain['double_separator'])} |")
    dropped={k:m['dropped_symbol_values'] for k,m in document()['profiles'].items() if m['dropped_symbol_values']}
    lines.extend(["", f"All-symbol source pairs removed from sampling: {json.dumps(dropped,sort_keys=True)}. Generated lengths remain equal in raw/plain modes. Avoid rejection is deterministic, tries at most 128 skeleton draws, and raises ValueError on failure; every >=30-pair category has 30 delimiter-exclusion checks, with explicit impossible-constraint tests.", "",
        "## Thirty generated Password values", "", "These are the first 30 deterministic raw draws; JSON quoting preserves spaces and punctuation.", "", "```json",
        json.dumps([p.generate_from_profile(document()['profiles']['category:Password'],Draw(f'empirical-v2:Password:{i}')) for i in range(30)],ensure_ascii=False,indent=2), "```", ""])
    return lines,rows


def report(path):
    if not HAS_INPUTS:
        raise SystemExit("Ignored CredData inputs absent")
    rows = []
    lines = ["# Empirical CredData category profile validation", "",
             f"{DRAWS:,} independent draws/category; weights are distinct (session,value) pairs.",
             "Cells show train/generated percentages; lengths and class-run positions use full maximum CDF gaps.",
             "All free-form categories with >=30 session/value pairs are included (even when distinct values <30).", "",
             "Whole base64 and unstructured hex/digit bodies use uniform characters; counting/repeated digits, repeated short hex blocks, leading 00 prefixes and public dictionary matches retain structure. An independent 8,000-draw random.Random reference checks unavoidable run-position changes; new direct train comparisons reject the earlier syllable, dictionary, sequence, hex, Unicode, percent and plain-mode regressions.", "",
             "| Category | Distinct/pairs | Length CDF gap | Shape shares T/G | Class presence T/G | Longest first T/G | Longest position CDF gap | Starts >=5 digits T/G | Rigid CVC (runs >=4) T/G | Rigid CVC (all lower runs) T/G | Padded T/G | Invalid padding T/G | Plain invalid/dash/length failures |",
             "|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    review_lines,review_numeric=review3_tables()
    lines[1:1]=review_lines
    def pct(a, b): return f"{100*a:.2f}/{100*b:.2f}"
    def dist(a, b): return "; ".join(f"{k}:{pct(a.get(k,0), b.get(k,0))}" for k in sorted(set(a)|set(b)))
    for category, source in sorted(training().full.items()):
        if not p.is_free(category) or sum(source.values()) < 30: continue
        sampled = generated(category)
        a, b, gaps = comparison(source, sampled)
        model = document()["profiles"]["category:" + category]
        plain_fail = [0, 0, 0]
        for i in range(DRAWS):
            seed = f"empirical-v2:{category}:{i}"
            plain = p.generate_from_profile(model, Draw(seed), True)
            raw = p.generate_from_profile(model, Draw(seed))
            plain_fail[0] += not set(plain) <= set(p.PLAIN_ALPHABET)
            plain_fail[1] += plain.startswith("-")
            plain_fail[2] += len(plain) != len(raw)
        scalar = [pct(a[k], b[k]) for k in ("starts_5_digits", "rigid_cvc", "rigid_all_lower", "padding", "invalid_padding")]
        lines.append(f"| {category} | {len(source)}/{sum(source.values())} | {gaps['length_cdf']:.4f} | {dist(a['shape'],b['shape'])} | {dist(a['classes'],b['classes'])} | {pct(a['longest_first'],b['longest_first'])} | {gaps['longest_cdf']:.4f} | " + " | ".join(scalar) + " | " + "/".join(map(str, plain_fail)) + " |")
        rows.append((category, a, b, gaps))
    lines.extend(["", "## Full length distributions", "", "| Category | Length: train/generated % |", "|---|---|"])
    for category, a, b, _ in rows:
        lines.append(f"| {category} | {dist(a['length'],b['length'])} |")
    lines.extend(["", "## Shape-conditional run audit", "", "| Category / shape (>=30 distinct values) | Train/generated pairs | Longest first T/G | Position CDF gap | Starts >=5 digits T/G | Rigid CVC T/G |", "|---|---:|---:|---:|---:|---:|"])
    for category, source in sorted(training().full.items()):
        if not p.is_free(category): continue
        for shape in p.SHAPES:
            a, b = by_shape(source,shape), by_shape(generated(category),shape)
            if len(a)<30: continue
            x, y, gaps = comparison(a,b)
            lines.append(f"| {category} / {shape} | {sum(a.values())}/{sum(b.values())} | {pct(x['longest_first'],y['longest_first'])} | {gaps['longest_cdf']:.4f} | {pct(x['starts_5_digits'],y['starts_5_digits'])} | {pct(x['rigid_cvc'],y['rigid_cvc'])} |")
    lines.extend(["", "## Small-category decisions and padding repairs", "", p.summary(document(),training()), "",
                  "The only exact length changes repair malformed source padding by adding 1..3 body characters; there are 14 such original pairs (6 Key, 8 Token), or 28 contributions across profiles after singleton pooling.", "",
                  "| Category with <5 distinct values | Distinct/pairs | Choice | Own distance | Closest other singleton | Other distance |", "|---|---:|---|---:|---|---:|"])
    singletons = {c:v for c,v in training().full.items() if p.is_free(c) and ':' not in c and len(v)>=2}
    for category, source in sorted(training().full.items()):
        if not p.is_free(category) or len(source)>=5: continue
        eligible = {c:v for c,v in singletons.items() if c != category}
        closest = min(eligible, key=lambda c:(p.profile_distance(source,eligible[c]),c))
        fallback = document()['fallbacks'].get(category)
        choice = ('pool with '+fallback['singleton']) if fallback else 'own skeletons'
        lines.append(f"| {category} | {len(source)}/{sum(source.values())} | {choice} | {0 if not fallback else 'n/a'} | {closest} | {p.profile_distance(source,eligible[closest]):.4f} |")
    lines.extend(["", "## Independent uniform reference for run metrics", "",
                  "T/R/G = train / independent reference / generated; tests allow 5.5 percentage points around the reference, plus its measured difference from train when comparing directly to train.", "",
                  "| Category | Longest first T/R/G % | Starts >=5 digits T/R/G % | Position CDF train/generated | Position CDF reference/generated |", "|---|---:|---:|---:|---:|"])
    for category, a, b, gaps in rows:
        ref=metrics(uniform_reference(category))
        first='/'.join(f"{100*x['longest_first']:.2f}" for x in (a,ref,b))
        prefix='/'.join(f"{100*x['starts_5_digits']:.2f}" for x in (a,ref,b))
        lines.append(f"| {category} | {first} | {prefix} | {gaps['longest_cdf']:.4f} | {p.cdf_gap(ref['longest_position'],b['longest_position']):.4f} |")
    lines.extend(["",
                  "## All-split collision audit", "", f"{COLLISION_DRAWS:,} draws for each of {len(document()['profiles'])} categories; every gold value of length >=6 in train/val/test is tested against its analytic sampler probability.",
                  "Exact public dictionary weights, primitive repeated-block counts, counting-sequence choices and uniform alphabets define chance; the binomial Chernoff bound has family-wise alpha 0.001 across all gold values and profiles.",
                  "| Category | Distinct gold hits | Total gold hits | Minimum log chance-tail bound |", "|---|---:|---:|---:|"])
    collision_rows, failures = collision_audit()
    for category, unique, total, tail in collision_rows:
        lines.append(f"| {category} | {unique} | {total} | {tail:.4f} |")
    lines.extend(["", f"Unexpected gold reproduction failures: {len(failures)}."])
    lines.extend(["", "## Validation commands and output", "", "```text",
                  p.BUILD_COMMAND,
                  "python3 -B -m unittest discover -s metric-detection/scripts -p test_creddata_category_profiles.py -v",
                  "python3 -B metric-detection/scripts/test_creddata_category_profiles.py --report runs/creddata-source-fullfile/category_profiles_v2_review.md",
                  "```"])
    for name in ("category_profiles_v2_tests.txt", "category_profiles_v2_without_inputs_tests.txt", "category_profiles_v2_review3_baseline_tests.txt"):
        log = p.DEFAULT_OUTPUT.parent / name
        if log.exists():
            lines.extend(["", f"{name}:", "", "```text", log.read_text(encoding="utf-8").strip(), "```"])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n",encoding="utf-8")
    numeric = dict(review3=review_numeric, composition={category: dict(train=a, generated=b, gaps=g) for category,a,b,g in rows})
    path.with_suffix('.json').write_text(json.dumps(numeric,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(f"Wrote {path} and {path.with_suffix('.json')}; collision failures={len(failures)}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--report":
        report(sys.argv[2])
    else:
        unittest.main()
