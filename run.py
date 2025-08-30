from app import app, socketio, init_db, create_status_table
from werkzeug.security import generate_password_hash
import sqlite3
import os, sys, logging
import werkzeug.serving as _serving

# Configure root logger
handlers = [logging.StreamHandler()]

# Only use file logging if the system allows writing
if os.access(".", os.W_OK):  # check if current dir is writable
    from logging.handlers import RotatingFileHandler
    log_file = os.path.join(os.getcwd(), "chatapp.log")
    handlers.append(RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=5))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=handlers
)
logging.info("=== Chat App starting ===")

def create_sample_data():
    """Create sample data if it doesn't exist"""
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        admin_password = generate_password_hash('admin123')
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, full_name, department, location, phone, bio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', ('admin', 'admin@nimasa.gov.ng', admin_password, 'NIMASA Administrator', 
              'Administration', 'NIMASA HQ Abuja', '+234 801 000 0000', 
              'NIMASA DockTalk System Administrator'))
        
        admin_id = cursor.lastrowid
        
        cursor.execute('''
            INSERT INTO communities (name, description, created_by)
            VALUES (?, ?, ?)
        ''', ('NIMASA Maritime Community', 
              'Official NIMASA community for maritime professionals across Nigeria', 
              admin_id))
        
        community_id = cursor.lastrowid
        
        cursor.execute('''
            INSERT INTO community_members (community_id, user_id, role)
            VALUES (?, ?, ?)
        ''', (community_id, admin_id, 'admin'))
        
        groups_data = [
            ('Lagos Port Operations', 'Coordination group for Lagos Port Complex operations'),
            ('Emergency Response Team', 'Emergency response coordination for maritime incidents'),
            ('Port Harcourt Operations', 'Port Harcourt maritime operations coordination')
        ]
        
        for group_name, group_desc in groups_data:
            cursor.execute('''
                INSERT INTO groups (name, description, community_id, created_by)
                VALUES (?, ?, ?, ?)
            ''', (group_name, group_desc, community_id, admin_id))
            
            group_id = cursor.lastrowid
            cursor.execute('''
                INSERT INTO group_members (group_id, user_id, role)
                VALUES (?, ?, ?)
            ''', (group_id, admin_id, 'admin'))
        
        conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    create_sample_data()
    create_status_table()
    
    socketio.run(app, host="0.0.0.0", port=600, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
