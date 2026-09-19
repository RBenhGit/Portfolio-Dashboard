#!/usr/bin/env python3
"""Delete the transactions the pre-fix PDF converter inserted broken.

Those rows carry a `transaction_type` that is not in IBIClassifier's
vocabulary (reversed Hebrew, or a type glued to the security name), so they
were stored with effect='none': present in the table but skipped by the
builder, i.e. silently missing from the portfolio.

They cannot be corrected in place. Dedup is a sha256 over all columns, so the
fixed converter produces different hashes and re-ingesting would insert the
corrected rows *alongside* these rather than replacing them.

Scope is deliberately narrow. Only rows whose type is outside the vocabulary
are removed -- a phantom tax row with a *valid* type also classifies as
effect='none', but that is correct behaviour and those rows arrive from Excel
too (e.g. ("הפקדה","9992985") appears 58 times), so they are left alone.

Run:
    venv/bin/python scripts/cleanup_broken_pdf_rows.py          # dry run
    venv/bin/python scripts/cleanup_broken_pdf_rows.py --apply  # delete
"""
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.input.pdf_type_map import CLASSIFIER_VOCABULARY  # noqa: E402

DB = PROJECT_ROOT / "data" / "portfolio.db"


def find_broken(conn):
    rows = conn.execute(
        """select id, date, transaction_type, security_name, security_symbol,
                  quantity, currency, market
           from transactions where effect = 'none' order by id"""
    ).fetchall()
    return [r for r in rows if (r[2] or "") not in CLASSIFIER_VOCABULARY]


def main() -> int:
    apply = "--apply" in sys.argv
    conn = sqlite3.connect(DB)
    broken = find_broken(conn)

    if not broken:
        print("No broken PDF rows found.")
        return 0

    print(f"{'id':>6}  {'date':10}  {'type':28} {'symbol':12} {'qty':>9}")
    for r in broken:
        print(f"{r[0]:>6}  {r[1]:10}  {str(r[2])[:26]!r:28} {str(r[4]):12} {r[5]:>9}")
    print(f"\n{len(broken)} row(s) with a transaction_type outside the app vocabulary.")

    if not apply:
        print("\nDry run. Re-run with --apply to delete, then re-ingest the PDFs.")
        return 0

    ids = [r[0] for r in broken]
    conn.executemany("delete from transactions where id = ?", [(i,) for i in ids])
    conn.commit()
    print(f"\nDeleted {len(ids)} row(s). Re-ingest the PDFs and rebuild:")
    print("  venv/bin/python scripts/run_import.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
