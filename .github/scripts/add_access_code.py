"""Add a temporary access code to docs/access-codes.json.

Reads a "Temp access code" issue body (or workflow_dispatch inputs), hashes the
code with a per-code salt, and appends it with an expiry. The plaintext code
never lands in the repo, the outputs, or the log -- the login page hashes what
gets typed and compares. Also writes a redacted copy of the issue body so the
caller can strip the code out of the issue itself.

Run by .github/workflows/temp-code.yml.
"""

import datetime
import hashlib
import io
import json
import os
import re
import secrets
import sys
import tempfile

CODES_PATH = "docs/access-codes.json"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
NO_RESPONSE = "_No response_"


def emit(**pairs):
    """Write step outputs. Falls back to stdout when run outside Actions."""
    path = os.environ.get("GITHUB_OUTPUT")
    handle = io.open(path, "a", encoding="utf-8") if path else sys.stdout
    for key, value in pairs.items():
        handle.write("%s=%s\n" % (key, value))
    if path:
        handle.close()


def fail(message):
    """Bail out. The step goes red so the failure is visible on every path;
    the workflow's report step still runs and explains it on the issue."""
    emit(ok="false", error=message)
    raise SystemExit(1)


def split_sections(body):
    """Issue forms render as '### Label' headings followed by the answer."""
    sections, current = {}, None
    for line in body.splitlines():
        heading = re.match(r"^###\s+(.*?)\s*$", line)
        if heading:
            current = heading.group(1).strip().lower()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def section(sections, name):
    value = "\n".join(sections.get(name, [])).strip()
    return "" if value == NO_RESPONSE else value


def redact(body, temp_dir):
    """Rewrite the issue body with the Code answer replaced."""
    out, dropping = [], False
    for line in body.splitlines():
        heading = re.match(r"^###\s+(.*?)\s*$", line)
        if heading:
            dropping = heading.group(1).strip().lower() == "code"
            out.append(line)
            if dropping:
                out.extend(["", "_[redacted by the bot]_", ""])
            continue
        if not dropping:
            out.append(line)
    target = os.path.join(temp_dir, "redacted.md")
    io.open(target, "w", encoding="utf-8", newline="\n").write("\n".join(out).strip() + "\n")
    return target


def load_codes(now_stamp):
    """Existing codes, minus anything that has already lapsed."""
    try:
        data = json.load(io.open(CODES_PATH, encoding="utf-8"))
    except Exception:
        return []
    return [
        code
        for code in (data.get("codes") or [])
        if isinstance(code, dict) and str(code.get("expires", "")) > now_stamp
    ]


def main():
    event = os.environ.get("EVENT", "")
    issue_body = os.environ.get("ISSUE_BODY") or ""

    # Redact first. A bad code still has to come out of the public issue, and
    # anything below here can bail out before reaching the end.
    if event == "issues":
        redact(issue_body, os.environ.get("RUNNER_TEMP") or tempfile.gettempdir())

    if event == "issues":
        sections = split_sections(issue_body)
        code = section(sections, "code")
        hours = section(sections, "hours until it stops working")
        note = section(sections, "who is it for")
        expire_session = "[x]" in section(sections, "options").lower()
    else:
        code = os.environ.get("IN_CODE", "")
        hours = os.environ.get("IN_HOURS", "")
        note = os.environ.get("IN_NOTE", "")
        expire_session = os.environ.get("IN_EXPIRE", "").lower() == "true"

    normalised = re.sub(r"\s+", "", code).lower()
    if not re.match(r"^[a-z0-9]{4,40}$", normalised):
        fail("the code must be 4-40 letters and digits, nothing else")

    digits = re.sub(r"[^0-9]", "", hours)
    life = int(digits) if digits else 24
    if not 1 <= life <= 720:
        fail("hours must be between 1 and 720")

    now = datetime.datetime.now(datetime.timezone.utc)
    expires = now + datetime.timedelta(hours=life)
    salt = secrets.token_hex(8)

    codes = load_codes(now.strftime(STAMP))
    codes.append(
        {
            "id": secrets.token_hex(4),
            "len": len(normalised),
            "salt": salt,
            "hash": hashlib.sha256((salt + ":" + normalised).encode("utf-8")).hexdigest(),
            "expires": expires.strftime(STAMP),
            "expireSession": bool(expire_session),
            "note": note[:120],
            "issued": now.strftime(STAMP),
        }
    )
    io.open(CODES_PATH, "w", encoding="utf-8", newline="\n").write(
        json.dumps({"codes": codes}, indent=2, sort_keys=True) + "\n"
    )

    emit(
        ok="true",
        expires=expires.strftime(STAMP),
        hours=str(life),
        expire_session="yes" if expire_session else "no",
        live=str(len(codes)),
    )


if __name__ == "__main__":
    main()
