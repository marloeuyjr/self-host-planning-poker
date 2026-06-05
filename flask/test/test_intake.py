import unittest

from gamestate.exceptions import InvalidBacklogError
from gamestate.intake import parse_issues, _MAX_INPUT_CHARS, _MAX_ISSUES


class IntakeParseTestCase(unittest.TestCase):
    """S3 — pure parsing of a pasted backlog or CSV into issue dicts (E1, E6).

    No DB, no Socket.IO, no Jira call — just text in, dicts out.
    """

    # --- paste format: `KEY  Summary` per line ---

    def test_paste_parses_key_and_summary(self):
        issues = parse_issues('OPS-1  Add backup job\nOPS-2  Tune the probe', 'paste')
        self.assertEqual(len(issues), 2)
        self.assertEqual(issues[0]['jira_key'], 'OPS-1')
        self.assertEqual(issues[0]['summary'], 'Add backup job')
        self.assertEqual(issues[1]['jira_key'], 'OPS-2')
        self.assertEqual(issues[1]['summary'], 'Tune the probe')

    def test_paste_splits_on_first_whitespace_run_only(self):
        # The summary may contain spaces; only the first gap separates key from summary.
        issues = parse_issues('OPS-7\tRework the eventlet worker pool', 'paste')
        self.assertEqual(issues[0]['jira_key'], 'OPS-7')
        self.assertEqual(issues[0]['summary'], 'Rework the eventlet worker pool')

    def test_paste_skips_blank_lines(self):
        issues = parse_issues('OPS-1  one\n\n   \nOPS-2  two\n', 'paste')
        self.assertEqual([i['jira_key'] for i in issues], ['OPS-1', 'OPS-2'])

    def test_paste_rejects_a_key_with_no_summary(self):
        with self.assertRaises(InvalidBacklogError) as ctx:
            parse_issues('OPS-1  fine\nOPS-2', 'paste')
        # The error names the offending line so it isn't silently dropped.
        self.assertIn('2', str(ctx.exception))

    # --- CSV format: key,summary,url,description ---

    def test_csv_parses_all_columns(self):
        csv_text = ('key,summary,url,description\n'
                    'OPS-1,Add backup,http://j/OPS-1,Nightly sqlite copy\n'
                    'OPS-2,Tune probe,,')
        issues = parse_issues(csv_text, 'csv')
        self.assertEqual(len(issues), 2)
        self.assertEqual(issues[0]['jira_key'], 'OPS-1')
        self.assertEqual(issues[0]['summary'], 'Add backup')
        self.assertEqual(issues[0]['url'], 'http://j/OPS-1')
        self.assertEqual(issues[0]['description'], 'Nightly sqlite copy')
        # Empty optional columns become None, not empty strings.
        self.assertIsNone(issues[1]['url'])
        self.assertIsNone(issues[1]['description'])

    def test_csv_without_header_still_parses(self):
        issues = parse_issues('OPS-1,Add backup\nOPS-2,Tune probe', 'csv')
        self.assertEqual([i['jira_key'] for i in issues], ['OPS-1', 'OPS-2'])
        self.assertEqual(issues[0]['summary'], 'Add backup')

    def test_csv_rejects_a_row_missing_summary(self):
        with self.assertRaises(InvalidBacklogError):
            parse_issues('OPS-1,fine\nOPS-2,', 'csv')

    # --- shared behaviour ---

    def test_dedupes_within_one_import_keeping_first(self):
        issues = parse_issues('OPS-1  first\nOPS-2  other\nOPS-1  second', 'paste')
        self.assertEqual([i['jira_key'] for i in issues], ['OPS-1', 'OPS-2'])
        # First occurrence wins.
        self.assertEqual(issues[0]['summary'], 'first')

    def test_empty_text_yields_no_issues(self):
        self.assertEqual(parse_issues('', 'paste'), [])
        self.assertEqual(parse_issues('   \n  ', 'csv'), [])

    def test_unknown_format_falls_back_to_paste(self):
        issues = parse_issues('OPS-1  hi', 'something-else')
        self.assertEqual(issues[0]['jira_key'], 'OPS-1')

    # --- import guardrails (size / count caps, single-worker DoS) ---

    def test_accepts_rows_up_to_the_issue_cap(self):
        text = '\n'.join(f'OPS-{i}  Summary {i}' for i in range(_MAX_ISSUES))
        self.assertEqual(len(parse_issues(text, 'paste')), _MAX_ISSUES)

    def test_rejects_more_rows_than_the_issue_cap(self):
        text = '\n'.join(f'OPS-{i}  Summary {i}' for i in range(_MAX_ISSUES + 1))
        with self.assertRaises(InvalidBacklogError):
            parse_issues(text, 'paste')

    def test_rejects_oversized_input_text(self):
        text = 'OPS-1  ' + ('x' * (_MAX_INPUT_CHARS + 1))
        with self.assertRaises(InvalidBacklogError):
            parse_issues(text, 'paste')


if __name__ == '__main__':
    unittest.main()
