"""Parse a pasted backlog or a CSV into issue dicts for bulk insert (S3).

Pure module — no database, no Socket.IO. It is called by the `/create` REST route
on the request thread, so the parse never blocks the single eventlet greenlet, and
it is **never** a Jira API call (import/export-only, E1). Output feeds
`GameManager.create`, which inserts the rows in one transaction.

Two input shapes (E6 assumes ~15–40 issues, so a full parse in one pass is fine):
  - `paste`: one `KEY  Summary` line per issue (the key, then the rest of the line).
  - `csv`:   `key,summary,url,description` rows, with an optional header row.
"""
import csv
import io
import re

from gamestate.exceptions import InvalidBacklogError

# A key is the first whitespace-delimited token on a pasted line; the summary is
# everything after the first run of whitespace.
_PASTE_SPLIT = re.compile(r'\s+')


def parse_issues(text, fmt='paste') -> list:
    """Parse `text` into an ordered, de-duped list of issue dicts.

    Each dict has `jira_key`, `summary`, and (CSV only) optional `url` / `description`.
    Raises `InvalidBacklogError` naming the offending line rather than dropping it.
    """
    text = (text or '').strip()
    if not text:
        return []
    rows = _parse_csv(text) if fmt == 'csv' else _parse_paste(text)
    return _dedupe(rows)


def _parse_paste(text) -> list:
    issues = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        parts = _PASTE_SPLIT.split(line, maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            raise InvalidBacklogError(
                f'Line {lineno} has no summary: "{line}". Expected "KEY  Summary".')
        issues.append({'jira_key': parts[0].strip(), 'summary': parts[1].strip(),
                       'url': None, 'description': None})
    return issues


def _parse_csv(text) -> list:
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        return []
    # Skip a header row if the first cell names the key column.
    if rows[0] and rows[0][0].strip().lower() in ('key', 'jira_key', 'jira key'):
        rows = rows[1:]
    issues = []
    for lineno, row in enumerate(rows, start=1):
        cells = [c.strip() for c in row]
        key = cells[0] if len(cells) > 0 else ''
        summary = cells[1] if len(cells) > 1 else ''
        if not key or not summary:
            raise InvalidBacklogError(
                f'CSV row {lineno} is missing a key or summary: {row}. '
                f'Expected "key,summary,url,description".')
        url = cells[2] if len(cells) > 2 and cells[2] else None
        description = cells[3] if len(cells) > 3 and cells[3] else None
        issues.append({'jira_key': key, 'summary': summary,
                       'url': url, 'description': description})
    return issues


def _dedupe(rows) -> list:
    """Drop duplicate keys within one import, keeping the first occurrence."""
    seen = set()
    deduped = []
    for row in rows:
        if row['jira_key'] in seen:
            continue
        seen.add(row['jira_key'])
        deduped.append(row)
    return deduped
