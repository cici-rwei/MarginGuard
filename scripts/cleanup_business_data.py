"""Clean expired private uploads. No business records are printed.

Run under the same OS user and settings as the web service. The web service also
checks expiry on every request and runs a periodic best-effort cleanup thread.
"""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from business_store import BusinessStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', default=os.environ.get('MARGINGUARD_PRIVATE_DIR') or os.environ.get('BUSINESS_STORAGE_ROOT'))
    args = parser.parse_args()
    if not args.storage_root:
        parser.error('Configure MARGINGUARD_PRIVATE_DIR or --storage-root outside the project.')
    try:
        BusinessStore(args.storage_root).cleanup()
    except (ValueError, OSError):
        raise SystemExit('Private storage is unavailable; check configuration and permissions.') from None
    print('Expired private data cleanup completed.')


if __name__ == '__main__':
    main()
