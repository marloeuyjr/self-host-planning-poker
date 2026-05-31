import datetime

from peewee import (Model, UUIDField, CharField, TextField, IntegerField,
                    FloatField, DateTimeField, ForeignKeyField, Proxy)

database_proxy = Proxy()


class StoredGame(Model):
    uuid = UUIDField(primary_key=True)
    name = CharField()
    deck = CharField()
    created_at = DateTimeField(default=datetime.datetime.now, null=True)  # for recall ordering (B2)

    class Meta:
        database = database_proxy


class Issue(Model):
    """A backlog item to estimate, owned by a game/session and ordered in a queue."""
    game = ForeignKeyField(StoredGame, backref='issues', on_delete='CASCADE')
    jira_key = CharField()
    summary = CharField()
    description = TextField(null=True)
    url = CharField(null=True)             # optional Jira link (CSV import, S3)
    order_index = IntegerField()
    status = CharField(default='pending')  # pending | estimating | estimated | refinement | skipped
    park_reason = TextField(null=True)     # why an issue was parked / skipped (S6)
    source = CharField(null=True)          # provenance, e.g. 'paste' or 'csv'
    imported_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        database = database_proxy


class EstimationResult(Model):
    """An append-only record of one voting round on an issue (EC2).

    Several rows may exist per issue — one per re-vote round; `final_value` is set
    on the accepted round (E4). The numbers are computed server-side by
    `gamestate.stats.compute_stats` and frozen here before hands are cleared (E5).
    """
    issue = ForeignKeyField(Issue, backref='results', on_delete='CASCADE')
    round_number = IntegerField()
    final_value = FloatField(null=True)
    average = FloatField(null=True)
    median = FloatField(null=True)
    agreement = FloatField(null=True)
    deck_at_vote = CharField()
    voter_count = IntegerField(default=0)
    decided_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        database = database_proxy
        # Append-only integrity: exactly one row per (issue, round).
        indexes = ((('issue', 'round_number'), True),)


# Columns added to a table after it first shipped. On a fresh DB peewee creates them
# from the model; on a DB that already has the older table they are added by a guarded
# `ALTER TABLE`. Both paths are idempotent and forward-only.
_ISSUE_ADDED_COLUMNS = {
    'url': 'VARCHAR',                # optional Jira link (S3)
    'park_reason': 'TEXT',          # why an issue was parked / skipped (S6)
}
_STOREDGAME_ADDED_COLUMNS = {
    'created_at': 'DATETIME',       # creation time for recall ordering (B2)
}


def create_tables():
    """Create all tables if missing, then add any columns introduced in later slices.

    Forward-only, additive migration: existing `StoredGame` rows are untouched; the
    `Issue` / `EstimationResult` tables are created on boot if absent, and columns
    added in later slices are appended in place on an older DB (`url`, `park_reason`
    on `issue`; `created_at` on `storedgame`). Idempotent — safe to run on every
    startup. Replaces the old single `StoredGame.create_table()` startup call.
    """
    database_proxy.create_tables([StoredGame, Issue, EstimationResult])
    _add_missing_columns('issue', _ISSUE_ADDED_COLUMNS)
    _add_missing_columns('storedgame', _STOREDGAME_ADDED_COLUMNS)


def _add_missing_columns(table_name: str, columns: dict) -> None:
    """Append any of `columns` (name -> SQL type) absent from `table_name`.

    Guarded `ALTER TABLE ADD COLUMN` per missing column — idempotent and forward-only.
    Columns added this way are always nullable, so existing rows get NULL (SQLite
    can't backfill a default like `now()` in an ALTER); for `created_at` those legacy
    rows simply sort last in the recall list.
    """
    existing = {col.name for col in database_proxy.get_columns(table_name)}
    for name, sql_type in columns.items():
        if name not in existing:
            database_proxy.execute_sql(f'ALTER TABLE {table_name} ADD COLUMN {name} {sql_type}')


def _add_missing_issue_columns():
    """Backwards-compatible thin wrapper over the generic column migrator."""
    _add_missing_columns('issue', _ISSUE_ADDED_COLUMNS)
