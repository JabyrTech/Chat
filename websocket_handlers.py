from flask_socketio import emit, join_room, leave_room
from flask_login import current_user
from app import socketio
import sqlite3
from datetime import datetime
import json

# Store active users and their socket IDs
active_users = {}

@socketio.on('connect')
def on_connect():
    if current_user.is_authenticated:
        active_users[current_user.id] = request.sid
        
        # Update user online status
        conn = sqlite3.connect('docktalk.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_online = TRUE WHERE id = ?', (current_user.id,))
        conn.commit()
        conn.close()
        
        # Join user to their personal room
        join_room(f"user_{current_user.id}")
        
        # Join user to all their group rooms
        conn = sqlite3.connect('docktalk.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT g.id FROM groups g
            JOIN group_members gm ON g.id = gm.group_id
            WHERE gm.user_id = ?
        ''', (current_user.id,))
        
        for (group_id,) in cursor.fetchall():
            join_room(f"group_{group_id}")
        
        conn.close()
        
        emit('user_status', {'user_id': current_user.id, 'status': 'online'}, broadcast=True)
        print(f"User {current_user.username} connected")

@socketio.on('disconnect')
def on_disconnect():
    if current_user.is_authenticated:
        # Remove from active users
        if current_user.id in active_users:
            del active_users[current_user.id]
        
        # Update user offline status
        conn = sqlite3.connect('docktalk.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_online = FALSE, last_seen = CURRENT_TIMESTAMP WHERE id = ?', (current_user.id,))
        conn.commit()
        conn.close()
        
        emit('user_status', {'user_id': current_user.id, 'status': 'offline'}, broadcast=True)
        print(f"User {current_user.username} disconnected")

@socketio.on('join_chat')
def on_join_chat(data):
    if not current_user.is_authenticated:
        return
    
    chat_type = data.get('type')  # 'user' or 'group'
    chat_id = data.get('id')
    
    if chat_type == 'user':
        join_room(f"user_{chat_id}")
    elif chat_type == 'group':
        join_room(f"group_{chat_id}")
    
    print(f"User {current_user.username} joined {chat_type}_{chat_id}")

@socketio.on('leave_chat')
def on_leave_chat(data):
    if not current_user.is_authenticated:
        return
    
    chat_type = data.get('type')
    chat_id = data.get('id')
    
    if chat_type == 'user':
        leave_room(f"user_{chat_id}")
    elif chat_type == 'group':
        leave_room(f"group_{chat_id}")

@socketio.on('send_message')
def on_send_message(data):
    if not current_user.is_authenticated:
        return
    
    message_content = data.get('content', '').strip()
    chat_type = data.get('chat_type')  # 'user' or 'group'
    chat_id = data.get('chat_id')
    message_type = data.get('message_type', 'text')  # 'text', 'image', 'file', 'voice'
    file_data = data.get('file_data', {})
    
    if not message_content and message_type == 'text':
        return
    
    # Save message to database
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO messages (content, message_type, sender_id, chat_type, chat_id, file_url, file_name, file_size, voice_duration)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        message_content,
        message_type,
        current_user.id,
        chat_type,
        chat_id,
        file_data.get('url'),
        file_data.get('name'),
        file_data.get('size'),
        file_data.get('duration')
    ))
    
    message_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Prepare message data for broadcast
    message_data = {
        'id': message_id,
        'content': message_content,
        'type': message_type,
        'sender': {
            'id': current_user.id,
            'name': current_user.full_name,
            'username': current_user.username,
            'avatar': current_user.avatar_url or '/static/default-avatar.png'
        },
        'timestamp': datetime.now().isoformat(),
        'chat_type': chat_type,
        'chat_id': chat_id,
        'file_data': file_data
    }
    
    # Broadcast message to appropriate room
    if chat_type == 'user':
        # Send to both sender and receiver
        emit('new_message', message_data, room=f"user_{current_user.id}")
        emit('new_message', message_data, room=f"user_{chat_id}")
    elif chat_type == 'group':
        emit('new_message', message_data, room=f"group_{chat_id}")
    
    print(f"Message sent by {current_user.username} to {chat_type}_{chat_id}")

@socketio.on('send_announcement')
def on_send_announcement(data):
    if not current_user.is_authenticated:
        return
    
    content = data.get('content', '').strip()
    community_id = data.get('community_id')
    
    if not content:
        return
    
    # Get all groups in the community
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM groups WHERE community_id = ?', (community_id,))
    group_ids = [row[0] for row in cursor.fetchall()]
    
    # Send announcement to all groups
    for group_id in group_ids:
        cursor.execute('''
            INSERT INTO messages (content, message_type, sender_id, chat_type, chat_id, is_announcement)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (content, 'announcement', current_user.id, 'group', group_id, True))
        
        message_id = cursor.lastrowid
        
        # Broadcast announcement
        announcement_data = {
            'id': message_id,
            'content': content,
            'type': 'announcement',
            'sender': {
                'id': current_user.id,
                'name': current_user.full_name,
                'username': current_user.username
            },
            'timestamp': datetime.now().isoformat(),
            'chat_type': 'group',
            'chat_id': group_id,
            'is_announcement': True
        }
        
        emit('new_message', announcement_data, room=f"group_{group_id}")
    
    conn.commit()
    conn.close()
    
    print(f"Announcement sent by {current_user.username} to community {community_id}")

@socketio.on('typing_start')
def on_typing_start(data):
    if not current_user.is_authenticated:
        return
    
    chat_type = data.get('chat_type')
    chat_id = data.get('chat_id')
    
    typing_data = {
        'user': {
            'id': current_user.id,
            'name': current_user.full_name
        },
        'chat_type': chat_type,
        'chat_id': chat_id
    }
    
    if chat_type == 'user':
        emit('user_typing', typing_data, room=f"user_{chat_id}")
    elif chat_type == 'group':
        emit('user_typing', typing_data, room=f"group_{chat_id}")

@socketio.on('typing_stop')
def on_typing_stop(data):
    if not current_user.is_authenticated:
        return
    
    chat_type = data.get('chat_type')
    chat_id = data.get('chat_id')
    
    typing_data = {
        'user': {
            'id': current_user.id,
            'name': current_user.full_name
        },
        'chat_type': chat_type,
        'chat_id': chat_id
    }
    
    if chat_type == 'user':
        emit('user_stop_typing', typing_data, room=f"user_{chat_id}")
    elif chat_type == 'group':
        emit('user_stop_typing', typing_data, room=f"group_{chat_id}")

# Call handling
@socketio.on('start_call')
def on_start_call(data):
    if not current_user.is_authenticated:
        return
    
    call_type = data.get('type')  # 'audio' or 'video'
    target_type = data.get('target_type')  # 'user' or 'group'
    target_id = data.get('target_id')
    
    call_data = {
        'call_id': f"call_{datetime.now().timestamp()}",
        'type': call_type,
        'caller': {
            'id': current_user.id,
            'name': current_user.full_name,
            'avatar': current_user.avatar_url or '/static/default-avatar.png'
        },
        'target_type': target_type,
        'target_id': target_id
    }
    
    if target_type == 'user':
        emit('incoming_call', call_data, room=f"user_{target_id}")
    elif target_type == 'group':
        emit('incoming_call', call_data, room=f"group_{target_id}")
    
    print(f"Call started by {current_user.username} to {target_type}_{target_id}")

@socketio.on('answer_call')
def on_answer_call(data):
    call_id = data.get('call_id')
    caller_id = data.get('caller_id')
    
    answer_data = {
        'call_id': call_id,
        'answerer': {
            'id': current_user.id,
            'name': current_user.full_name
        }
    }
    
    emit('call_answered', answer_data, room=f"user_{caller_id}")

@socketio.on('end_call')
def on_end_call(data):
    call_id = data.get('call_id')
    target_type = data.get('target_type')
    target_id = data.get('target_id')
    
    end_data = {
        'call_id': call_id,
        'ended_by': current_user.id
    }
    
    if target_type == 'user':
        emit('call_ended', end_data, room=f"user_{target_id}")
    elif target_type == 'group':
        emit('call_ended', end_data, room=f"group_{target_id}")
