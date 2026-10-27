"""Publication drafts must not silently become upload-ready packages."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publication_check', ROOT / 'tools/check_publication_metadata.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
PAPER_DOI = '10.1234/example-preprint'


@pytest.fixture
def documents(tmp_path):
    root, prep = tmp_path / 'repo', tmp_path / 'preparation'
    prep.mkdir()
    for relative in check.PUBLIC_DOCS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(PAPER_DOI if relative in check.PAPER_DOCS else 'Release document', encoding='utf-8')
    (prep / 'START_HERE.md').write_text('Release instructions', encoding='utf-8')
    cff = ('doi: "' + check.ZENODO_DOI + '"\nkeywords:\n'
           + ''.join('  - ' + word + '\n' for word in check.KEYWORDS)
           + 'references:\n  - type: article\n    doi: "' + PAPER_DOI + '"\n')
    (root / 'CITATION.cff').write_text(cff, encoding='utf-8')
    metadata = {'doi': check.ZENODO_DOI, 'keywords': check.KEYWORDS,
                'related_identifiers': [{'identifier': PAPER_DOI,
                    'relation_type': 'Is supplement to', 'resource_type': 'Publication / Preprint'}]}
    (prep / 'Zenodo_record_draft.json').write_text(json.dumps(metadata), encoding='utf-8')
    return root, prep


def test_consistent_documents_pass(documents):
    assert check.validate(*documents)['status'] == 'Passed'


@pytest.mark.parametrize('name', [*check.PAPER_DOCS, 'Zenodo_record_draft.json'])
def test_placeholder_blocks_each_of_five_files(documents, name):
    root, prep = documents
    path = (prep if name.endswith('.json') else root) / name
    path.write_text(path.read_text(encoding='utf-8').replace(PAPER_DOI, '10.1101/TODO_' + 'BIORXIV_DOI'), encoding='utf-8')
    result = check.validate(root, prep)
    assert result['status'] == 'Blocked'
    assert any(error['file'] == name and 'placeholder' in error['message'] for error in result['errors'])


def test_mismatched_doi_blocks(documents):
    root, prep = documents
    path = root / 'CITATION.cff'
    path.write_text(path.read_text(encoding='utf-8').replace(PAPER_DOI, '10.1234/different'), encoding='utf-8')
    assert check.validate(root, prep)['status'] == 'Blocked'


def test_missing_document_blocks(documents):
    root, prep = documents
    (root / 'README.md').unlink()
    assert check.validate(root, prep)['status'] == 'Blocked'


def test_keyword_mismatch_blocks(documents):
    root, prep = documents
    path = root / 'CITATION.cff'
    path.write_text(path.read_text(encoding='utf-8').replace('  - brain atlas', '  - different keyword'), encoding='utf-8')
    assert check.validate(root, prep)['status'] == 'Blocked'


def test_project_has_only_requested_keywords():
    assert check.citation_keywords((ROOT / 'CITATION.cff').read_text(encoding='utf-8')) == check.KEYWORDS
