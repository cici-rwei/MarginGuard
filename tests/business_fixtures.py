"""Explicitly SYNTHETIC business CSV fixtures; never real enterprise or M5 data.

The deterministic values exercise contracts and are not accuracy evidence.
"""
import csv
import io
from datetime import date, timedelta


FIELDS = ['Date', 'Product', 'Store', 'Units Sold', 'Unit Price', 'Unit Cost']
START = date(2024, 1, 1)
AS_OF = date(2025, 1, 1)
PRODUCT = 'SYNTHETIC_SKU_001'
STORE = 'SYNTHETIC_STORE_A'


def synthetic_rows(days=84, *, product=PRODUCT, store=STORE, values=None,
                   start=START):
    """One completed daily row per synthetic product/store; no random source."""
    if values is None:
        values = [2 + day % 7 for day in range(days)]
    return [
        {'Date': str(start + timedelta(days=day)), 'Product': product, 'Store': store,
         'Units Sold': str(value), 'Unit Price': '4.50', 'Unit Cost': '2.10'}
        for day, value in enumerate(values)
    ]


def csv_bytes(rows, fields=FIELDS, *, bom=False):
    handle = io.StringIO(newline='')
    writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue().encode('utf-8-sig' if bom else 'utf-8')

