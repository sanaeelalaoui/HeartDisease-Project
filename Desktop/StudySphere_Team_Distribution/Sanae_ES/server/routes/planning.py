"""
routes/planning.py — Revision planning routes
Auto-generates study sessions from the user's exam list.

Routes (prefix: /api/planning):
  GET    /                   — list all sessions for current user
  POST   /generate           — auto-generate sessions from exams
  PATCH  /<session_id>/done  — mark a session as done
"""
from flask import Blueprint, request, jsonify, session
from bson import ObjectId
from datetime import datetime, timedelta

from db import get_db

def emit_progress_update(user_id):
    """Notify the user's dashboard that progress has changed."""
    try:
        from app import socketio
        if socketio and getattr(socketio, 'server', None):
            socketio.emit('progress_update', {'user_id': str(user_id)}, room=str(user_id))
        else:
            print(f"DEBUG: socketio not fully initialized. Skipping emit for user {user_id}")
    except Exception as e:
        print(f"DEBUG emit_progress_update error: {e}")


planning_bp = Blueprint('planning', __name__)


# ─────────────────────────────────────────────────────────────
# DELETE /api/planning/clear
# ─────────────────────────────────────────────────────────────
@planning_bp.route('/clear', methods=['DELETE'])
def clear_sessions():
    """
    SCRUM-40: Delete all 'todo' sessions for the logged-in user,
    preserving any sessions already marked done or in_progress.
    Allows the user to cleanly regenerate their revision planning.
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    db = get_db()
    result = db.sessions.delete_many({
        'user_id': ObjectId(user_id),
        'status':  {'$in': ['todo', None]},
        'is_done': {'$ne': True},
    })

    return jsonify({
        'message': f'{result.deleted_count} sessions cleared.',
        'deleted': result.deleted_count,
    }), 200


def serialize_session(s):
    """Convert MongoDB session document to JSON-safe dict."""
    return {
        'id':             str(s['_id']),
        'user_id':        str(s['user_id']),
        'subject_id':     str(s['subject_id']),
        'subject_name':   s['subject_name'],
        'date':           s['date'].isoformat(),
        'duration_hours': s['duration_hours'],
        'status':         s.get('status', 'done' if s.get('is_done') else 'todo'),
        'study_method':   s.get('study_method', ''),
        'key_objectives': s.get('key_objectives', []),
        'revision_tips':  s.get('revision_tips', []),
        'created_at':     s['created_at'].isoformat(),
    }


# ─────────────────────────────────────────────────────────────
# GET /api/planning/
# ─────────────────────────────────────────────────────────────
@planning_bp.route('/', methods=['GET'])
def get_sessions():
    """Return all revision sessions for the logged-in user."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    db       = get_db()
    sessions_list = list(db.sessions.find(
        {'user_id': ObjectId(user_id)},
        sort=[('date', 1)]
    ))

    return jsonify({'sessions': [serialize_session(s) for s in sessions_list]}), 200


def get_session_content(subject_name):
    """
    Generate study method, objectives, and tips based on subject name keywords.
    Follows Task 2 requirement for smart default tasks.
    """
    name = subject_name.lower()
    
    # 1. Math / Algo / Calcul
    if any(kw in name for kw in ['math', 'algo', 'calcul', 'statistique']):
        return {
            'method': "Work through exercises progressively. Start with theory, then solve problems step by step.",
            'objectives': [
                "Read and write down all key formulas",
                "Solve 3 warm-up exercises",
                "Attempt 2 past exam problems",
                "Check all your answers and note mistakes",
                "Write a one-line summary of each concept"
            ],
            'tips': [
                "Write formulas by hand before solving",
                "Never skip steps even if they seem obvious",
                "If stuck for 10 minutes, move on and come back"
            ]
        }
    
    # 2. Security / Network / Cyber
    elif any(kw in name for kw in ['securite', 'reseau', 'cyber', 'network']):
        return {
            'method': "Map out all attack types and their defenses, then quiz yourself without looking at notes.",
            'objectives': [
                "List all attack types covered in this chapter",
                "For each attack write its definition + countermeasure",
                "Draw a simple diagram of the network layers",
                "Create 5 flashcard-style questions and answer them",
                "Review the most important protocols"
            ],
            'tips': [
                "Link every attack to its defense mechanism",
                "Draw diagrams from memory first",
                "Focus on acronyms — exams love them"
            ]
        }
    
    # 3. Softeng / UML / Agile
    elif any(kw in name for kw in ['genie', 'logiciel', 'software', 'uml', 'agile']):
        return {
            'method': "Study diagrams first, then patterns, then review methodology.",
            'objectives': [
                "Draw all UML diagram types from memory",
                "Explain 2 design patterns in your own words",
                "Review the Scrum/Agile methodology steps",
                "Write a mini user story for a fictional project",
                "Compare waterfall vs agile in a table"
            ],
            'tips': [
                "Always draw before you read",
                "Link patterns to real project examples",
                "Your cahier des charges is useful here"
            ]
        }
    
    # 4. OS / Kernel / Process
    elif any(kw in name for kw in ['se', 'systeme', 'os', 'kernel', 'process']):
        return {
            'method': "Master concepts through diagrams and comparisons. Definitions are heavily tested in exams.",
            'objectives': [
                "List and explain all process states",
                "Draw the process state transition diagram",
                "Compare 3 scheduling algorithms in a table",
                "Explain memory management techniques",
                "Write definitions of 10 key terms"
            ],
            'tips': [
                "Draw diagrams from memory first",
                "Make comparison tables for algorithms",
                "Memorize exact definitions — exams are definition-heavy"
            ]
        }
    
    # 5. Default
    else:
        return {
            'method': "Read once to understand, then summarize, then review your summary 3 times.",
            'objectives': [
                "Read the full chapter without taking notes first",
                "Go back and highlight all key definitions",
                "Write a one-page handwritten summary",
                "Turn your summary into 5 questions and answer them",
                "Review everything one final time out loud"
            ],
            'tips': [
                "Study in 25-minute blocks with 5-minute breaks (Pomodoro)",
                "Put your phone in another room during sessions",
                "Teach the concept out loud as if explaining to a friend"
            ]
        }

# ─────────────────────────────────────────────────────────────
# POST /api/planning/generate
# ─────────────────────────────────────────────────────────────
@planning_bp.route('/generate', methods=['POST'])
def generate_planning():
    """
    Auto-generate revision sessions from the user's exams.
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    db    = get_db()
    exams = list(db.exams.find(
        {'user_id': ObjectId(user_id)},
        sort=[('exam_date', 1)]
    ))

    if not exams:
        return jsonify({'error': 'No exams found. Add exams first.'}), 400

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Track how many sessions are already planned per date
    existing = list(db.sessions.find({'user_id': ObjectId(user_id)}))
    sessions_per_day = {}
    for s in existing:
        day_key = s['date'].strftime('%Y-%m-%d')
        sessions_per_day[day_key] = sessions_per_day.get(day_key, 0) + 1

    new_sessions = []

    for exam in exams:
        exam_date = exam['exam_date'].replace(hour=0, minute=0, second=0, microsecond=0)
        if exam_date <= today:
            continue

        subject_doc = db.subjects.find_one({
            'user_id': ObjectId(user_id),
            'name':    exam['subject'],
        })
        subject_id   = str(subject_doc['_id']) if subject_doc else 'unknown'
        subject_name = exam['subject']
        
        # Get pre-generated content
        content = get_session_content(subject_name)

        current_day = today
        while current_day < exam_date - timedelta(days=1):
            day_key = current_day.strftime('%Y-%m-%d')
            if sessions_per_day.get(day_key, 0) < 4:
                new_session = {
                    'user_id':        ObjectId(user_id),
                    'subject_id':     subject_id,
                    'subject_name':   subject_name,
                    'date':           current_day + timedelta(hours=9),
                    'duration_hours': 2,
                    'status':         'todo',
                    'is_done':        False,
                    'study_method':   content['method'],
                    'key_objectives': [{'text': obj, 'done': False} for obj in content['objectives']],
                    'revision_tips':  content['tips'],
                    'created_at':     datetime.utcnow(),
                }
                new_sessions.append(new_session)
                sessions_per_day[day_key] = sessions_per_day.get(day_key, 0) + 1

            current_day += timedelta(days=2)

    if new_sessions:
        db.sessions.insert_many(new_sessions)

    all_sessions = list(db.sessions.find(
        {'user_id': ObjectId(user_id)},
        sort=[('date', 1)]
    ))

    return jsonify({
        'message':  f'{len(new_sessions)} sessions generated',
        'sessions': [serialize_session(s) for s in all_sessions],
    }), 201


# ─────────────────────────────────────────────────────────────
# PATCH /api/planning/<session_id>/done
# ─────────────────────────────────────────────────────────────
@planning_bp.route('/<session_id>/done', methods=['PATCH'])
def mark_done(session_id):
    """Toggle a session's is_done status to True."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        db     = get_db()
        result = db.sessions.update_one(
            {'_id': ObjectId(session_id), 'user_id': ObjectId(user_id)},
            {'$set': {'is_done': True, 'status': 'done'}}
        )
    except Exception as e:
        print(f"ERROR mark_done: {e}")
        return jsonify({'error': str(e)}), 500

    if result.matched_count == 0:
        return jsonify({'error': 'Session not found or not yours'}), 404

    updated = db.sessions.find_one({'_id': ObjectId(session_id)})
    
    # Real-time update
    emit_progress_update(user_id)
    
    return jsonify({'message': 'Session marked as done', 'session': serialize_session(updated)}), 200


# ─────────────────────────────────────────────────────────────
# PATCH /api/planning/<session_id>
# ─────────────────────────────────────────────────────────────
@planning_bp.route('/<session_id>', methods=['PATCH'])
def update_session(session_id):
    """Update session status or objectives."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    print(f"DEBUG update_session for {session_id}: {data}")
    db   = get_db()
    
    update_fields = {}
    if 'status' in data:
        update_fields['status'] = data['status']
        update_fields['is_done'] = (data['status'] == 'done')
    
    if 'key_objectives' in data:
        update_fields['key_objectives'] = data['key_objectives']

    if not update_fields:
        return jsonify({'error': 'No fields to update'}), 400

    try:
        result = db.sessions.update_one(
            {'_id': ObjectId(session_id), 'user_id': ObjectId(user_id)},
            {'$set': update_fields}
        )
    except Exception as e:
        print(f"ERROR update_session: {e}")
        return jsonify({'error': str(e)}), 500

    if result.matched_count == 0:
        return jsonify({'error': 'Session not found or not yours'}), 404

    updated = db.sessions.find_one({'_id': ObjectId(session_id)})
    
    # Real-time update
    emit_progress_update(user_id)
    
    return jsonify({'message': 'Session updated', 'session': serialize_session(updated)}), 200


# ─────────────────────────────────────────────────────────────
# Sharing Routes
# ─────────────────────────────────────────────────────────────

@planning_bp.route('/share', methods=['POST'])
def share_calendar():
    """
    Share the user's entire calendar or a specific session with another user (by email).
    JSON: { "email": "...", "type": "full" | "session", "session_id": "..." }
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    target_email = data.get('email', '').strip().lower()
    share_type = data.get('type', 'full') # 'full' or 'session'
    target_session_id = data.get('session_id')

    if not target_email:
        return jsonify({'error': 'Target email is required'}), 400

    db = get_db()
    # Find the target user
    target_user = db.users.find_one({'email': target_email})
    if not target_user:
        return jsonify({'error': f'User with email {target_email} not found'}), 404

    if str(target_user['_id']) == user_id:
        return jsonify({'error': 'You cannot share your calendar with yourself'}), 400

    # Check if already shared
    query = {
        'owner_id': ObjectId(user_id),
        'shared_with': target_user['_id'],
        'type': share_type
    }
    if share_type == 'session' and target_session_id:
        query['session_id'] = ObjectId(target_session_id)

    if db.shares.find_one(query):
        return jsonify({'error': 'Already shared with this user'}), 409

    # Create share record
    share_record = {
        'owner_id': ObjectId(user_id),
        'shared_with': target_user['_id'],
        'type': share_type,
        'created_at': datetime.utcnow()
    }
    if share_type == 'session' and target_session_id:
        share_record['session_id'] = ObjectId(target_session_id)
    
    db.shares.insert_one(share_record)

    return jsonify({'message': f'Calendar shared with {target_email}'}), 201


@planning_bp.route('/shared-with-me', methods=['GET'])
def get_shared_with_me():
    """List calendars and sessions shared with the current user."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    db = get_db()
    shares = list(db.shares.find({'shared_with': ObjectId(user_id)}))
    
    # Add local_name to results
    results = []
    for s in shares:
        owner = db.users.find_one({'_id': s['owner_id']})
        results.append({
            'id': str(s['_id']),
            'owner_id': str(s['owner_id']),
            'owner_name': owner['name'] if owner else 'Unknown',
            'local_name': s.get('local_name'),
            'type': s['type'],
            'session_id': str(s['session_id']) if 'session_id' in s else None,
            'created_at': s['created_at'].isoformat()
        })
    
    return jsonify({'shares': results}), 200


@planning_bp.route('/shares/<share_id>', methods=['PATCH'])
def update_share(share_id):
    """Update a share record (e.g., local_name)."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    local_name = data.get('local_name', '').strip()

    db = get_db()
    result = db.shares.update_one(
        {'_id': ObjectId(share_id), 'shared_with': ObjectId(user_id)},
        {'$set': {'local_name': local_name}}
    )

    if result.matched_count == 0:
        return jsonify({'error': 'Share record not found or not yours'}), 404

    return jsonify({'message': 'Share updated'}), 200


@planning_bp.route('/shares/<share_id>', methods=['DELETE'])
def delete_share(share_id):
    """Remove a shared calendar/session from the user's list."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    db = get_db()
    result = db.shares.delete_one(
        {'_id': ObjectId(share_id), 'shared_with': ObjectId(user_id)}
    )

    if result.deleted_count == 0:
        return jsonify({'error': 'Share record not found or not yours'}), 404

    return jsonify({'message': 'Shared access removed'}), 200


@planning_bp.route('/view-shared/<owner_id>', methods=['GET'])
def view_shared_calendar(owner_id):
    """Fetch sessions for a shared calendar."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    db = get_db()
    # Verify access (either full calendar share or specific sessions)
    share = db.shares.find_one({
        'owner_id': ObjectId(owner_id),
        'shared_with': ObjectId(user_id),
        'type': 'full'
    })
    
    if share:
        # Full access: return all sessions
        sessions_list = list(db.sessions.find(
            {'user_id': ObjectId(owner_id)},
            sort=[('date', 1)]
        ))
    else:
        # Check for specific session shares
        session_shares = list(db.shares.find({
            'owner_id': ObjectId(owner_id),
            'shared_with': ObjectId(user_id),
            'type': 'session'
        }))
        if not session_shares:
            return jsonify({'error': 'Access denied'}), 403
            
        session_ids = [s['session_id'] for s in session_shares]
        sessions_list = list(db.sessions.find(
            {'_id': {'$in': session_ids}},
            sort=[('date', 1)]
        ))

    return jsonify({'sessions': [serialize_session(s) for s in sessions_list]}), 200


@planning_bp.route('/shared-by-me', methods=['GET'])
def get_shared_by_me():
    """List what the current user has shared with others."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    db = get_db()
    shares = list(db.shares.find({'owner_id': ObjectId(user_id)}))
    
    results = []
    for s in shares:
        recipient = db.users.find_one({'_id': s['shared_with']})
        results.append({
            'id': str(s['_id']),
            'shared_with_email': recipient['email'] if recipient else 'Unknown',
            'type': s['type'],
            'session_id': str(s['session_id']) if 'session_id' in s else None,
            'created_at': s['created_at'].isoformat()
        })
    
    return jsonify({'shares': results}), 200

