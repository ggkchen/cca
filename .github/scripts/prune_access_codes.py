"""Drop lapsed temporary access codes from docs/access-codes.json.

The login page already refuses an expired code, but leaving them in the file
means the published site keeps advertising hashes forever. Run hourly by
.github/workflows/prune-codes.yml, and by the force sign-out bot with
--all, which clears every code regardless of expiry.
"""

import datetime
import io
import json
import os
import sys

CODES_PATH = "docs/access-codes.json"
STAMP = "%Y-%m-%dT%H:%M:%SZ"


def emit(**pairs):
    path = os.environ.get("GITHUB_OUTPUT")
    handle = io.open(path, "a", encoding="utf-8") if path else sys.stdout
    for key, value in pairs.items():
        handle.write("%s=%s\n" % (key, value))
    if path:
        handle.close()


def main():
    clear_all = "--all" in sys.argv
    now = datetime.datetime.now(datetime.timezone.utc).strftime(STAMP)

    try:
        data = json.load(io.open(CODES_PATH, encoding="utf-8"))
    except Exception:
        data = {}
    before = [c for c in (data.get("codes") or []) if isinstance(c, dict)]
    after = [] if clear_all else [c for c in before if str(c.get("expires", "")) > now]

    removed = len(before) - len(after)
    if removed or len(before) != len(data.get("codes") or []):
        io.open(CODES_PATH, "w", encoding="utf-8", newline="\n").write(
            json.dumps({"codes": after}, indent=2, sort_keys=True) + "\n"
        )

    print("removed %d code(s), %d still live" % (removed, len(after)))
    emit(removed=str(removed), live=str(len(after)))


if __name__ == "__main__":
    main()
