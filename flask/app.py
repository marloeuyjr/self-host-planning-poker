import errno
import os
import sys
import uuid

from flask import Flask, request, session, render_template
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

if app.config['DEBUG']:
    real_db = SqliteDatabase('database.db')
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
    session['player_id'] = player_id
    player_name = data['name']
    spectator = data['spectator']
    game_id = data['game']

    session['game_id'] = game_id
    join_room(game_id)

    info, state = gm.join_game(game_id, player_id, player_name, spectator)
    emit('state', state, to=game_id, json=True)

    # Hand the room the current backlog so late joiners see the queue + pointer (S4).
    backlog = gm.backlog(game_id)
    if backlog['issues']:
        emit('backlog', backlog, to=game_id, json=True)

    info['playerId'] = player_id
    return info


@socketio.event
def disconnect():
    player_id = session['player_id']
    game_id = session['game_id']

    state = gm.leave_game(game_id, player_id)
    leave_room(game_id)
    emit('state', state, to=game_id, json=True)

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

    info, state = gm.set_deck(game_id, deck_name)
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

    state, info, results = gm.reveal_cards(game_id)
    emit('state', state, to=game_id, json=True)
    emit('info', info, to=game_id, json=True)
    emit('results', results, to=game_id, json=True)


@socketio.event
def accept_estimate(data):
    game_id = session['game_id']
    value = data.get('value') if data else None

    backlog, state, info = gm.accept_estimate(game_id, value)
    emit('state', state, to=game_id, json=True)
    emit('info', info, to=game_id, json=True)
    emit('backlog', backlog, to=game_id, json=True)
    emit('new_game', to=game_id)


@socketio.event
def revote():
    game_id = session['game_id']

    backlog, state, info = gm.revote(game_id)
    emit('state', state, to=game_id, json=True)
    emit('info', info, to=game_id, json=True)
    emit('backlog', backlog, to=game_id, json=True)
    emit('new_game', to=game_id)


@socketio.event
def select_issue(data):
    game_id = session['game_id']
    index = data['index']

    backlog, state, info = gm.select_issue(game_id, index)
    emit('state', state, to=game_id, json=True)
    emit('info', info, to=game_id, json=True)
    emit('backlog', backlog, to=game_id, json=True)
    emit('new_game', to=game_id)


@socketio.event
def park_issue(data):
    game_id = session['game_id']
    status = (data.get('status') if data else None) or 'refinement'
    reason = data.get('reason') if data else None

    backlog, state, info = gm.park_issue(game_id, status, reason)
    emit('state', state, to=game_id, json=True)
    emit('info', info, to=game_id, json=True)
    emit('backlog', backlog, to=game_id, json=True)
    emit('new_game', to=game_id)


@socketio.event
def end_turn():
    game_id = session['game_id']

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
