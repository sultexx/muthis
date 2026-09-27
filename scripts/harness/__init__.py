"""
The behaviour-regression harness: designed on its own page (revision 2), the
design approved in its foundation at DEC-154, revision 2 and rulings ①–⑤ in
Sultan's brief of 2026-09-27 (not yet in the ledger); the DEC-154 logging hazard
is fixed by `1c38f1b`. Drives the REAL kernel graph with only the provider real and every
outside edge fixed, records each pass, and compares two configurations by
counts. Lives in `scripts/`, outside the suite, and never calls the logging
setup. Entry point: `python scripts/harness <command>` (see `cli.py`).
"""
