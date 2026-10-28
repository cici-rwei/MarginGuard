"""Build a reviewed source/ABS/synthetic-example ZIP without private or M5 records.

This intentionally uses exact relative names, not a recursive '*.py' glob.
New deliverables must be reviewed and added to the allowlist. Source files are
opened read-only; an existing destination is never overwritten. The ZIP does
not grant redistribution rights and is not a backup of private business data.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_NAME = 'MarginGuard_COMP9001_Final.zip'

ROOT_FILES = (
    'abs_counts.py', 'abs_data.py', 'abs_indicators.py', 'app.py',
    'business_api.py', 'business_csv.py', 'business_forecast.py',
    'business_service.py', 'business_store.py', 'business_worker.py',
    'currency.py', 'data_loader.py', 'finance.py', 'forecast.py',
    'inventory.py', 'market_api.py', 'market_service.py', 'phase2_inputs.py',
    'run_phase1.py', 'run_phase2.py', 'runtime_config.py', 'scenario.py',
    'synthetic_demo.py',
    'gunicorn.conf.py', 'wsgi.py', 'requirements.txt', 'requirements-abs.txt',
    'requirements-production.txt', '.python-version', 'render.yaml',
    '.gitignore', 'start.command',
    'README.md', 'PHASE4A_REPORT.md', 'PHASE4B_REPORT.md', 'PHASE5A_REPORT.md',
    'PHASE5B_REPORT.md', 'PHASE5C_REPORT.md', 'RESTRUCTURE_B_REPORT.md',
    'FINAL_QA_REPORT.md', 'DEPLOYMENT_REPORT.md', 'DEPLOYMENT_EVIDENCE.md',
    'COMP9001_COMPLIANCE.md', 'AI_USE_DECLARATION.md', 'PADLET_DRAFT.md',
    'DEMO_SCRIPT_3MIN.md', 'AUD_USD_CURRENCY_DESIGN.md',
    'BUSINESS_DATA_UPLOAD_PRD.md', 'MARGINGUARD_PRODUCT_RESTRUCTURE.md',
    'PRODUCT_RESTRUCTURE_A_REPORT.md', 'SYNTHETIC_DEMO_MINIMAL_PLAN.md',
    'PUBLIC_DEPLOYMENT_REPORT.md', 'DEPLOYMENT_FILE_AUDIT.md', 'POST_DEPLOYMENT_UAT_REPORT.md',
    'deployment_files.json',
)
TEST_FILES = (
    'business_fixtures.py', 'test_abs_counts.py', 'test_abs_data.py',
    'test_abs_indicators.py', 'test_business_api.py', 'test_business_csv.py',
    'test_business_forecast.py', 'test_business_store.py', 'test_currency.py',
    'test_finance.py', 'test_inventory.py', 'test_market_web.py',
    'test_phase1.py', 'test_product_navigation.py', 'test_real_data.py',
    'test_scenario.py', 'test_web.py', 'test_release_config.py',
    'test_final_package.py', 'test_business_context.py',
    'test_business_ui.py', 'test_restructure_b.py', 'test_synthetic_demo.py',
    'business_context.test.js', 'test_uat_templates.py', 'uat_business_ui.test.js',
)
TEMPLATE_FILES = (
    '_business_upload.html', 'base.html', 'dashboard.html', 'forecasting.html',
    'inventory.html', 'market.html', 'scenarios.html',
)
STATIC_FILES = (
    'css/style.css', 'css/market.css', 'js/main.js', 'js/market.js',
    'js/business_upload.js', 'js/business_context.js',
)
SCRIPT_FILES = (
    'audit_m5.py', 'prepare_m5.py', 'prepare_abs.py',
    'cleanup_business_data.py', 'package_final.py',
)
ABS_FILES = (
    'market_quality.json', 'sources.json', 'market_data.json.gz',
    'market_catalog.json', 'build_all.json', 'business_counts.json',
)
EXAMPLE_FILES = ('README.md', 'synthetic_84_days.csv', 'synthetic_multi_series.csv', 'template.csv')
ALLOWLIST = tuple(sorted(
    list(ROOT_FILES)
    + ['tests/' + name for name in TEST_FILES]
    + ['templates/' + name for name in TEMPLATE_FILES]
    + ['static/' + name for name in STATIC_FILES]
    + ['scripts/' + name for name in SCRIPT_FILES]
    + ['data/abs/' + name for name in ABS_FILES]
    + ['examples/business_csv/' + name for name in EXAMPLE_FILES]
    + ['data/DATA_SOURCE.md', 'data/scenario_defaults.json', '.github/workflows/ci.yml']
))
# These must be present in a final handoff. Optional historical design notes
# and future test filenames above are not completeness requirements.
REQUIRED_FILES = (
    'app.py', 'forecast.py', 'inventory.py', 'finance.py', 'scenario.py',
    'business_csv.py', 'business_forecast.py', 'business_api.py',
    'business_store.py', 'business_service.py', 'business_worker.py',
    'currency.py', 'runtime_config.py', 'synthetic_demo.py', 'wsgi.py', 'gunicorn.conf.py',
    'requirements.txt', 'requirements-production.txt', 'render.yaml',
    'README.md', 'PHASE5A_REPORT.md', 'PHASE5B_REPORT.md', 'PHASE5C_REPORT.md',
    'RESTRUCTURE_B_REPORT.md', 'FINAL_QA_REPORT.md', 'DEPLOYMENT_REPORT.md',
    'COMP9001_COMPLIANCE.md', 'AI_USE_DECLARATION.md', 'PADLET_DRAFT.md',
    'DEMO_SCRIPT_3MIN.md', 'AUD_USD_CURRENCY_DESIGN.md',
    'BUSINESS_DATA_UPLOAD_PRD.md', 'data/DATA_SOURCE.md',
    'data/scenario_defaults.json', 'scripts/package_final.py', '.github/workflows/ci.yml',
) + tuple('templates/' + name for name in TEMPLATE_FILES) + tuple(
    'static/' + name for name in STATIC_FILES
) + tuple('data/abs/' + name for name in ABS_FILES) + tuple(
    'examples/business_csv/' + name for name in EXAMPLE_FILES
)

EXCLUSION_NOTES = [
    'All files outside the explicit source/config/document/data allowlist are omitted.',
    'Walmart M5 raw CSVs, processed sales, backtest actuals, forecasts, phase 1/2 results and old phase 1/2/3 reports are omitted pending verified redistribution permission.',
    'Historical screenshots and phase3_preview.png are omitted. Only explicitly named synthetic_* or abs_* screenshots may be included.',
    'Private uploads, sessions, SQLite/databases, secrets/.env, logs, caches, virtual environments, research downloads, existing ZIPs and unreviewed files are omitted.',
    'Symlinks and non-regular allowlisted files are rejected; source files are read-only.',
    'ABS lightweight snapshots retain source/licence metadata. CSV examples are explicitly synthetic, not Walmart or user business records.',
    'This package does not contain M5 sales history. Restore legitimately obtained M5 files locally using README instructions to enable that demo.',
]


def _safe_source(root, relative):
    """Reject links in the candidate or any of its in-project ancestors."""
    path = root / relative
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise ValueError('Refusing symbolic link in allowlisted path: ' + relative)
        if candidate == root:
            break
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError('Allowlisted path is not a regular file: ' + relative)
    return path


def collect_files(source_root=ROOT):
    """Return safe existing files; never recurse into uploads or research."""
    root = Path(source_root).expanduser().absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Source root must be an existing real project directory.')
    files = {}
    for relative in ALLOWLIST:
        path = _safe_source(root, relative)
        if path is not None:
            files[relative] = path
    screenshots = root / 'screenshots'
    if screenshots.is_symlink():
        raise ValueError('Screenshot directory must not be a symbolic link.')
    if screenshots.is_dir():
        for path in sorted(screenshots.iterdir()):
            if path.name.startswith(('synthetic_', 'abs_')) and path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
                relative = 'screenshots/' + path.name
                candidate = _safe_source(root, relative)
                if candidate is not None:
                    files[relative] = candidate
    return root, dict(sorted(files.items()))


def _read_regular(path):
    """Do not follow a symlink swapped in after candidate validation."""
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Only regular source files may be packaged.')
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            content = stream.read()
        return content, info.st_mode
    finally:
        os.close(descriptor)


def package(destination=None, *, source_root=ROOT, require_complete=True):
    root, files = collect_files(source_root)
    target = Path(destination) if destination is not None else root.parent / ARCHIVE_NAME
    target = target.expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError('Archive already exists; choose another path. Existing backups are never overwritten.')
    if not target.parent.is_dir():
        raise ValueError('Archive destination directory must already exist.')
    if target == root or root in target.parents:
        raise ValueError('Write the final ZIP outside the project directory.')
    missing = sorted(set(REQUIRED_FILES) - set(files))
    if require_complete and missing:
        raise ValueError('Final deliverables are missing: ' + ', '.join(missing))

    # Only allowlisted files are read into memory; no private directory traversal.
    contents, modes = {}, {}
    for relative, path in files.items():
        _safe_source(root, relative)
        contents[relative], modes[relative] = _read_regular(path)
    manifest = {
        'schema_version': 1,
        'package_kind': 'reviewed_source_abs_and_synthetic_examples',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'archive_root': 'MarginGuard',
        'contains_walmart_history': False,
        'contains_private_business_uploads': False,
        'missing_required_files': missing,
        'files': [{'path': name, 'size_bytes': len(content),
                   'sha256': hashlib.sha256(content).hexdigest()}
                  for name, content in contents.items()],
        'exclusions': EXCLUSION_NOTES,
        'manifest_hash_scope': 'All packaged source files; this generated manifest and generated PACKAGE_SCOPE.md are excluded from the manifest hash list.',
    }
    scope = '# MarginGuard final package scope\n\n' + '\n'.join('- ' + note for note in EXCLUSION_NOTES)
    scope += '\n\nMANIFEST.json lists SHA-256 and byte size for each source file.\n'
    directories = {'', 'data/', 'data/raw/'}
    for relative in contents:
        parent = Path(relative).parent
        while parent != Path('.'):
            directories.add(parent.as_posix() + '/')
            parent = parent.parent
    # Exclusive creation also prevents replacing an archive created concurrently.
    with ZipFile(target, 'x', ZIP_DEFLATED) as archive:
        for directory in sorted(directories):
            archive.writestr('MarginGuard/' + directory, '')
        for relative, content in contents.items():
            # ZipInfo preserves executable mode for start.command without changing it.
            entry = ZipInfo('MarginGuard/' + relative)
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = (modes[relative] & 0xFFFF) << 16
            archive.writestr(entry, content)
        archive.writestr('MarginGuard/MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        archive.writestr('MarginGuard/PACKAGE_SCOPE.md', scope)
    with ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP integrity verification failed.')
        for entry in manifest['files']:
            content = archive.read('MarginGuard/' + entry['path'])
            if hashlib.sha256(content).hexdigest() != entry['sha256']:
                raise ValueError('ZIP content hash verification failed.')
            current, _ = _read_regular(files[entry['path']])
            if hashlib.sha256(current).hexdigest() != entry['sha256']:
                raise ValueError('A source file changed during packaging. Review and build a new archive.')
    return {'path': str(target), 'files': len(contents), 'size_bytes': target.stat().st_size,
            'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, help='Default: source parent / ' + ARCHIVE_NAME)
    options = parser.parse_args()
    result = package(options.output, source_root=options.source_root)
    print(json.dumps(result, indent=2))
