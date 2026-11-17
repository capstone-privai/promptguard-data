"""Offline audit of instantiated bilingual CredData task environments. No agent runs, no API calls.

Checks the frozen catalog against its instances: Korean/English pairs share source, split, component,
rendered source bytes and injected values; families and instruction languages are balanced; no placeholder
is left; every registry span decodes to its value; and the rendered source, passed through the rollout
labeler as a tool output, keeps every known source span. This covers known source gold only. It does not
show that unregistered secrets are annotated, and it is not a task-success or agent-behaviour check.
The record goes under the mutable instances/ directory, so the frozen catalog comparison is unaffected.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import re
import sys

import creddata_tasks as T
import creddata_rollout as R
import convert_trajectory as C

HANGUL = re.compile(r"[가-힣]")
UNFILLED = re.compile(r"\{source_file\}|\{source_language\}")
PAIR_FIELDS = ("family", "split", "component_id", "source_repo_id", "source_session_id", "source_item_id",
               "source_item_sha256", "source_file", "source_line_range", "source_filename", "language",
               "source_language", "syntax_mode", "slots", "occurrences", "source_license")


def tree(path: Path) -> dict[str, bytes]:
    return {str(p.relative_to(path)): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}


def audit(root: Path, instances: Path, split_dir: Path = T.DEFAULT_SPLIT) -> dict:
    failures = []

    def check(ok: bool, task_id: str, name: str):
        if not ok:
            failures.append({"task": task_id, "check": name})
        return ok

    config = json.loads((root / "tasks.json").read_text())
    specs = {t["task_id"]: t for t in config["tasks"]}
    pack = root / "templates"
    manifest = json.loads((split_dir / "manifest.json").read_text())
    inputs = {name: T.ROOT / record["path"] for name, record in manifest["inputs"].items()}
    train = set((split_dir / "train.txt").read_text().splitlines())
    repos = {r["group_id"]: r for r in T.rows(split_dir / "repositories.jsonl")}
    wanted = {t["source_session_id"] for t in specs.values()}
    sessions = {s["session_id"]: s for s in T.rows(inputs["sessions"]) if s["session_id"] in wanted}
    gold = defaultdict(list)
    for row in T.rows(inputs["gold"]):
        if row["session_id"] in wanted:
            gold[(row["session_id"], row["item_id"])].append(row["span"])

    # Catalog: the frozen templates are what the current code builds from tasks.json.
    check(tree(pack) == T.build_pack(root / "tasks.json", split_dir), "*", "catalog_rebuild_byte_identical")
    on_disk = {p.name for p in instances.iterdir() if (p / "task.json").is_file()}
    check(on_disk == set(specs), "*", "instances_match_catalog_tasks")
    cells = Counter((t["family"], t["instruction_language"]) for t in specs.values())
    check(set(cells) == {(f, l) for f in T.FAMILIES for l in ("ko", "en")} and len(set(cells.values())) == 1,
          "*", "family_and_instruction_language_balanced")

    tasks, registries, sources, stats = {}, {}, {}, Counter()
    redraws, projection_misses, by_language = [], [], defaultdict(Counter)
    for task_id in sorted(on_disk & set(specs)):
        inst = instances / task_id
        task = json.loads((inst / "task.json").read_text())
        registry = json.loads((inst / "private/registry.json").read_text())
        text = (inst / "workspace" / task["source_filename"]).read_text()
        tasks[task_id], registries[task_id], sources[task_id] = task, registry, text
        by_language[task["family"]][task["language"]] += 1

        check(task == json.loads((pack / task_id / "task.json").read_text()), task_id, "task_equals_catalog_template")
        check(tree(inst) == T.instantiate(pack, task_id, registry["seed"]), task_id, "instantiate_is_deterministic")
        # Source identity and the frozen partition.
        session = sessions[task["source_session_id"]]
        item = next(i for i in session["items"] if i["item_id"] == task["source_item_id"])
        repo = repos[session["meta"]["group_id"]]
        check(task["split"] == "train" and task["source_session_id"] in train and repo["split"] == "train",
              task_id, "train_membership")
        check(task["component_id"] == repo["component_id"] and task["source_repo_id"] == repo["repo_id"],
              task_id, "component_and_repository_inherited")
        check(task["source_item_sha256"] == T.sha(item["text"].encode()), task_id, "source_excerpt_unchanged")
        # Placeholders stand exactly on the known source gold, and nothing else in the excerpt changed.
        template = (pack / task_id / "workspace" / task["source_filename"]).read_text()
        rebuilt, cursor = [], 0
        for occurrence in task["occurrences"]:
            rebuilt += [template[cursor:occurrence["start"]], item["text"][occurrence["source_start"]:occurrence["source_end"]]]
            cursor = occurrence["end"]
        check("".join(rebuilt) + template[cursor:] == item["text"], task_id, "template_restores_source_excerpt")
        check(sorted((o["source_start"], o["source_end"]) for o in task["occurrences"]) ==
              sorted((s["start"], s["end"]) for s in gold[(session["session_id"], item["item_id"])]),
              task_id, "placeholders_cover_all_known_source_gold")
        # Complete substitution, in the right natural language.
        workspace = {p.name: p.read_text() for p in (inst / "workspace").iterdir() if p.is_file()}
        check(not any(T.PLACEHOLDER.search(v) or UNFILLED.search(v) for v in workspace.values()),
              task_id, "no_placeholder_left")
        request = workspace["request.md"]
        check(task["source_filename"] in request and task["rendered_instruction"] in request
              and T.L.LABELS[task["language"]] in request, task_id, "request_names_source_file_and_language")
        korean = bool(HANGUL.search(request + workspace["README.md"]))
        check(korean == (task["instruction_language"] == "ko"), task_id, "request_language_matches")
        check(task["source_language"] == task["language"] == T.L.language_for(task["source_file"]),
              task_id, "source_language_recorded")
        # Registry spans decode to the injected values.
        annotations = registry["source_annotations"]
        check(registry["source_sha256"] == T.sha(text.encode()), task_id, "registry_source_hash")
        check(set(registry["values"]) == set(task["slots"]) and len(annotations) == len(task["occurrences"])
              and [a["secret_id"] for a in annotations] == [o["secret_id"] for o in task["occurrences"]],
              task_id, "registry_covers_every_slot_and_occurrence")
        check(all(T.decode_fragment(text[a["start"]:a["end"]], a["codec"]) == registry["values"][a["secret_id"]]
                  for a in annotations), task_id, "registry_spans_decode_to_values")
        if registry.get("source_rule_redraws"):
            redraws.append({"task_id": task_id, "redraws": registry["source_rule_redraws"]})
        # Projection: the labeler the rollout uses must keep every known source span.
        file_path = str(inst / "workspace" / task["source_filename"])
        items = [C.Item("t0", "tool_output", text, "Read", {"file_path": file_path})]
        _, labeled, _, _ = R.label_items(task, registry, items, "preflight")
        found = {(g["span"]["start"], g["span"]["end"]) for g in labeled}
        known = {(a["start"], a["end"]) for a in annotations}
        stats["source_spans"] += len(known)
        stats["projected_exactly"] += len(known & found)
        stats["additional_labeled_spans"] += len(found - known)
        for start, end in sorted(known - found):
            covered = any(a <= start and end <= b for a, b in found)
            projection_misses.append({"task_id": task_id, "start": start, "end": end,
                                      "kind": "different_boundary" if covered else "not_labeled"})
        check(known <= found, task_id, "source_span_projection_preserved")

    # Pairs: the two natural-language variants are the same environment apart from the wording.
    pairs = defaultdict(dict)
    for task_id, task in tasks.items():
        pairs[task["task_pair_id"]][task["instruction_language"]] = task_id
    for pair_id, members in sorted(pairs.items()):
        if not check(set(members) == {"ko", "en"}, pair_id, "pair_has_ko_and_en"):
            continue
        ko, en = members["ko"], members["en"]
        check(all(tasks[ko].get(f) == tasks[en].get(f) for f in PAIR_FIELDS), pair_id, "pair_shares_source_metadata")
        check(sources[ko].encode() == sources[en].encode(), pair_id, "pair_shares_rendered_source_bytes")
        check(all(registries[ko][f] == registries[en][f] for f in ("values", "source_annotations", "seed", "source_sha256")),
              pair_id, "pair_shares_injected_values_and_spans")
        check(tasks[ko]["rendered_instruction"] != tasks[en]["rendered_instruction"], pair_id, "pair_wording_differs")

    base = [t for t in tasks.values() if t["instruction_language"] == "ko"]
    return {
        "catalog": config["version"], "instances": os.path.relpath(instances, T.ROOT),
        "seeds": sorted({r["seed"] for r in registries.values()}),
        "environments": len(tasks), "task_pairs": len(pairs),
        "by_family_and_instruction_language": {f: {l: cells[(f, l)] for l in ("ko", "en")} for f in T.FAMILIES},
        "source_language_by_family": {f: dict(sorted(by_language[f].items())) for f in T.FAMILIES},
        "base_source_files": len({t["source_session_id"] for t in base}),
        "base_source_excerpts": len({(t["source_session_id"], t["source_item_id"]) for t in base}),
        "base_source_repositories": len({t["source_repo_id"] for t in base}),
        "components": len({t["component_id"] for t in base}),
        "source_spans_verified": stats["source_spans"],
        "source_spans_projected_exactly": stats["projected_exactly"],
        "source_label_projection_misses": projection_misses,
        "additional_labeled_spans": stats["additional_labeled_spans"],
        "value_redraw_instances": redraws,
        "checks_failed": failures, "passed": not failures, "agent_runs": 0, "api_calls": 0,
        "scope": "Known source gold only. Completeness of annotation, task quality and agent behaviour are not checked. "
                 "Projection uses the raw rendered source as one tool output; real tool output may reformat it.",
    }


def numbered(text: str, style: str) -> tuple[str, list[int]]:
    """The file as a tool prints it with line numbers, and the rendered offset of every original offset (end too).
    cat_n: right-aligned number and a tab, as the Read tool and cat -n print it; grep_n: N: as grep -n prints it."""
    lines = text.split("\n")
    trailing = lines[-1] == ""
    if trailing:
        lines.pop()
    out, offsets, length = [], [], 0
    for n, line in enumerate(lines, 1):
        prefix = f"{n:>6}\t" if style == "cat_n" else f"{n}:"
        offsets.extend(range(length + len(prefix), length + len(prefix) + len(line) + 1))
        out.append(prefix + line)
        length += len(prefix) + len(line) + 1
    rendered = "\n".join(out) + ("\n" if trailing else "")
    offsets = offsets[:len(text)] + [len(rendered)]
    return rendered, offsets


RENDERINGS = ("raw", "cat_n", "grep_n")


def project_renderings(task: dict, registry: dict, text: str):
    """(rendering, annotation, result, additional spans in that rendering) of the rendered file read as one tool
    output; result is labeled_exactly, different_type, different_boundary or not_labeled."""
    annotations = registry["source_annotations"]
    for rendering in RENDERINGS:
        shown, offsets = (text, list(range(len(text) + 1))) if rendering == "raw" else numbered(text, rendering)
        items = [C.Item("t0", "tool_output", shown, "Read", {"file_path": task["source_filename"]})]
        _, labeled, _, _ = R.label_items(task, registry, items, "preflight")
        found = {(g["span"]["start"], g["span"]["end"]): g["span"]["type"] for g in labeled}
        expected = [(offsets[a["start"]], offsets[a["end"] - 1] + 1) for a in annotations]
        extra = len(set(found) - set(expected))
        for a, span in zip(annotations, expected):
            result = ("labeled_exactly" if found.get(span) == a["source_type"] else "different_type" if span in found
                      else "different_boundary" if any(s <= span[0] and span[1] <= e for s, e in found)
                      else "not_labeled")
            yield rendering, a, result, extra if a is annotations[0] else 0


def audit_candidates(root: Path, seed: str) -> dict:
    """Every eligible file of a whole-file catalog, not only the selected ones: per-slot value draws (with the
    redraw counts by check, category and position), category conformance, syntax and the three-rendering projection."""
    import creddata_fullfile as F
    import creddata_category_formats as formats
    candidates = list(T.rows(root / "eligibility.jsonl"))
    split = json.loads((root / "tasks.json").read_text())["split"]
    sessions, gold, _ = F.load_sources(F.FULLFILE, {c["source_session_id"] for c in candidates}, split)
    draws, rejections, results, failures, conformance = Counter(), Counter(), Counter(), [], Counter()
    for candidate in candidates:
        session = sessions[candidate["source_session_id"]]
        text = session["items"][0]["text"]
        language, _, parsed = F.file_language(session["meta"]["creddata_file"])
        mode = F.syntax_mode(text, language, parsed)
        template, slots, occurrences = F.make_template(text, gold[session["session_id"]], language, mode,
                                                       f"{session['session_id']}:0")
        task = {"task_id": candidate["source_session_id"], "family": "analysis", "split": split,
                "language": language, "syntax_mode": mode, "source_scope": "whole_file", "slots": slots,
                "occurrences": occurrences, "component_id": candidate["component_id"],
                "source_repo_id": candidate["source_repo_id"], "source_session_id": session["session_id"],
                "source_item_id": 0, "source_license": "check", "source_filename": "subject"}
        try:
            values, rendered, annotations, redraws, log = F.sample_rendered_values(task, template, seed)
        except ValueError as error:
            failures.append({"source_session_id": session["session_id"], "error": str(error)})
            continue
        for a in annotations:
            draws[(slots[a["secret_id"]]["type"], a["position"])] += 1
        for row in log:
            rejections[(row["check"], row["category"] if row["check"] != "syntax" else "language:" + row["language"],
                        row["position"])] += 1
        for name, slot in slots.items():
            ok = formats.conforms(slot["type"], values[name]) if slot["format_atom"] else \
                bool(values[name]) and not set(values[name]) & set(slot["avoid"])
            conformance[("fixed_format" if slot["format_atom"] else "profile") + (":pass" if ok else ":fail")] += 1
            if not ok:
                failures.append({"source_session_id": session["session_id"], "error": "value_conformance", "slot": name})
        if not F.still_valid(rendered, language, mode):
            failures.append({"source_session_id": session["session_id"], "error": "syntax_not_preserved"})
        registry = {"values": values, "source_annotations": annotations}
        for rendering, a, result, _ in project_renderings(task, registry, rendered):
            results[(rendering, a["position"], result)] += 1
            if result != "labeled_exactly":
                failures.append({"source_session_id": session["session_id"], "error": "projection_" + rendering,
                                 "position": a["position"], "kind": result})
    by_category = defaultdict(dict)
    for (category, position), n in sorted(draws.items()):
        by_category[category][position] = n
    return {"catalog_root": os.path.relpath(root, T.ROOT), "seed": seed, "eligible_files": len(candidates),
            "files_drawn": len(candidates) - len({f["source_session_id"] for f in failures if "error" in f
                                                   and f["error"].startswith("could not")}),
            "accepted_occurrences_by_category_and_position": dict(sorted(by_category.items())),
            "redraw_rejections": [{"check": c, "category": k, "position": p, "rejections": n}
                                  for (c, k, p), n in sorted(rejections.items())],
            "value_conformance": dict(sorted(conformance.items())),
            "projection": {f"{r}/{p}/{k}": n for (r, p, k), n in sorted(results.items())},
            "failures": failures, "passed": not failures, "agent_runs": 0, "api_calls": 0}


def audit_whole_file(root: Path, instances: Path, split_dir: Path = T.DEFAULT_SPLIT) -> dict:
    """Catalog v3 (whole files, category gold). The excerpt checks adapted, plus value conformance to the category,
    syntax kept after injection, and label projection of the file read raw, with cat -n numbers and as grep -n output."""
    import creddata_fullfile as F
    import creddata_category_formats as formats
    import creddata_category_profiles as profiles
    from label_rules import PEM_BEGIN, pem_has_body
    failures = []

    def check(ok: bool, task_id: str, name: str):
        if not ok:
            failures.append({"task": task_id, "check": name})
        return ok

    config = json.loads((root / "tasks.json").read_text())
    specs = {t["task_id"]: t for t in config["tasks"]}
    pack = root / "templates"
    split = config["split"]
    F.check_manifest(F.FULLFILE, split)
    train = set((split_dir / f"{split}.txt").read_text().splitlines())
    repos = {r["group_id"]: r for r in T.rows(split_dir / "repositories.jsonl")}
    wanted = {t["source_session_id"] for t in specs.values()}
    sessions, gold, _ = F.load_sources(F.FULLFILE, wanted, split)
    dropped = defaultdict(set)
    for row in T.rows(F.input_paths(F.FULLFILE, split)["gold_category"]):
        if row["session_id"] in wanted and "dropped" in row:
            dropped[row["session_id"]].add((row["start"], row["end"]))

    check(tree(pack) == F.build_pack(root / "tasks.json", split_dir), "*", "catalog_rebuild_byte_identical")
    on_disk = {p.name for p in instances.iterdir() if (p / "task.json").is_file()}
    check(on_disk == set(specs), "*", "instances_match_catalog_tasks")
    cells = Counter((t["family"], t["instruction_language"]) for t in specs.values())
    check(set(cells) == {(f, l) for f in T.FAMILIES for l in ("ko", "en")} and len(set(cells.values())) == 1,
          "*", "family_and_instruction_language_balanced")

    tasks, registries, sources, stats = {}, {}, {}, Counter()
    projection, by_language, redraw_log, redraws = defaultdict(Counter), defaultdict(Counter), Counter(), []
    misses, conformance = [], Counter()
    for task_id in sorted(on_disk & set(specs)):
        inst = instances / task_id
        task = json.loads((inst / "task.json").read_text())
        registry = json.loads((inst / "private/registry.json").read_text())
        text = (inst / "workspace" / task["source_filename"]).read_text()
        tasks[task_id], registries[task_id], sources[task_id] = task, registry, text
        by_language[task["family"]][task["language"]] += 1
        check(task == json.loads((pack / task_id / "task.json").read_text()), task_id, "task_equals_catalog_template")
        check(tree(inst) == T.instantiate(pack, task_id, registry["seed"]), task_id, "instantiate_is_deterministic")
        session = sessions[task["source_session_id"]]
        source_text = session["items"][0]["text"]
        repo = repos[session["meta"]["group_id"]]
        check(task["split"] == split and task["source_session_id"] in train and repo["split"] == split,
              task_id, f"{split}_membership")
        check(task["component_id"] == repo["component_id"] and task["source_repo_id"] == repo["repo_id"],
              task_id, "component_and_repository_inherited")
        check(task["source_item_sha256"] == T.sha(source_text.encode()), task_id, "source_file_unchanged")
        template = (pack / task_id / "workspace" / task["source_filename"]).read_text()
        rebuilt, cursor = [], 0
        for occurrence in task["occurrences"]:
            rebuilt += [template[cursor:occurrence["start"]],
                        source_text[occurrence["source_start"]:occurrence["source_end"]]]
            cursor = occurrence["end"]
        check("".join(rebuilt) + template[cursor:] == source_text, task_id, "template_restores_whole_source_file")
        known_gold = {(s["start"], s["end"]) for s in gold[session["session_id"]]}
        placed = [(o["source_start"], o["source_end"]) for o in task["occurrences"]]
        check(len(placed) == len(set(placed)) and set(placed) == known_gold, task_id,
              "placeholders_cover_exactly_the_non_dropped_gold")
        check(not set(placed) & dropped[session["session_id"]], task_id, "dropped_spans_keep_source_text")
        workspace = {p.name: p.read_text() for p in (inst / "workspace").iterdir() if p.is_file()}
        check(not any(T.PLACEHOLDER.search(v) or UNFILLED.search(v) for v in workspace.values()),
              task_id, "no_placeholder_left")
        request = workspace["request.md"]
        check(task["source_filename"] in request and task["rendered_instruction"] in request
              and task["source_language_label"] in request, task_id, "request_names_source_file_and_language")
        check(request.startswith(F.COMMON_EN if task["instruction_language"] == "en" else F.COMMON)
              and ("whole source file" in workspace["README.md"] or "원본 파일 하나 전체" in workspace["README.md"]),
              task_id, "workspace_says_whole_source_file")
        korean = bool(HANGUL.search(request + workspace["README.md"]))
        check(korean == (task["instruction_language"] == "ko"), task_id, "request_language_matches")
        check(all(s["type"] and s["coarse_type"] in {"PASSWORD", "TOKEN", "SECRET", "ACCESS_KEY", "PRIVATE_KEY"}
                  and s["category_source"] in {"creddata", "same_value", "opus", "model"} for s in task["slots"].values()),
              task_id, "slots_carry_category_coarse_type_and_source")
        annotations = registry["source_annotations"]
        values = registry["values"]
        check(registry["source_sha256"] == T.sha(text.encode()), task_id, "registry_source_hash")
        check(set(values) == set(task["slots"]) and [a["secret_id"] for a in annotations] ==
              [o["secret_id"] for o in task["occurrences"]], task_id, "registry_covers_every_slot_and_occurrence")
        check(all(a["source_type"] == task["slots"][a["secret_id"]]["type"] for a in annotations),
              task_id, "registry_span_type_is_category")
        check(all(F.decode(text[a["start"]:a["end"]], a["codec"]) == values[a["secret_id"]] for a in annotations),
              task_id, "registry_spans_decode_to_values")
        # (i) every value conforms to its category.
        for name, slot in task["slots"].items():
            value = values[name]
            if slot["format_atom"]:
                ok = formats.conforms(slot["type"], value)
                kind = "fixed_format_conforms"
            else:
                try:
                    profiles.profile_for(slot["type"])
                    ok = bool(value) and not set(value) & set(slot["avoid"])
                except KeyError:
                    ok = False
                kind = "profile_value_avoids_context"
            conformance[kind + (":pass" if ok else ":fail")] += 1
            check(ok, task_id, "value_conforms_to_category")
        for a in annotations:
            if a["codec"] == "pem":
                check(bool(PEM_BEGIN.match(text, a["start"])) and pem_has_body(text[a["start"]:a["end"]]),
                      task_id, "pem_block_is_a_labelable_key")
        # (ii) syntax of a parsed language that was valid before injection is still valid.
        check(F.still_valid(text, task["language"], task["syntax_mode"]), task_id, "syntax_preserved_after_injection")
        # (iii) projection through the rollout labeler in three renderings.
        for rendering, a, result, extra in project_renderings(task, registry, text):
            projection[(rendering, a["position"])]["spans"] += 1
            stats["additional_labeled_spans_" + rendering] += extra
            if result == "labeled_exactly":
                projection[(rendering, a["position"])]["labeled_exactly"] += 1
            else:
                misses.append({"task_id": task_id, "rendering": rendering, "position": a["position"],
                               "category": a["source_type"], "kind": result})
                check(False, task_id, "source_span_projection_" + rendering)
        stats["source_spans"] += len(annotations)
        if registry.get("source_rule_redraws"):
            redraws.append({"task_id": task_id, "redraws": registry["source_rule_redraws"]})
            for row in registry["redraw_log"]:
                redraw_log[(row["check"], row["category"] if row["check"] != "syntax" else "language:" + row["language"],
                            row["position"])] += 1

    pairs = defaultdict(dict)
    for task_id, task in tasks.items():
        pairs[task["task_pair_id"]][task["instruction_language"]] = task_id
    for pair_id, members in sorted(pairs.items()):
        if not check(set(members) == {"ko", "en"}, pair_id, "pair_has_ko_and_en"):
            continue
        ko, en = members["ko"], members["en"]
        check(all(tasks[ko].get(f) == tasks[en].get(f) for f in PAIR_FIELDS + ("source_scope",)),
              pair_id, "pair_shares_source_metadata")
        check(sources[ko].encode() == sources[en].encode(), pair_id, "pair_shares_rendered_source_bytes")
        check(all(registries[ko][f] == registries[en][f] for f in ("values", "source_annotations", "seed", "source_sha256")),
              pair_id, "pair_shares_injected_values_and_spans")
        check(tasks[ko]["rendered_instruction"] != tasks[en]["rendered_instruction"], pair_id, "pair_wording_differs")

    base = [t for t in tasks.values() if t["instruction_language"] == "ko"]
    category_spans, position_spans = Counter(), Counter()
    seen = set()
    for t in base:
        if t["source_session_id"] in seen:
            continue
        seen.add(t["source_session_id"])
        for o in t["occurrences"]:
            category_spans[t["slots"][o["secret_id"]]["type"]] += 1
            position_spans[o["position"]] += 1
    return {
        "catalog": config["version"], "instances": os.path.relpath(instances, T.ROOT),
        "seeds": sorted({r["seed"] for r in registries.values()}),
        "environments": len(tasks), "task_pairs": len(pairs),
        "by_family_and_instruction_language": {f: {l: cells[(f, l)] for l in ("ko", "en")} for f in T.FAMILIES},
        "source_language_by_family": {f: dict(sorted(by_language[f].items())) for f in T.FAMILIES},
        "base_source_files": len(seen), "base_source_repositories": len({t["source_repo_id"] for t in base}),
        "components": len({t["component_id"] for t in base}),
        "gold_spans_in_selected_files_by_category": dict(sorted(category_spans.items(), key=lambda kv: (-kv[1], kv[0]))),
        "gold_spans_in_selected_files_by_position": dict(sorted(position_spans.items())),
        "source_spans_verified": stats["source_spans"],
        "projection": {f"{r}/{p}": dict(c) for (r, p), c in sorted(projection.items())},
        "source_label_projection_misses": misses,
        "additional_labeled_spans": {r: stats["additional_labeled_spans_" + r] for r in RENDERINGS},
        "value_conformance": dict(sorted(conformance.items())),
        "value_redraw_instances": redraws,
        "value_redraw_rejections": [{"check": c, "category": cat, "position": pos, "rejections": n}
                                    for (c, cat, pos), n in sorted(redraw_log.items())],
        "multi_line_extent": "A value interrupted by line-number prefixes (a re-laid PEM block or JWK fragment over "
                             "several lines) is labeled as one span from its first to its last character; the "
                             "prefixes between its lines are inside the span.",
        "checks_failed": failures, "passed": not failures, "agent_runs": 0, "api_calls": 0,
        "scope": "Known non-dropped source gold only. Completeness of annotation, task quality and agent behaviour are "
                 "not checked. Projection reads the rendered file as one tool output: raw, with cat -n style numbers "
                 "(the Read tool) and as grep -n output; other tool output formats are not checked.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="generated catalog with tasks.json and templates/")
    parser.add_argument("--instances", type=Path, required=True, help="an instantiated directory under <root>/instances")
    parser.add_argument("--split-dir", type=Path, default=T.DEFAULT_SPLIT)
    parser.add_argument("--all-candidates", action="store_true",
                        help="whole-file catalogs: also draw, check and project every eligible file "
                             "(candidates_check.json next to preflight.json)")
    args = parser.parse_args()
    root, instances = args.root.resolve(), args.instances.resolve()
    if instances.parent != root / "instances":
        parser.error("--instances must be a directory directly under <root>/instances")
    whole_file = json.loads((root / "tasks.json").read_text()).get("source_scope") == "whole_file"
    report = (audit_whole_file if whole_file else audit)(root, instances, args.split_dir)
    (instances / "preflight.json").write_bytes(T.jb(report))
    if args.all_candidates and whole_file:
        seed = report["seeds"][0] if report["seeds"] else instances.name
        everything = audit_candidates(root, seed)
        (instances / "candidates_check.json").write_bytes(T.jb(everything))
        report["passed"] = report["passed"] and everything["passed"]
        print(json.dumps({k: v for k, v in everything.items() if k != "failures"} |
                         {"failures": len(everything["failures"])}, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "scope"}, ensure_ascii=False, indent=2))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
