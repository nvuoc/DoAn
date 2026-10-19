"""Offline integrity and design-fixture checks for the vanuoc document package.

This validates artifacts, not the unimplemented conversation engine. No network,
production database, package installation or runtime imports are performed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import unquote


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def markdown_headings(text: str):
    fenced = False
    for line_number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(('```', '~~~')):
            fenced = not fenced
            continue
        if not fenced:
            match = re.match(r'^(#{1,6})\s+(.+?)\s*#*$', line)
            if match:
                yield {'line': line_number, 'level': len(match[1]), 'heading': match[2]}


def slug(text: str) -> str:
    text = re.sub(r'<[^>]*>', '', text).lower().replace('`', '')
    text = re.sub(r'[^\w\-\s]', '', text, flags=re.UNICODE)
    return re.sub(r'\s', '-', text)


def check_package(root: Path, require_schema: bool):
    errors = []
    stats = Counter()

    def check(condition: bool, message: str):
        stats['assertions'] += 1
        if not condition:
            errors.append(message)

    required = ['README.md', 'PLAN_HOP_NHAT.md', 'SOURCE_MANIFEST.json',
                'SOURCE_COVERAGE.json', 'PACKAGE_MANIFEST.json',
                'decisions/OPEN_DECISIONS.md', 'data/original-64.jsonl',
                'examples/storage-target.sql', 'examples/scenarios.jsonl']
    for relative in required:
        check((root / relative).is_file(), f'Missing required file: {relative}')

    parsed = {}
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        stats['files'] += 1
        try:
            text = path.read_text(encoding='utf-8-sig')
            check('\ufffd' not in text, f'{relative}: replacement Unicode character')
        except UnicodeError as exc:
            check(False, f'{relative}: UTF-8 decoding failed: {exc}')
            continue
        if path.suffix == '.json':
            try:
                parsed[relative] = json.loads(text)
                stats['json_files'] += 1
            except ValueError as exc:
                check(False, f'{relative}: JSON parse failed: {exc}')
        elif path.suffix == '.jsonl':
            rows = []
            for index, line in enumerate(text.splitlines(), 1):
                if not line.strip():
                    check(False, f'{relative}:{index}: blank JSONL row')
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError as exc:
                    check(False, f'{relative}:{index}: JSON parse failed: {exc}')
            parsed[relative] = rows
            stats['jsonl_files'] += 1
            stats['jsonl_rows'] += len(rows)
        if relative.startswith(('sources/', 'validation/')) or path.suffix != '.md':
            continue
        stats['normative_markdown_files'] += 1
        check(not re.search(r'\b(?:TODO|TBD|FIXME)\b|\[(?:[Đđ]iền|chưa điền)[^\]]*\]', text),
              f'{relative}: unfinished placeholder')
        check('??' not in text, f'{relative}: suspicious lost Unicode (double question marks)')
        # Strip fenced code so examples of link syntax and paths are not links.
        prose = re.sub(r'(?ms)^\s*(```|~~~).*?^\s*\1\s*$', '', text)
        for match in re.finditer(r'(?<!!)\[[^\]\n]+\]\(([^\n]+?)\)', prose):
            target = match[1].strip()
            if target.startswith('<') and target.endswith('>'):
                target = target[1:-1]
            if re.match(r'^(?:https?://|mailto:)', target):
                stats['external_links_unchecked'] += 1
                continue
            if re.match(r'^(?:[A-Za-z]:|/|file:)', target):
                check(False, f'{relative}: nonportable absolute link: {target}')
                continue
            file_part, _, anchor = unquote(target).partition('#')
            destination = (path.parent / file_part).resolve() if file_part else path.resolve()
            check(destination.is_relative_to(root), f'{relative}: link escapes package: {target}')
            check(destination.is_file(), f'{relative}: missing relative link: {target}')
            stats['relative_links'] += 1
            if anchor and destination.is_file() and destination.suffix == '.md':
                counts = Counter()
                anchors = set()
                for heading in markdown_headings(destination.read_text(encoding='utf-8-sig')):
                    base = slug(heading['heading'])
                    ordinal = counts[base]
                    counts[base] += 1
                    anchors.add(base if ordinal == 0 else f'{base}-{ordinal}')
                check(anchor in anchors, f'{relative}: missing Markdown anchor: {target}')

    source_manifest = parsed.get('SOURCE_MANIFEST.json', {})
    for item in source_manifest.get('sources', []):
        path = root / item['archived_path']
        check(path.is_file() and sha256(path) == item['sha256'],
              f'Source archive checksum: {item["archived_path"]}')
        stats['source_checksums'] += 1
    coverage = parsed.get('SOURCE_COVERAGE.json', {})
    source_rows = coverage.get('headings', [])
    expected = []
    for name in ('PLAN.md', 'PLAN_BONUS.md'):
        path = root / 'sources' / name
        if path.is_file():
            expected += [(name, h['line'], h['heading']) for h in markdown_headings(path.read_text(encoding='utf-8-sig'))]
    actual = [(r.get('source'), r.get('line'), r.get('heading')) for r in source_rows]
    check(Counter(actual) == Counter(expected), 'Every source heading must be mapped exactly once')
    for row in source_rows:
        check(bool(row.get('disposition')), f'Source heading without disposition: {row}')
        check((root / row['destination']).is_file(), f'Missing coverage destination: {row}')
    stats['mapped_source_headings'] = len(source_rows)

    archived_plan = root / 'sources' / 'PLAN.md'
    original = []
    if archived_plan.is_file():
        for line in archived_plan.read_text(encoding='utf-8-sig').splitlines():
            match = re.match(r'^\|\s*(\d+)\s*\|\s*(.*?)\s*\|', line)
            if match:
                original.append((int(match[1]), match[2]))
    # Select the appendix table, not numbered examples outside it.
    original = [(number, text) for number, text in original if 1 <= number <= 64]
    seeds = parsed.get('data/original-64.jsonl', [])
    seed_texts = [s.get('original_text', s.get('raw_utterance', s.get('text'))) for s in seeds]
    check(len(original) == 64 and [n for n, _ in original] == list(range(1, 65)),
          'Source appendix must contain exactly numbered original64 rows')
    check(len(seeds) == 64 and seed_texts == [text for _, text in original],
          'Extracted 64 seed utterances must be unchanged and in order')
    stats['original_seeds'] = len(seeds)

    scenarios = parsed.get('examples/scenarios.jsonl', [])
    check(len(scenarios) >= 12, 'At least twelve designed synthetic scenarios are required')
    scenario_ids = [s.get('scenario_id') for s in scenarios]
    check(len(scenario_ids) == len(set(scenario_ids)), 'Scenario IDs must be unique')
    seed_ids = {s.get('seed_id') for s in seeds}
    for scenario in scenarios:
        label = scenario['scenario_id']
        timeline = scenario['timeline']
        event_ids = [e['event_id'] for e in timeline]
        check(len(event_ids) == len(set(event_ids)), f'{label}: event IDs must be unique')
        user_events = {e['event_id'] for e in timeline if e['kind'] == 'user_turn'}
        proposal_ids = set(scenario['fixtures'].get('nlu_proposals', {}))
        check(proposal_ids <= user_events, f'{label}: proposal fixture must reference a user event')
        for assertion in scenario['oracle']['assertions']:
            check(assertion['at'] == 'final' or assertion['at'] in event_ids, f'{label}: assertion event missing')
            if 'baseline_event' in assertion:
                check(assertion['baseline_event'] == 'initial' or assertion['baseline_event'] in event_ids,
                      f'{label}: assertion baseline event missing')
            stats['scenario_assertions'] += 1
        check(set(scenario.get('seed_ids', [])) <= seed_ids, f'{label}: source seed ID missing')
        check(scenario['review']['gold'] is False and scenario['review']['execution_status'] == 'not_run_on_new_core',
              f'{label}: designed cases cannot claim gold or engine execution')
    stats['designed_scenarios'] = len(scenarios)

    schema_files = {name: value for name, value in parsed.items() if name.startswith('schemas/')}
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError:
        check(not require_schema, 'jsonschema unavailable; full schema validation required')
        stats['schema_validation_available'] = 0
    else:
        stats['schema_validation_available'] = 1
        checker = FormatChecker()

        @checker.checks('date-time')
        def valid_datetime(value):
            if not isinstance(value, str):
                return True
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})', value):
                return False
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00').replace('z', '+00:00')).tzinfo is not None
            except ValueError:
                return False
        validators = {}
        for name, schema in schema_files.items():
            try:
                Draft202012Validator.check_schema(schema)
                validators[name] = Draft202012Validator(schema, format_checker=checker)
                stats['schemas'] += 1
            except Exception as exc:
                check(False, f'{name}: invalid schema: {exc}')
        assignments = [
            ('examples/turn-input.json', 'schemas/turn-input.schema.json'),
            ('examples/turn-result.json', 'schemas/turn-result.schema.json'),
            ('examples/delivery-event.json', 'schemas/control-event.schema.json'),
        ]
        assignments += [('examples/scenarios.jsonl', 'schemas/scenario.schema.json')]
        for example_name, schema_name in assignments:
            check(example_name in parsed, f'Missing parsed example: {example_name}')
            check(schema_name in validators, f'Missing validator: {schema_name}')
            if example_name not in parsed or schema_name not in validators:
                continue
            values = parsed[example_name] if example_name.endswith('.jsonl') else [parsed[example_name]]
            for index, value in enumerate(values, 1):
                failures = sorted(validators[schema_name].iter_errors(value), key=lambda e: str(e.path))
                check(not failures, f'{example_name}:{index}: ' + '; '.join(e.message for e in failures[:4]))
                stats['schema_validated_examples'] += 1

        negative_cases = [
            ('examples/turn-input.json', 'schemas/turn-input.schema.json', lambda v: v.update(kind='timeout'), 'user text cannot select control kind'),
            ('examples/turn-input.json', 'schemas/turn-input.schema.json', lambda v: v.update(text=''), 'empty original text'),
            ('examples/turn-input.json', 'schemas/turn-input.schema.json', lambda v: v.update(untrusted_extra=True), 'unknown input field'),
            ('examples/turn-input.json', 'schemas/turn-input.schema.json', lambda v: v.update(received_at='yesterday'), 'invalid timestamp'),
            ('examples/turn-input.json', 'schemas/turn-input.schema.json', lambda v: v['trusted']['input_timing'].update(basis='text_adapter'), 'voice source cannot claim text timing basis'),
            ('examples/turn-result.json', 'schemas/turn-result.schema.json', lambda v: v.update(status='booked_real'), 'unknown outcome status'),
            ('examples/turn-result.json', 'schemas/turn-result.schema.json', lambda v: v.update(response=None), 'committed result without response'),
            ('examples/turn-result.json', 'schemas/turn-result.schema.json', lambda v: v.update(new_commit=False), 'committed result cannot deny new commit'),
            ('examples/delivery-event.json', 'schemas/control-event.schema.json', lambda v: v.update(kind='arbitrary_tool'), 'unknown control event'),
            ('examples/delivery-event.json', 'schemas/control-event.schema.json', lambda v: v.update(extra='injected'), 'unknown control field'),
            ('examples/delivery-event.json', 'schemas/control-event.schema.json', lambda v: v['payload'].update(playback_id=None), 'voice playback completion lacks identity'),
        ]
        for example_name, schema_name, mutate, reason in negative_cases:
            if example_name not in parsed or schema_name not in validators:
                continue
            candidate = deepcopy(parsed[example_name])
            mutate(candidate)
            check(bool(list(validators[schema_name].iter_errors(candidate))), f'Negative schema case accepted: {reason}')
            stats['negative_schema_cases'] += 1

    turn_input = parsed.get('examples/turn-input.json', {})
    if turn_input:
        hash_keys = ['schema_version', 'kind', 'session_id', 'request_id', 'draft_id',
                     'turn_id', 'input_id', 'source', 'text']
        business_payload = {k: turn_input[k] for k in hash_keys}
        canonical = json.dumps(business_payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        check(hashlib.sha256(canonical.encode('utf-8')).hexdigest() == turn_input['trusted']['input_hash'],
              'Illustrative TurnInput hash must match original Unicode payload')
    turn_result = parsed.get('examples/turn-result.json', {})
    response = turn_result.get('response') or {}
    if response:
        segments = response.get('segments', [])
        check(response['final_text'] == ' '.join(s['text'] for s in segments), 'Illustrative final_text must join exact segments')
        check(len({s['segment_id'] for s in segments}) == len(segments), 'Illustrative segments have unique IDs')
        question_segments = [s for s in segments if s['kind'] == 'question']
        check(len(question_segments) <= 1, 'At most one offered question in illustrative response')
        question = response.get('question')
        if question:
            check(len(question_segments) == 1 and question['segment_id'] == question_segments[0]['segment_id'],
                  'Illustrative question points to correct segment')
        event = parsed.get('examples/delivery-event.json', {})
        if event:
            payload = event['payload']
            check(payload['response_id'] == response['response_id'] and payload['segment_id'] in {s['segment_id'] for s in segments},
                  'Illustrative delivery references current example output')

    for relative, value in parsed.items():
        if not relative.startswith(('examples/', 'data/')):
            continue
        def strings(item):
            if isinstance(item, str):
                yield item
            elif isinstance(item, dict):
                for child in item.values():
                    yield from strings(child)
            elif isinstance(item, list):
                for child in item:
                    yield from strings(child)
        for value_text in strings(value):
            check('??' not in value_text, f'{relative}: suspicious lost Unicode in fixture')

    sql = root / 'examples' / 'storage-target.sql'
    if sql.is_file():
        try:
            connection = sqlite3.connect(':memory:')
            connection.executescript(sql.read_text(encoding='utf-8-sig'))
            check(not connection.execute('PRAGMA foreign_key_check').fetchall(), 'Illustrative SQL foreign key check')
            check(connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Illustrative SQL integrity check')
            stats['sql_tables'] = connection.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
            connection.close()
        except sqlite3.Error as exc:
            check(False, f'Illustrative SQL failed in RAM: {exc}')

    manifest = parsed.get('PACKAGE_MANIFEST.json', {})
    included = set()
    for item in manifest.get('files', []):
        relative = item['path']
        included.add(relative)
        path = root / relative
        check(path.is_file() and sha256(path) == item['sha256'], f'Package checksum: {relative}')
        stats['package_checksums'] += 1
    excluded = set(manifest.get('excluded_from_checksums', []))
    actual_files = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    check(actual_files == included | excluded, 'Manifest file coverage: unlisted or missing file')
    check(len(included) == len(manifest.get('files', [])), 'Manifest duplicate paths')
    return {'status': 'PASS' if not errors else 'FAIL',
            'checked_at': datetime.now(timezone(timedelta(hours=7))).isoformat(),
            'scope': 'artifact integrity, schema and illustrative fixtures only; not core runtime acceptance',
            'statistics': dict(stats), 'errors': errors,
            'not_run': ['new core runtime tests (core not implemented)', 'provider live', 'audio integration',
                        'production migration/deploy', 'external source URL verification']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--require-schema-validation', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = check_package(args.root.resolve(), args.require_schema_validation)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + '\n', encoding='utf-8')
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
