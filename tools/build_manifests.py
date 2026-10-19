"""Build local provenance and artifact checksums; never read outside this package."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True

from validate_package import markdown_headings


def build(root: Path):
    plan_sections = {
        1: ('PLAN_HOP_NHAT.md', 'adapt_scope'),
        2: ('PLAN_HOP_NHAT.md', 'adapt_architecture'),
        3: ('docs/01_CORE_CONTRACT.md', 'extend_runtime_contract'),
        4: ('PLAN_HOP_NHAT.md', 'preserve_profiles_adapt_provider_choice'),
        5: ('docs/10_IMPLEMENTATION_BACKLOG.md', 'adapt_cli_as_core_adapter'),
        6: ('docs/02_CORE_STATE_MACHINE.md', 'extend_identity_versions_state'),
        7: ('docs/05_NLU_AND_CONTEXT.md', 'preserve_semantics_extend_uncertainty'),
        8: ('docs/03_CORE_TRANSACTION_PROTOCOL.md', 'extend_delivery_fencing_causality'),
        9: ('docs/06_LOCATION_AND_KNOWLEDGE.md', 'preserve_evidence_correct_unsafe_rules'),
        10: ('docs/06_LOCATION_AND_KNOWLEDGE.md', 'preserve_source_tariff_gate'),
        11: ('docs/06_LOCATION_AND_KNOWLEDGE.md', 'preserve_approved_effective_knowledge'),
        12: ('docs/07_RESPONSE_AND_DELIVERY.md', 'extend_presented_history_delivery'),
        13: ('docs/08_TEST_FACTORY_AND_ACCEPTANCE.md', 'preserve_behavior_as_synthetic_scenarios'),
        14: ('docs/08_TEST_FACTORY_AND_ACCEPTANCE.md', 'preserve_L1_L2_L3_extend_L4'),
        15: ('docs/08_TEST_FACTORY_AND_ACCEPTANCE.md', 'preserve_independent_oracle_extend_mutators'),
        16: ('docs/09_MIGRATION_AND_CUTOVER.md', 'replace_greenfield_layout_with_repo_compatibility'),
        17: ('docs/03_CORE_TRANSACTION_PROTOCOL.md', 'extend_atomic_protocol_recovery'),
        18: ('docs/05_NLU_AND_CONTEXT.md', 'replace_pseudocode_with_contract_and_state_spec'),
        19: ('docs/10_IMPLEMENTATION_BACKLOG.md', 'replace_milestones_with_R0_R8_gates'),
        20: ('decisions/OPEN_DECISIONS.md', 'preserve_risks_register_open_decisions'),
    }
    rows = []
    for name in ('PLAN.md', 'PLAN_BONUS.md'):
        current = ('PLAN_HOP_NHAT.md', 'intro_or_navigation')
        for heading in markdown_headings((root / 'sources' / name).read_text(encoding='utf-8-sig')):
            title, number = heading['heading'], heading['line']
            if name == 'PLAN.md':
                import re
                match = re.match(r'(\d+)\.\s', title)
                if heading['level'] == 2 and match:
                    current = plan_sections.get(int(match[1]), current)
                if title.startswith('Phụ lục A'):
                    current = ('data/original-64.jsonl', 'preserve_all_64_verbatim_not_gold')
                elif title.startswith('Phụ lục B'):
                    current = ('docs/08_TEST_FACTORY_AND_ACCEPTANCE.md', 'adapt_demo_fixtures_not_live_facts')
                elif title.startswith('Phụ lục C'):
                    current = ('sources/README.md', 'archive_upstream_recheck_at_integration')
                elif title.startswith('Phụ lục D'):
                    current = ('docs/10_IMPLEMENTATION_BACKLOG.md', 'adapt_coding_handoff_to_repo')
            else:
                if number < 34:
                    current = ('docs/05_NLU_AND_CONTEXT.md', 'hypothesis_not_authoritative_rewrite')
                elif number < 79:
                    current = ('docs/05_NLU_AND_CONTEXT.md', 'preserve_sidetalk_fragment_numbers_with_guards')
                elif number < 95:
                    current = ('docs/06_LOCATION_AND_KNOWLEDGE.md', 'phonetic_experiment_not_automatic_verification')
                elif number < 116:
                    current = ('docs/07_RESPONSE_AND_DELIVERY.md', 'preserve_adaptive_clarification_with_evidence')
                elif number < 133:
                    current = ('docs/05_NLU_AND_CONTEXT.md', 'preserve_self_repair_with_ambiguity_guards')
                elif number < 194:
                    current = ('docs/08_TEST_FACTORY_AND_ACCEPTANCE.md', 'extend_mutators_correct_hidden_meaning_oracle')
                elif number < 251:
                    current = ('docs/05_NLU_AND_CONTEXT.md', 'replace_patch_with_canonical_schema_contract')
                elif number < 294:
                    current = ('docs/05_NLU_AND_CONTEXT.md', 'replace_raw_concat_with_idempotent_component_merge')
                elif number < 367:
                    current = ('docs/06_LOCATION_AND_KNOWLEDGE.md', 'normalization_scoped_phonetic_requires_benchmark')
                elif number < 407:
                    current = ('docs/07_RESPONSE_AND_DELIVERY.md', 'preserve_clarification_no_false_noise_or_driver_claim')
                elif number < 448:
                    current = ('docs/08_TEST_FACTORY_AND_ACCEPTANCE.md', 'mutator_acceptance_observable_information')
                elif number < 482:
                    current = ('docs/04_CORE_POLICY_MATRIX.md', 'asymmetry_keep_precision_remove_automatic_center')
                elif number < 512:
                    current = ('docs/07_RESPONSE_AND_DELIVERY.md', 'one_decision_not_one_extracted_location_no_forced_origin_first')
                elif number < 539:
                    current = ('docs/06_LOCATION_AND_KNOWLEDGE.md', 'coaching_keep_spatial_search_experimental')
                elif number < 582:
                    current = ('docs/06_LOCATION_AND_KNOWLEDGE.md', 'preserve_number_guard_reject_neighbor_coordinate_inference')
                elif number < 685:
                    current = ('docs/06_LOCATION_AND_KNOWLEDGE.md', 'spoken_alias_hypotheses_not_fact_or_auto_branch')
                elif number < 741:
                    current = ('docs/06_LOCATION_AND_KNOWLEDGE.md', 'replace_hard_tiers_85pct_with_soft_rank_hard_constraints')
                else:
                    current = ('docs/07_RESPONSE_AND_DELIVERY.md', 'hold_resume_with_target_version_expiry_no_misbound_yes')
            rows.append({'source': name, **heading, 'destination': current[0], 'disposition': current[1]})
    stamp = datetime.now(timezone(timedelta(hours=7))).isoformat()
    coverage = {'version': '3.0', 'created_at': stamp,
                'meaning': 'Structural heading coverage; semantic dispositions are reviewed in docs/12_SOURCE_TRACEABILITY.md. No claim of automated semantic completeness.',
                'headings': rows}
    (root / 'SOURCE_COVERAGE.json').write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    excluded = ['PACKAGE_MANIFEST.json', 'validation/VALIDATION.md', 'validation/package-check.json']
    files = []
    for path in sorted(root.rglob('*')):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            if relative not in excluded:
                files.append({'path': relative, 'bytes': path.stat().st_size,
                              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = {'package': 'vanuoc', 'version': '3.0', 'created_at': stamp,
                'algorithm': 'sha256', 'files': files, 'excluded_from_checksums': excluded,
                'exclusion_reason': 'Manifest avoids self-hash; validation report/results are generated after hash checking.'}
    (root / 'PACKAGE_MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'hashed_files': len(files), 'source_headings': len(rows)}, ensure_ascii=False))


if __name__ == '__main__':
    build(Path(__file__).resolve().parents[1])
