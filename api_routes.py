from flask import request, jsonify
from flask_login import login_required, current_user
from app import app
import sqlite3

@app.route('/api/messages')
@login_required
def get_messages():
    chat_type = request.args.get('chat_type')  # 'user' or 'group'
    chat_id = request.args.get('chat_id')
    limit = request.args.get('limit', 50)
    
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    if chat_type == 'user':
        # Get messages between current user and target user
        cursor.execute('''
            SELECT m.id, m.content, m.message_type, m.sender_id, m.created_at, 
                   m.file_url, m.file_name, m.file_size, m.voice_duration, m.is_announcement,
                   u.full_name as sender_name
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.chat_type = 'user' AND 
                  ((m.sender_id = ? AND m.chat_id = ?) OR (m.sender_id = ? AND m.chat_id = ?))
            ORDER BY m.created_at ASC
            LIMIT ?
        ''', (current_user.id, chat_id, chat_id, current_user.id, limit))
    else:
        # Get group messages
        cursor.execute('''
            SELECT m.id, m.content, m.message_type, m.sender_id, m.created_at,
                   m.file_url, m.file_name, m.file_size, m.voice_duration, m.is_announcement,
                   u.full_name as sender_name
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.chat_type = 'group' AND m.chat_id = ?
            ORDER BY m.created_at ASC
            LIMIT ?
        ''', (chat_id, limit))
    
    messages = []
    for row in cursor.fetchall():
        messages.append({
            'id': row[0],
            'content': row[1],
            'message_type': row[2],
            'sender_id': row[3],
            'created_at': row[4],
            'file_url': row[5],
            'file_name': row[6],
            'file_size': row[7],
            'voice_duration': row[8],
            'is_announcement': row[9],
            'sender_name': row[10]
        })
    
    conn.close()
    return jsonify(messages)

@app.route('/api/create_group', methods=['POST'])
@login_required
def create_group():
    data = request.get_json()
    name = data.get('name')
    description = data.get('description', '')
    community_id = data.get('community_id')
    expires_at = data.get('expires_at')
    
    if not name or not community_id:
        return jsonify({'error': 'Name and community ID are required'}), 400
    
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    # Create group
    cursor.execute('''
        INSERT INTO groups (name, description, community_id, created_by, expires_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, description, community_id, current_user.id, expires_at))
    
    group_id = cursor.lastrowid
    
    # Add creator as admin
    cursor.execute('''
        INSERT INTO group_members (group_id, user_id, role)
        VALUES (?, ?, 'admin')
    ''', (group_id, current_user.id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'group_id': group_id})

@app.route('/api/join_group', methods=['POST'])
@login_required
def join_group():
    data = request.get_json()
    group_id = data.get('group_id')
    
    if not group_id:
        return jsonify({'error': 'Group ID is required'}), 400
    
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    # Add user to group
    cursor.execute('''
        INSERT OR IGNORE INTO group_members (group_id, user_id, role)
        VALUES (?, ?, 'member')
    ''', (group_id, current_user.id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/users/search')
@login_required
def search_users():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])
    
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, username, full_name, department, location, avatar_url, is_online
        FROM users
        WHERE (full_name LIKE ? OR username LIKE ? OR department LIKE ?) AND id != ?
        LIMIT 20
    ''', (f'%{query}%', f'%{query}%', f'%{query}%', current_user.id))
    
    users = []
    for row in cursor.fetchall():
        users.append({
            'id': row[0],
            'username': row[1],
            'full_name': row[2],
            'department': row[3],
            'location': row[4],
            'avatar_url': row[5] or '/static/default-avatar.png',
            'is_online': row[6]
        })
    
    conn.close()
    return jsonify(users)
