import csv
import errno
import io
import os
import re
import sys
import uuid

from flask import Flask, request, session, render_template, jsonify, Response
from flask_cors import CORS
from flask_socketio import SocketIO, join_room, leave_room, emit
from peewee import SqliteDatabase, OperationalError

from permission_check import check_db_file_permissions
from gamestate.exceptions import PlanningPokerException
from gamestate.game_manager import GameManager
from gamestate.intake import parse_issues
from gamestate.models import database_proxy, StoredGame, create_tables

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'

# DATABASE_PATH lets a test (or a dev) point the DB at a scratch file and take the
# dev-style socketio/CORS setup without the /data permission check. Prod sets nothing,
# so behaviour is unchanged there.
db_override = os.getenv('DATABASE_PATH')
if app.config['DEBUG'] or db_override:
    real_db = SqliteDatabase(db_override or 'database.db')
    socketio = SocketIO(app, cors_allowed_origins=[
        'http://localhost:4200', 'http://localhost:5000',
        'http://127.0.0.1:4200', 'http://127.0.0.1:5000'
    ])
    CORS(app)
else:
    check_db_file_permissions()
    real_db = SqliteDatabase('/data/database.db')
    socketio = SocketIO(app)
database_proxy.initialize(real_db)
if database_proxy.is_closed():
    database_proxy.connect()
create_tables()

gm = GameManager()

app_root = os.getenv('APP_ROOT', '/')
if not app_root.endswith('/'):
    app_root += '/'

app_title = os.getenv('APP_TITLE', 'Driftsprognoser Planning Poker')


@app.route('/create', methods=['POST'])
def create():
    body = request.json
    game_name = body['name']
    game_deck = body['deck']
    # Optional starting backlog (S3). Parsed here on the request thread — never a
    # Jira API call, never inside a Socket.IO handler (E1).
    backlog_text = body.get('backlog')
    backlog_format = body.get('backlogFormat', 'paste')
    try:
        issues = parse_issues(backlog_text, backlog_format) if backlog_text else None
        return gm.create(game_name, game_deck, issues, source=backlog_format if issues else None)
    except PlanningPokerException as e:
        return str(e), 400


@app.route('/sessions')
def sessions():
    # Saved-session recall list for the home page (B2). Read-only; declared before the
    # catch-all so the `<path:path>` converter never swallows it. Returns a JSON array.
    return jsonify(gm.list_sessions())


# CSV header order. Kept beside the route so the column contract is obvious; mirrors
# the per-issue dict keys from `GameManager.export_session`.
_EXPORT_CSV_COLUMNS = ['order', 'key', 'summary', 'status', 'final_value', 'rounds',
                       'average', 'agreement', 'voter_count', 'deck', 'park_reason']


def _export_slug(name: str) -> str:
    """Filename-safe slug from a session name for the CSV download (ASCII, dashed)."""
    slug = re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-')
    return slug or 'session'


@app.route('/sessions/<string:game_uuid>/export.json')
def export_session_json(game_uuid):
    # Full per-issue results of one saved session as JSON (v2 export). Declared beside
    # /sessions; the literal `export.json` suffix ranks this static rule ahead of the
    # `<path:path>` catch-all, so the SPA never swallows it. 404 on an unknown uuid.
    data = gm.export_session(game_uuid)
    if data is None:
        return '', 404
    return jsonify(data)


@app.route('/sessions/<string:game_uuid>/export.csv')
def export_session_csv(game_uuid):
    # Same export as a spreadsheet-friendly CSV: a header row plus one row per issue.
    # The Content-Disposition filename is the sanitised session name. A backlog-less
    # ("classic") game exports just the header — never crashes.
    data = gm.export_session(game_uuid)
    if data is None:
        return '', 404
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_EXPORT_CSV_COLUMNS)
    for issue in data['issues']:
        writer.writerow([
            issue['orderIndex'], issue['key'], issue['summary'], issue['status'],
            issue['finalValue'], issue['rounds'], issue['average'], issue['agreement'],
            issue['voterCount'], issue['deck'], issue['parkReason'],
        ])
    filename = f'{_export_slug(data["name"])}-poker.csv'
    return Response(buf.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.route('/<string:file>.<string:ext>')
def serve_file(file, ext):
    return app.send_static_file(f'{file}.{ext}')

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    return render_template('index.html', app_root=app_root, app_title=app_title)


@app.route('/favicon.ico')
def serve_icon():
    return app.send_static_file('favicon/favicon.ico')

@app.route('/assets/<path:path>')
def serve_assets(path):
    return app.send_static_file(f'assets/{path}')

@socketio.event
def join(data):
    player_id = str(uuid.uuid4())
    player_name = data['name']
    spectator = data['spectator']
    game_id = data['game']
    token = data.get('token')   # localStorage rejoin token (S7) — reattach, not auth

    session['game_id'] = game_id
    join_room(game_id)

    info, state, player_id, resumed = gm.join_game(game_id, player_id, player_name, spectator, token)
    session['player_id'] = player_id
    emit('state', state, to=game_id, json=True)

    # Hand the room the current backlog so late joiners see the queue + pointer (S4).
    backlog = gm.backlog(game_id)
    if backlog['issues']:
        emit('backlog', backlog, to=game_id, json=True)

    info['playerId'] = player_id
    if resumed:
        info['resumed'] = True
    return info


@socketio.event
def disconnect():
    player_id = session['player_id']
    game_id = session['game_id']

    state = gm.leave_game(game_id, player_id)
    leave_room(game_id)
    emit('state', state, to=game_id, json=True)
    # Re-broadcast info so a driver auto-handoff (S8) reaches the remaining clients.
    info = gm.info(game_id)
    if info:
        emit('info', info, to=game_id, json=True)

    session['player_id'] = None
    session['game_id'] = None


@socketio.event
def rename_game(data):
    game_id = session['game_id']
    game_name = data['name']

    info = gm.rename_game(game_id, game_name)
    emit('info', info, to=game_id, json=True)


@socketio.event
def set_deck(data):
    game_id = session['game_id']
    deck_name = data['deck']

    gm.require_driver(game_id, session['player_id'])
    info, state = gm.set_deck(game_id, deck_name)
    emit('info', info, to=game_id, json=True)
    emit('state', state, to=game_id, json=True)


@socketio.event
def claim_driver():
    game_id = session['game_id']

    info, state = gm.claim_driver(game_id, session['player_id'])
    emit('info', info, to=game_id, json=True)
    emit('state', state, to=game_id, json=True)


@socketio.event
def set_player_name(data):
    player_id = session['player_id']
    game_id = session['game_id']
    player_name = data['name']

    state = gm.set_player_name(game_id, player_id, player_name)
    emit('state', state, to=game_id, json=True)


@socketio.event
def set_spectator(data):
    player_id = session['player_id']
    game_id = session['game_id']
    is_spectator = data['spectator']

    state = gm.set_player_spectator(game_id, player_id, is_spectator)
    emit('state', state, to=game_id, json=True)


@socketio.event
def pick_card(data):
    player_id = session['player_id']
    game_id = session['game_id']
    card = data['card']

    state = gm.pick_card(game_id, player_id, card)
    emit('state', state, to=game_id, json=True)


@socketio.event
def reveal_cards():
    game_id = session['game_id']

    gm.require_driver(game_id, session['player_id'])
    state, info, results = gm.reveal_cards(game_id)
    emit('state', state, to=game_id, json=True)
    emit('info', info, to=game_id, json=True)
    emit('results', results, to=game_id, json=True)


@socketio.event
def accept_estimate(data):
    game_id = session['game_id']
    value = data.get('value') if data else None

    gm.require_driver(game_id, session['player_id'])
    backlog, state, info = gm.accept_estimate(game_id, value)
    emit('state', state, to=game_id, json=True)
    emit('info', info, to=game_id, json=True)
    emit('backlog', backlog, to=game_id, json=True)
    emit('new_game', to=game_id)


@socketio.event
def revote():
    game_id = session['game_id']

    gm.require_driver(game_id, session['player_id'])
    backlog, state, info = gm.revote(game_id)
    emit('state', state, to=game_id, json=True)
    emit('info', info, to=game_id, json=True)
    emit('backlog', backlog, to=game_id, json=True)
    emit('new_game', to=game_id)


@socketio.event
def select_issue(data):
    game_id = session['game_id']
    index = data['index']

    gm.require_driver(game_id, session['player_id'])
    backlog, state, info = gm.select_issue(game_id, index)
    emit('state', state, to=game_id, json=True)
    emit('info', info, to=game_id, json=True)
    emit('backlog', backlog, to=game_id, json=True)
    emit('new_game', to=game_id)


@socketio.event
def reopen_issue():
    game_id = session['game_id']

    gm.require_driver(game_id, session['player_id'])
    backlog, state, info = gm.reopen_issue(game_id)
    emit('state', state, to=game_id, json=True)
    emit('info', info, to=game_id, json=True)
    emit('backlog', backlog, to=game_id, json=True)
    emit('new_game', to=game_id)


@socketio.event
def park_issue(data):
    game_id = session['game_id']
    status = (data.get('status') if data else None) or 'refinement'
    reason = data.get('reason') if data else None

    gm.require_driver(game_id, session['player_id'])
    backlog, state, info = gm.park_issue(game_id, status, reason)
    emit('state', state, to=game_id, json=True)
    emit('info', info, to=game_id, json=True)
    emit('backlog', backlog, to=game_id, json=True)
    emit('new_game', to=game_id)


@socketio.event
def add_issues(data):
    game_id = session['game_id']
    text = data.get('backlog') if data else None
    fmt = (data.get('backlogFormat') if data else None) or 'paste'

    gm.require_driver(game_id, session['player_id'])
    backlog = gm.add_issues(game_id, text, fmt)
    # Append touches neither the players nor the active round, so only the backlog
    # is re-broadcast (no state / info / new_game).
    emit('backlog', backlog, to=game_id, json=True)


@socketio.event
def end_turn():
    game_id = session['game_id']

    gm.require_driver(game_id, session['player_id'])
    state, info = gm.end_turn(game_id)
    emit('state', state, to=game_id, json=True)
    emit('info', info, to=game_id, json=True)
    emit('new_game', to=game_id)


@socketio.on_error()
def on_error_handler(e):
    body = {'error': True, 'message': str(e), 'code': 0}
    if isinstance(e, PlanningPokerException):
        body['code'] = e.code
    return body


if __name__ == '__main__':
    socketio.run(app)
