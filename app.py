import flask_socketio, socketio, engineio
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room, rooms
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import uuid
from datetime import datetime
import json
import mimetypes
import logging, os
from PIL import Image
import math
app = Flask(__name__)
app.config['SECRET_KEY'] = 'nimasa-docktalk-secret-key-2024'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static/uploads/images', exist_ok=True)
os.makedirs('static/uploads/files', exist_ok=True)
os.makedirs('static/uploads/voice', exist_ok=True)
os.environ["EVENTLET_NO_GREENDNS"] = "yes"   # avoid dnspython headaches
#socketio = SocketIO(app,async_mode="eventlet",cors_allowed_origins="*",logger=False,engineio_logger=False,)
socketio = SocketIO(app,async_mode="threading",cors_allowed_origins="*",logger=False,engineio_logger=False,)
#socketio = SocketIO(app, cors_allowed_origins="*")
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Store active users and their socket IDs
active_users = {}
# Store active calls
active_calls = {}

# Database initialization
def init_db():
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            department TEXT,
            location TEXT,
            phone TEXT,
            bio TEXT,
            avatar_url TEXT,
            is_online BOOLEAN DEFAULT FALSE,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Communities table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS communities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            avatar_url TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
    ''')
    
    # Groups table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            avatar_url TEXT,
            community_id INTEGER,
            created_by INTEGER,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (community_id) REFERENCES communities (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
    ''')
    
    # Messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            message_type TEXT DEFAULT 'text',
            sender_id INTEGER NOT NULL,
            chat_type TEXT NOT NULL,
            chat_id INTEGER NOT NULL,
            file_url TEXT,
            file_name TEXT,
            file_size TEXT,
            voice_duration INTEGER,
            is_announcement BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sender_id) REFERENCES users (id)
                   
        )
    ''')
    
    # Group members table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT DEFAULT 'member',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES groups (id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(group_id, user_id)
        )
    ''')
    
    # Community members table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS community_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            community_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT DEFAULT 'member',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (community_id) REFERENCES communities (id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(community_id, user_id)
        )
    ''')
    
    # Calls table for call history
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id TEXT UNIQUE NOT NULL,
            caller_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            call_type TEXT NOT NULL,
            status TEXT DEFAULT 'initiated',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            duration INTEGER DEFAULT 0,
            FOREIGN KEY (caller_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username, email, full_name, department=None, location=None, phone=None, bio=None, avatar_url=None, is_online=False, last_seen=None):
        self.id = id
        self.username = username
        self.email = email
        self.full_name = full_name
        self.department = department
        self.location = location
        self.phone = phone
        self.bio = bio
        self.avatar_url = avatar_url
        self.is_online = is_online
        self.last_seen = last_seen

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    
    if user_data:
        return User(
            id=user_data[0],
            username=user_data[1],
            email=user_data[2],
            full_name=user_data[4],
            department=user_data[5],
            location=user_data[6],
            phone=user_data[7],
            bio=user_data[8],
            avatar_url=user_data[9],
            is_online=user_data[10],
            last_seen=user_data[11]
        )
    return None

# Routes
@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        conn = sqlite3.connect('docktalk.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ? OR email = ?', (username, username))
        user_data = cursor.fetchone()
        conn.close()
        
        if user_data and check_password_hash(user_data[3], password):
            user = User(
                id=user_data[0],
                username=user_data[1],
                email=user_data[2],
                full_name=user_data[4],
                department=user_data[5],
                location=user_data[6],
                phone=user_data[7],
                bio=user_data[8],
                avatar_url=user_data[9]
            )
            login_user(user)
            
            # Update user online status
            conn = sqlite3.connect('docktalk.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET is_online = TRUE WHERE id = ?', (user.id,))
            conn.commit()
            conn.close()
            
            return jsonify({'success': True, 'redirect': url_for('index')})
        else:
            return jsonify({'success': False, 'error': 'Invalid credentials'})
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        full_name = data.get('full_name')
        department = data.get('department', '')
        location = data.get('location', '')
        phone = data.get('phone', '')
        
        # Check if user already exists
        conn = sqlite3.connect('docktalk.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email))
        existing_user = cursor.fetchone()
        
        if existing_user:
            conn.close()
            return jsonify({'success': False, 'error': 'Username or email already exists'})
        
        # Create new user
        password_hash = generate_password_hash(password)
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, full_name, department, location, phone)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (username, email, password_hash, full_name, department, location, phone))
        
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Auto-join NIMASA community
        add_user_to_nimasa_community(user_id)
        
        return jsonify({'success': True, 'redirect': url_for('login')})
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    # Update user offline status
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_online = FALSE, last_seen = CURRENT_TIMESTAMP WHERE id = ?', (current_user.id,))
    conn.commit()
    conn.close()
    
    logout_user()
    return redirect(url_for('login'))

# API Routes
@app.route('/api/chats')
@login_required
def get_chats():
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    # Get individual chats (users the current user has messaged)
    cursor.execute('''
        SELECT DISTINCT u.id, u.username, u.full_name, u.department, u.location, 
               u.phone, u.email, u.bio, u.avatar_url, u.is_online, u.last_seen,
               m.content as last_message, m.created_at as last_message_time
        FROM users u
        LEFT JOIN messages m ON (
            (m.sender_id = u.id AND m.chat_type = 'user' AND m.chat_id = ?) OR
            (m.sender_id = ? AND m.chat_type = 'user' AND m.chat_id = u.id)
        )
        WHERE u.id != ? AND m.id IN (
            SELECT MAX(m2.id) FROM messages m2 
            WHERE m2.chat_type = 'user' AND 
            ((m2.sender_id = u.id AND m2.chat_id = ?) OR (m2.sender_id = ? AND m2.chat_id = u.id))
        )
        ORDER BY m.created_at DESC
    ''', (current_user.id, current_user.id, current_user.id, current_user.id, current_user.id))
    
    individual_chats = []
    for row in cursor.fetchall():
        individual_chats.append({
            'id': str(row[0]),
            'name': row[2],
            'username': row[1],
            'avatar': row[8] or '/static/default-avatar.png',
            'lastMessage': row[11] or 'No messages yet',
            'timestamp': row[12] or datetime.now().isoformat(),
            'unread': 0,  # TODO: implement unread count
            'type': 'individual',
            'isOnline': bool(row[9]),
            'department': row[3],
            'location': row[4],
            'phone': row[5],
            'email': row[6],
            'bio': row[7],
            'lastSeen': row[10]
        })
    
    conn.close()
    return jsonify(individual_chats)

@app.route('/api/groups')
@login_required
def get_groups():
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    # Get groups the user is a member of
    cursor.execute('''
        SELECT g.id, g.name, g.description, g.avatar_url, g.expires_at, g.created_at,
               c.name as community_name, c.id as community_id,
               (SELECT COUNT(*) FROM group_members WHERE group_id = g.id) as member_count,
               m.content as last_message, m.created_at as last_message_time
        FROM groups g
        JOIN group_members gm ON g.id = gm.group_id
        JOIN communities c ON g.community_id = c.id
        LEFT JOIN messages m ON m.chat_type = 'group' AND m.chat_id = g.id
        WHERE gm.user_id = ? AND (m.id IS NULL OR m.id IN (
            SELECT MAX(m2.id) FROM messages m2 
            WHERE m2.chat_type = 'group' AND m2.chat_id = g.id
        ))
        ORDER BY COALESCE(m.created_at, g.created_at) DESC
    ''', (current_user.id,))
    
    groups = []
    for row in cursor.fetchall():
        groups.append({
            'id': str(row[0]),
            'name': row[1],
            'description': row[2],
            'avatar': row[3] or '/static/default-group.png',
            'expiresAt': row[4],
            'createdAt': row[5],
            'community': {
                'id': str(row[7]),
                'name': row[6]
            },
            'members': row[8],
            'lastMessage': row[9] or 'No messages yet',
            'timestamp': row[10] or row[5],
            'unread': 0  # TODO: implement unread count
        })

    for row in cursor.fetchall():
        group_id, name, desc, expiry = row
        if expiry:
            expiry_dt = datetime.datetime.fromisoformat(expiry)
            if expiry_dt < row:
                continue  # skip expired
        groups.append({"id": group_id, "name": name, "description": desc})

    
    conn.close()
    return jsonify(groups)



@app.route("/api/group_status")
@login_required
def check_group_status():
    group_id = request.args.get("group_id")
    conn = sqlite3.connect("docktalk.db")
    cursor = conn.cursor()
    cursor.execute("SELECT expires_at FROM groups WHERE id = ?", (group_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        expiry_dt = datetime.datetime.fromisoformat(row[0])
        if datetime.datetime.utcnow() > expiry_dt:
            return jsonify({"expired": True})
    return jsonify({"expired": False})


@app.route('/api/communities')
@login_required
def get_communities():
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    # Get communities the user is a member of
    cursor.execute('''
        SELECT c.id, c.name, c.description, c.avatar_url, c.created_at,
               (SELECT COUNT(*) FROM community_members WHERE community_id = c.id) as member_count
        FROM communities c
        JOIN community_members cm ON c.id = cm.community_id
        WHERE cm.user_id = ?
        ORDER BY c.created_at DESC
    ''', (current_user.id,))
    
    communities = []
    for row in cursor.fetchall():
        community_id = row[0]
        
        # Get groups in this community that the user is a member of
        cursor.execute('''
            SELECT g.id, g.name, g.description, g.avatar_url, g.expires_at, g.created_at,
                   (SELECT COUNT(*) FROM group_members WHERE group_id = g.id) as member_count,
                   m.content as last_message, m.created_at as last_message_time
            FROM groups g
            JOIN group_members gm ON g.id = gm.group_id
            LEFT JOIN messages m ON m.chat_type = 'group' AND m.chat_id = g.id
            WHERE g.community_id = ? AND gm.user_id = ? AND (m.id IS NULL OR m.id IN (
                SELECT MAX(m2.id) FROM messages m2 
                WHERE m2.chat_type = 'group' AND m2.chat_id = g.id
            ))
            ORDER BY COALESCE(m.created_at, g.created_at) DESC
        ''', (community_id, current_user.id))
        
        groups = []
        for group_row in cursor.fetchall():
            groups.append({
                'id': str(group_row[0]),
                'name': group_row[1],
                'description': group_row[2],
                'avatar': group_row[3] or '/static/default-group.png',
                'expiresAt': group_row[4],
                'createdAt': group_row[5],
                'members': group_row[6],
                'lastMessage': group_row[7] or 'No messages yet',
                'timestamp': group_row[8] or group_row[5],
                'unread': 0
            })
        
        communities.append({
            'id': str(row[0]),
            'name': row[1],
            'description': row[2],
            'avatar': row[3] or '/static/default-community.png',
            'createdAt': row[4],
            'members': row[5],
            'groups': groups
        })
    
    conn.close()
    return jsonify(communities)

# @app.route('/api/messages')
# @login_required
# def get_messages():
#     chat_type = request.args.get('chat_type')  # 'user' or 'group'
#     chat_id = request.args.get('chat_id')
#     limit = request.args.get('limit', 50)
    
#     conn = sqlite3.connect('docktalk.db')
#     cursor = conn.cursor()
    
#     if chat_type == 'user':
#         # Get messages between current user and target user
#         cursor.execute('''
#             SELECT m.id, m.content, m.message_type, m.sender_id, m.created_at, 
#                    m.file_url, m.file_name, m.file_size, m.voice_duration, m.is_announcement,
#                    u.full_name as sender_name
#             FROM messages m
#             JOIN users u ON m.sender_id = u.id
#             WHERE m.chat_type = 'user' AND 
#                   ((m.sender_id = ? AND m.chat_id = ?) OR (m.sender_id = ? AND m.chat_id = ?))
#             ORDER BY m.created_at ASC
#             LIMIT ?
#         ''', (current_user.id, chat_id, chat_id, current_user.id, limit))
#     else:
#         # Get group messages
#         cursor.execute('''
#             SELECT m.id, m.content, m.message_type, m.sender_id, m.created_at,
#                    m.file_url, m.file_name, m.file_size, m.voice_duration, m.is_announcement,
#                    u.full_name as sender_name
#             FROM messages m
#             JOIN users u ON m.sender_id = u.id
#             WHERE m.chat_type = 'group' AND m.chat_id = ?
#             ORDER BY m.created_at ASC
#             LIMIT ?
#         ''', (chat_id, limit))
    
#     messages = []
#     for row in cursor.fetchall():
#         messages.append({
#             'id': row[0],
#             'content': row[1],
#             'message_type': row[2],
#             'sender_id': row[3],
#             'created_at': row[4],
#             'file_url': row[5],
#             'file_name': row[6],
#             'file_size': row[7],
#             'voice_duration': row[8],
#             'is_announcement': row[9],
#             'sender_name': row[10]
#         })
    
#     conn.close()
#     return jsonify(messages)

@app.route('/api/create_community', methods=['POST'])
@login_required
def create_community():
    data = request.get_json()
    name = data.get('name')
    description = data.get('description', '')
    
    if not name:
        return jsonify({'error': 'Community name is required'}), 400
    
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    # Create community
    cursor.execute('''
        INSERT INTO communities (name, description, created_by)
        VALUES (?, ?, ?)
    ''', (name, description, current_user.id))
    
    community_id = cursor.lastrowid
    
    # Add creator as admin
    cursor.execute('''
        INSERT INTO community_members (community_id, user_id, role)
        VALUES (?, ?, 'admin')
    ''', (community_id, current_user.id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'community_id': community_id})

@app.route('/api/create_group', methods=['POST'])
@login_required
def create_group():
    data = request.get_json()
    name = data.get('name')
    description = data.get('description', '')
    community_id = data.get('community_id')
    expires_at = data.get('expires_at')
    
    if not name or not community_id:
        return jsonify({'error': 'Group name and community ID are required'}), 400
    
    # Check if user is member of the community
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT role FROM community_members 
        WHERE community_id = ? AND user_id = ?
    ''', (community_id, current_user.id))
    
    membership = cursor.fetchone()
    if not membership:
        conn.close()
        return jsonify({'error': 'You must be a member of the community to create groups'}), 403
    
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

@app.route('/api/join_community', methods=['POST'])
@login_required
def join_community():
    data = request.get_json()
    community_id = data.get('community_id')
    
    if not community_id:
        return jsonify({'error': 'Community ID is required'}), 400
    
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    # Add user to community
    cursor.execute('''
        INSERT OR IGNORE INTO community_members (community_id, user_id, role)
        VALUES (?, ?, 'member')
    ''', (community_id, current_user.id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/groups/all')
@login_required
def get_all_groups():
    """Get all groups in communities the user is a member of"""
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT g.id, g.name, g.description, g.avatar_url, g.expires_at, g.created_at,
               c.name as community_name, c.id as community_id,
               (SELECT COUNT(*) FROM group_members WHERE group_id = g.id) as member_count,
               CASE WHEN gm.user_id IS NOT NULL THEN 1 ELSE 0 END as is_member
        FROM groups g
        JOIN communities c ON g.community_id = c.id
        JOIN community_members cm ON c.id = cm.community_id
        LEFT JOIN group_members gm ON g.id = gm.group_id AND gm.user_id = ?
        WHERE cm.user_id = ?
        ORDER BY c.name, g.name
    ''', (current_user.id, current_user.id))
    
    groups = []
    for row in cursor.fetchall():
        groups.append({
            'id': str(row[0]),
            'name': row[1],
            'description': row[2],
            'avatar': row[3] or '/static/default-group.png',
            'expiresAt': row[4],
            'createdAt': row[5],
            'community': {
                'id': str(row[7]),
                'name': row[6]
            },
            'members': row[8],
            'is_member': bool(row[9])
        })
    
    conn.close()
    return jsonify(groups)

@app.route('/api/join_group', methods=['POST'])
@login_required
def join_group():
    data = request.get_json()
    group_id = data.get('group_id')
    
    if not group_id:
        return jsonify({'error': 'Group ID is required'}), 400
    
    # Check if user is member of the group's community
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT g.community_id FROM groups g
        JOIN community_members cm ON g.community_id = cm.community_id
        WHERE g.id = ? AND cm.user_id = ?
    ''', (group_id, current_user.id))
    
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'You must be a member of the community to join this group'}), 403
    
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

@app.route('/api/communities/all')
@login_required
def get_all_communities():
    """Get all communities for joining"""
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.id, c.name, c.description, c.avatar_url, c.created_at,
               (SELECT COUNT(*) FROM community_members WHERE community_id = c.id) as member_count,
               CASE WHEN cm.user_id IS NOT NULL THEN 1 ELSE 0 END as is_member
        FROM communities c
        LEFT JOIN community_members cm ON c.id = cm.community_id AND cm.user_id = ?
        ORDER BY c.created_at DESC
    ''', (current_user.id,))
    
    communities = []
    for row in cursor.fetchall():
        communities.append({
            'id': str(row[0]),
            'name': row[1],
            'description': row[2],
            'avatar': row[3] or '/static/default-community.png',
            'createdAt': row[4],
            'members': row[5],
            'is_member': bool(row[6])
        })
    
    conn.close()
    return jsonify(communities)

@app.route('/api/start_chat', methods=['POST'])
@login_required
def start_chat():
    """Start a new chat with a user"""
    data = request.get_json()
    target_user_id = data.get('user_id')
    
    if not target_user_id:
        return jsonify({'error': 'User ID is required'}), 400
    
    # Get target user info
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, username, full_name, department, location, phone, email, bio, avatar_url, is_online
        FROM users WHERE id = ?
    ''', (target_user_id,))
    
    user_data = cursor.fetchone()
    if not user_data:
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    
    conn.close()
    
    chat_info = {
        'id': str(user_data[0]),
        'name': user_data[2],
        'username': user_data[1],
        'avatar': user_data[8] or '/static/default-avatar.png',
        'lastMessage': 'Start a conversation',
        'timestamp': datetime.now().isoformat(),
        'unread': 0,
        'type': 'individual',
        'isOnline': bool(user_data[9]),
        'department': user_data[3],
        'location': user_data[4],
        'phone': user_data[5],
        'email': user_data[6],
        'bio': user_data[7]
    }
    
    return jsonify({'success': True, 'chat': chat_info})

# File handling functions
ALLOWED_EXTENSIONS = {
    'image': {'png', 'jpg', 'jpeg', 'gif', 'webp'},
    'file': {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'zip', 'rar', 'png', 'jpg', 'jpeg', 'gif', 'webp'},
    'voice': {'wav', 'mp3', 'ogg', 'webm', 'm4a'}
}

def allowed_file(filename, file_type):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS.get(file_type, set())

def format_file_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    file_type = request.form.get('type', 'file')
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and allowed_file(file.filename, file_type):
        # Generate unique filename
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        
        # Determine upload path based on file type
        if file_type == 'image':
            upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'images')
        elif file_type == 'voice':
            upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'voice')
        else:
            upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'files')
        
        os.makedirs(upload_path, exist_ok=True)
        file_path = os.path.join(upload_path, unique_filename)
        file.save(file_path)
        
        # Process image files
        if file_type == 'image':
            try:
                # Create thumbnail
                with Image.open(file_path) as img:
                    img.thumbnail((800, 600), Image.Resampling.LANCZOS)
                    img.save(file_path, optimize=True, quality=85)
            except Exception as e:
                print(f"Error processing image: {e}")
        
        # Get file size
        file_size = os.path.getsize(file_path)
        file_size_str = format_file_size(file_size)
        
        # Generate file URL - Fix the path issue
        if file_type == 'image':
            file_url = f"/static/uploads/images/{unique_filename}"
        elif file_type == 'voice':
            file_url = f"/static/uploads/voice/{unique_filename}"
        else:
            file_url = f"/static/uploads/files/{unique_filename}"
        
        return jsonify({
            'success': True,
            'file_url': file_url,
            'file_name': file.filename,
            'file_size': file_size_str,
            'file_type': file_type,
            'mime_type': mimetypes.guess_type(file.filename)[0]
        })
    
    return jsonify({'error': 'File type not allowed'}), 400

def add_user_to_nimasa_community(user_id):
    """Add new user to NIMASA community automatically"""
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    # Check if NIMASA community exists, create if not
    cursor.execute('SELECT id FROM communities WHERE name = ?', ('NIMASA Maritime Community',))
    community = cursor.fetchone()
    
    if not community:
        cursor.execute('''
            INSERT INTO communities (name, description, created_by)
            VALUES (?, ?, ?)
        ''', ('NIMASA Maritime Community', 'Official NIMASA community for maritime professionals across Nigeria', user_id))
        community_id = cursor.lastrowid
    else:
        community_id = community[0]
    
    # Add user to community
    cursor.execute('''
        INSERT OR IGNORE INTO community_members (community_id, user_id, role)
        VALUES (?, ?, ?)
    ''', (community_id, user_id, 'member'))

    # Add userto group
    cursor.execute('''
        INSERT INTO group_members (group_id, user_id, role)
        VALUES (?, ?, ?)
    ''', (0, user_id, 'membe'))
    
    conn.commit()
    conn.close()

# WebSocket event handlers
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

# WebRTC Call handling
@socketio.on('start_call')
def on_start_call(data):
    if not current_user.is_authenticated:
        return
    
    call_type = data.get('type')  # 'audio' or 'video'
    target_type = data.get('target_type')  # 'user' or 'group'
    target_id = data.get('target_id')
    
    call_id = f"call_{uuid.uuid4()}"
    
    # Store call in database
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO calls (call_id, caller_id, target_type, target_id, call_type, status)
        VALUES (?, ?, ?, ?, ?, 'initiated')
    ''', (call_id, current_user.id, target_type, target_id, call_type))
    conn.commit()
    conn.close()
    
    # Store active call
    active_calls[call_id] = {
        'caller_id': current_user.id,
        'target_type': target_type,
        'target_id': target_id,
        'call_type': call_type,
        'status': 'initiated',
        'participants': [current_user.id]
    }
    
    call_data = {
        'call_id': call_id,
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
    
    print(f"Call {call_id} started by {current_user.username} to {target_type}_{target_id}")

@socketio.on('answer_call')
def on_answer_call(data):
    if not current_user.is_authenticated:
        return
    
    call_id = data.get('call_id')
    
    if call_id not in active_calls:
        emit('call_error', {'message': 'Call not found'})
        return
    
    call = active_calls[call_id]
    
    # Add answerer to participants
    if current_user.id not in call['participants']:
        call['participants'].append(current_user.id)
    
    call['status'] = 'connected'
    
    # Update database
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE calls SET status = 'connected' WHERE call_id = ?
    ''', (call_id,))
    conn.commit()
    conn.close()
    
    answer_data = {
        'call_id': call_id,
        'answerer': {
            'id': current_user.id,
            'name': current_user.full_name,
            'avatar': current_user.avatar_url or '/static/default-avatar.png'
        }
    }
    
    # Notify caller
    caller_id = call['caller_id']
    emit('call_answered', answer_data, room=f"user_{caller_id}")
    
    # Join call room
    join_room(f"call_{call_id}")
    emit('join_call_room', {'call_id': call_id}, room=f"user_{caller_id}")

@socketio.on('join_call_room')
def on_join_call_room(data):
    if not current_user.is_authenticated:
        return
    
    call_id = data.get('call_id')
    join_room(f"call_{call_id}")

@socketio.on('webrtc_offer')
def on_webrtc_offer(data):
    if not current_user.is_authenticated:
        return
    
    call_id = data.get('call_id')
    offer = data.get('offer')
    target_id = data.get('target_id')
    
    offer_data = {
        'call_id': call_id,
        'offer': offer,
        'from_user_id': current_user.id
    }
    
    if target_id:
        emit('webrtc_offer', offer_data, room=f"user_{target_id}")
    else:
        emit('webrtc_offer', offer_data, room=f"call_{call_id}", include_self=False)

@socketio.on('webrtc_answer')
def on_webrtc_answer(data):
    if not current_user.is_authenticated:
        return
    
    call_id = data.get('call_id')
    answer = data.get('answer')
    target_id = data.get('target_id')
    
    answer_data = {
        'call_id': call_id,
        'answer': answer,
        'from_user_id': current_user.id
    }
    
    if target_id:
        emit('webrtc_answer', answer_data, room=f"user_{target_id}")
    else:
        emit('webrtc_answer', answer_data, room=f"call_{call_id}", include_self=False)

@socketio.on('webrtc_ice_candidate')
def on_webrtc_ice_candidate(data):
    if not current_user.is_authenticated:
        return
    
    call_id = data.get('call_id')
    candidate = data.get('candidate')
    target_id = data.get('target_id')
    
    ice_data = {
        'call_id': call_id,
        'candidate': candidate,
        'from_user_id': current_user.id
    }
    
    if target_id:
        emit('webrtc_ice_candidate', ice_data, room=f"user_{target_id}")
    else:
        emit('webrtc_ice_candidate', ice_data, room=f"call_{call_id}", include_self=False)

@socketio.on('end_call')
def on_end_call(data):
    if not current_user.is_authenticated:
        return
    
    call_id = data.get('call_id')
    
    if call_id in active_calls:
        call = active_calls[call_id]
        
        # Update database
        conn = sqlite3.connect('docktalk.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE calls SET status = 'ended', ended_at = CURRENT_TIMESTAMP 
            WHERE call_id = ?
        ''', (call_id,))
        conn.commit()
        conn.close()
        
        end_data = {
            'call_id': call_id,
            'ended_by': current_user.id
        }
        
        # Notify all participants
        emit('call_ended', end_data, room=f"call_{call_id}")
        
        # Clean up
        del active_calls[call_id]
    
    # Leave call room
    leave_room(f"call_{call_id}")


# PATCH FOR app.py — Add support for delivery and read receipts

from flask_socketio import SocketIO, emit
# (Make sure `socketio` is already initialized as it is in your current file)

# --- NEW: Create message_status table if not already created
def create_status_table():
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS message_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(message_id, user_id),
            FOREIGN KEY (message_id) REFERENCES messages(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()


# --- NEW: Socket event for delivery
@socketio.on('message_delivered')
def handle_message_delivered(data):
    message_id = data['message_id']
    user_id = data['user_id']
    
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO message_status (message_id, user_id, status)
        VALUES (?, ?, 'delivered')
    ''', (message_id, user_id))
    conn.commit()
    conn.close()

    emit('message_status_update', {
        'message_id': message_id,
        'user_id': user_id,
        'status': 'delivered'
    }, broadcast=True)

# --- NEW: Socket event for seen
@socketio.on('message_seen')
def handle_message_seen(data):
    message_id = data['message_id']
    user_id = data['user_id']

    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO message_status (message_id, user_id, status)
        VALUES (?, ?, 'seen')
    ''', (message_id, user_id))
    conn.commit()
    conn.close()

    emit('message_status_update', {
        'message_id': message_id,
        'user_id': user_id,
        'status': 'seen'
    }, broadcast=True)

# PATCH /api/messages to return status
@app.route('/api/messages')
@login_required
def get_messages():
    chat_type = request.args.get('chat_type')  # 'user' or 'group'
    chat_id = request.args.get('chat_id')
    limit = request.args.get('limit', 50)

    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()

    if chat_type == 'user':
        cursor.execute('''
            SELECT m.id, m.content, m.message_type, m.sender_id, m.created_at, 
                   m.file_url, m.file_name, m.file_size, m.voice_duration, m.is_announcement,
                   u.full_name as sender_name,
                   (SELECT status FROM message_status WHERE message_id = m.id AND user_id = ?) as status
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.chat_type = 'user' AND 
                  ((m.sender_id = ? AND m.chat_id = ?) OR (m.sender_id = ? AND m.chat_id = ?))
            ORDER BY m.created_at ASC
            LIMIT ?
        ''', (current_user.id, current_user.id, chat_id, chat_id, current_user.id, limit))
    else:
        cursor.execute('''
            SELECT m.id, m.content, m.message_type, m.sender_id, m.created_at,
                   m.file_url, m.file_name, m.file_size, m.voice_duration, m.is_announcement,
                   u.full_name as sender_name,
                   (SELECT status FROM message_status WHERE message_id = m.id AND user_id = ?) as status
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.chat_type = 'group' AND m.chat_id = ?
            ORDER BY m.created_at ASC
            LIMIT ?
        ''', (current_user.id, chat_id, limit))

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
            'sender_name': row[10],
            'status': row[11] or 'sent'
        })

    conn.close()
    return jsonify(messages)

@app.route("/api/block_user", methods=["POST"])
@login_required
def block_user():
    data = request.get_json()
    user_id = data["user_id"]
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_blocks (
            blocker_id INTEGER,
            blocked_id INTEGER,
            PRIMARY KEY (blocker_id, blocked_id)
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO user_blocks (blocker_id, blocked_id) VALUES (?, ?)", (current_user.id, user_id))
    conn.commit()
    conn.close()
    return jsonify(success=True)

# === REPORT USER ===
@app.route("/api/report_user", methods=["POST"])
@login_required
def report_user():
    data = request.get_json()
    user_id = data["user_id"]
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_reports (
            reporter_id INTEGER,
            reported_id INTEGER,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute("INSERT INTO user_reports (reporter_id, reported_id, reason) VALUES (?, ?, ?)",
                   (current_user.id, user_id, data.get("reason", "")))
    conn.commit()
    conn.close()
    return jsonify(success=True)

# === LEAVE GROUP ===
@app.route("/api/leave_group", methods=["POST"])
@login_required
def leave_group():
    data = request.get_json()
    group_id = data["group_id"]
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM group_members WHERE user_id = ? AND group_id = ?", (current_user.id, group_id))
    conn.commit()
    conn.close()
    return jsonify(success=True)

# === JOIN REQUEST ===
@app.route("/api/request_join_group", methods=["POST"])
@login_required
def request_join_group():
    data = request.get_json()
    group_id = data["group_id"]
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS group_join_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER,
            user_id INTEGER,
            status TEXT DEFAULT 'pending'
        )
    ''')
    cursor.execute("INSERT INTO group_join_requests (group_id, user_id) VALUES (?, ?)", (group_id, current_user.id))
    conn.commit()
    conn.close()
    return jsonify(success=True)

# === ACCEPT REQUEST ===
@app.route("/api/accept_join_request", methods=["POST"])
@login_required
def accept_join_request():
    data = request.get_json()
    request_id = data["request_id"]
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute("SELECT group_id, user_id FROM group_join_requests WHERE id = ?", (request_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify(error="Request not found"), 404
    group_id, user_id = row
    cursor.execute("INSERT INTO group_members (group_id, user_id) VALUES (?, ?)", (group_id, user_id))
    cursor.execute("UPDATE group_join_requests SET status = 'accepted' WHERE id = ?", (request_id,))
    conn.commit()
    conn.close()
    return jsonify(success=True)

# === PROMOTE TO ADMIN ===
@app.route("/api/promote_to_admin", methods=["POST"])
@login_required
def promote_to_admin():
    data = request.get_json()
    group_id = data["group_id"]
    user_id = data["user_id"]
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE group_members SET is_admin = 1 WHERE group_id = ? AND user_id = ?", (group_id, user_id))
    conn.commit()
    conn.close()
    return jsonify(success=True)

# === ADD MEMBER DIRECTLY ===
@app.route("/api/add_member", methods=["POST"])
@login_required
def add_member():
    data = request.get_json()
    group_id = data["group_id"]
    user_id = data["user_id"]
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)", (group_id, user_id))
    conn.commit()
    conn.close()
    return jsonify(success=True)





@app.route("/api/lookup_user")
@login_required
def lookup_user():
    username = request.args.get("username")
    if not username:
        return jsonify(error="Username required"), 400

    conn = sqlite3.connect("docktalk.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, full_name FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return jsonify({"id": row[0], "username": row[1], "full_name": row[2]})
    return jsonify({"error": "User not found"}), 404


@app.route("/api/group_members")
@login_required
def group_members():
    group_id = request.args.get("group_id")
    conn = sqlite3.connect("docktalk.db")
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.id, u.full_name, u.username, gm.is_admin
        FROM group_members gm
        JOIN users u ON gm.user_id = u.id
        WHERE gm.group_id = ?
    ''', (group_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([
        {"id": r[0], "full_name": r[1], "username": r[2], "is_admin": bool(r[3])} for r in rows
    ])


@app.route("/api/feed")
@login_required
def get_feed():
    page = int(request.args.get("page", 1))
    per_page = 10
    offset = (page - 1) * per_page

    conn = sqlite3.connect("docktalk.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        SELECT f.id, f.content, f.created_at, u.full_name
        FROM feed f
        JOIN users u ON u.id = f.user_id
        ORDER BY f.created_at DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([
        {"id": r[0], "content": r[1], "created_at": r[2], "author": r[3]} for r in rows
    ])

@app.route("/api/feed/post", methods=["POST"])
@login_required
def post_to_feed():
    if not current_user.is_super_admin:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    content = data.get("content")
    if not content:
        return jsonify({"error": "No content"}), 400

    conn = sqlite3.connect("docktalk.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO feed (user_id, content) VALUES (?, ?)", (current_user.id, content))
    conn.commit()
    conn.close()
    return jsonify({"success": True})




@app.route("/feed")
@login_required
def show_feed():
    
    return render_template("feed.html")


if __name__ == '__main__':
    init_db()
    socketio.run(app, host="0.0.0.0", port=600, debug=False, use_reloader=False,allow_unsafe_werkzeug=True)
