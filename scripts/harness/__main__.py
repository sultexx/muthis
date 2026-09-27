"""`python scripts/harness <command>` — puts `src/` and `scripts/` on the path
(the diag scripts' bootstrap) and hands over to `cli.main`."""

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
for entry in (REPO / "scripts", REPO / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from harness.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
