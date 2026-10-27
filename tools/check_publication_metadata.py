"""Check release documents before packaging; this does not publish anything.

The DOI check validates syntax and agreement across files, not registration or
online availability. Draft documents may keep placeholders until submission.
"""
import argparse
import json
from pathlib import Path
import re
import sys

PUBLIC_DOCS = (
    'README.md', 'CHANGELOG.md', 'CITATION.cff', 'THIRD_PARTY_NOTICES.md',
    'data/README.md', 'data/licenses/ReferenceLibrary-CC-BY-4.0.txt',
    'docs/ANTS_REGISTRATION.md', 'docs/DATA_DISTRIBUTION.md',
    'docs/OUTPUTS.md', 'docs/QT_RUNTIME.md', 'example_data/README.md',
)
PAPER_DOCS = (
    'README.md', 'CITATION.cff', 'data/README.md',
    'data/licenses/ReferenceLibrary-CC-BY-4.0.txt',
)
KEYWORDS = ['common marmoset', 'computed tomography', 'brain atlas', 'image registration']
ZENODO_DOI = '10.5281/zenodo.23683937'
PLACEHOLDER = re.compile(r'TODO_[A-Z0-9_]+|\[rights holders\]|YYYY-MM-DD')
DOI = re.compile(r'10\.\d{4,9}/[-._;()/:A-Za-z0-9]+')


def citation_keywords(text):
    """Read the plain string keyword list used in this project's CFF file."""
    section = re.search(r'^keywords:\s*\n(.*?)(?=^\S|\Z)', text, re.M | re.S)
    if not section:
        return []
    return [match.strip().strip('\"\'') for match in
            re.findall(r'^  - (.+)$', section.group(1), re.M)]


def validate(workspace, preparation):
    workspace, preparation = Path(workspace), Path(preparation)
    errors, documents = [], {}
    paths = {name: workspace / name for name in PUBLIC_DOCS}
    paths.update({name: preparation / name for name in
                  ['START_HERE.md', 'Zenodo_record_draft.json']})
    for name, path in paths.items():
        try:
            content = path.read_text(encoding='utf-8-sig')
        except OSError:
            errors.append({'file': name, 'message': 'Required file is missing or unreadable.'})
            continue
        documents[name] = content
        for token in sorted(set(PLACEHOLDER.findall(content))):
            errors.append({'file': name, 'message': 'Unresolved placeholder: ' + token})
    try:
        metadata = json.loads(documents.get('Zenodo_record_draft.json', '{}'))
        if not isinstance(metadata, dict):
            raise ValueError('Expected a JSON object')
    except ValueError:
        errors.append({'file': 'Zenodo_record_draft.json', 'message': 'Invalid metadata JSON.'})
        metadata = {}
    cff = documents.get('CITATION.cff', '')
    if citation_keywords(cff) != KEYWORDS:
        errors.append({'file': 'CITATION.cff', 'message': 'The four keywords do not match the release keywords.'})
    if metadata.get('keywords') != KEYWORDS:
        errors.append({'file': 'Zenodo_record_draft.json', 'message': 'The four keywords do not match the release keywords.'})
    cff_doi = re.search(r'^doi:\s*[\"\']?([^\s\"\']+)', cff, re.M)
    if not cff_doi or cff_doi.group(1) != ZENODO_DOI or metadata.get('doi') != ZENODO_DOI:
        errors.append({'file': 'CITATION.cff / Zenodo_record_draft.json',
                       'message': 'The software DOI must be ' + ZENODO_DOI})
    related = metadata.get('related_identifiers', [])
    if not isinstance(related, list):
        related = []
    papers = [item.get('identifier') for item in related if isinstance(item, dict)
              and item.get('relation_type') == 'Is supplement to'
              and item.get('resource_type') == 'Publication / Preprint']
    paper_doi = papers[0] if len(papers) == 1 else None
    if (not isinstance(paper_doi, str) or not DOI.fullmatch(paper_doi)
            or PLACEHOLDER.search(paper_doi) or paper_doi == ZENODO_DOI):
        errors.append({'file': 'Zenodo_record_draft.json',
                       'message': 'Set one actual preprint DOI in related_identifiers before building.'})
    else:
        for name in PAPER_DOCS:
            content = documents.get(name, '')
            if paper_doi not in set(DOI.findall(content)):
                errors.append({'file': name, 'message': 'The preprint DOI is missing or differs from the Zenodo draft.'})
        references = re.search(r'^references:\s*\n(.*)', cff, re.M | re.S)
        reference_dois = re.findall(r'^    doi:\s*[\"\']?([^\s\"\']+)',
                                    references.group(1) if references else '', re.M)
        if reference_dois != [paper_doi]:
            errors.append({'file': 'CITATION.cff', 'message': 'The publication reference must use the same preprint DOI.'})
    return {'status': 'Passed' if not errors else 'Blocked',
            'zenodo_doi': ZENODO_DOI, 'preprint_doi': paper_doi,
            'errors': errors, 'checked_files': list(paths),
            'scope': 'Document consistency only; DOI registration and online availability are not checked.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--preparation-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = validate(args.workspace, args.preparation_dir)
    serialized = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    if args.report:
        args.report.write_text(serialized, encoding='utf-8')
    print(serialized)
    return 0 if report['status'] == 'Passed' else 2


if __name__ == '__main__':
    sys.exit(main())
