import sqlite3
from werkzeug.security import generate_password_hash
from datetime import datetime

def create_test_user():
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    # Check if user already exists
    cursor.execute('SELECT id FROM users WHERE username = ?', ('testuser',))
    if cursor.fetchone():
        print("Test user already exists")
        conn.close()
        return
    
    # Create test user
    password_hash = generate_password_hash('password')
    cursor.execute('''
        INSERT INTO users (username, email, password_hash, full_name, department, location, phone)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', ('testuser', 'test@example.com', password_hash, 'Test User', 'IT Department', 'Lagos', '+2341234567890'))
    
    user_id = cursor.lastrowid
    
    # Create NIMASA community if it doesn't exist
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
    
    # Create a test group
    cursor.execute('''
        INSERT INTO groups (name, description, community_id, created_by)
        VALUES (?, ?, ?, ?)
    ''', ('General Discussion', 'General discussion for all NIMASA members', community_id, user_id))
    
    group_id = cursor.lastrowid
    
    # Add user as admin of the group
    cursor.execute('''
        INSERT INTO group_members (group_id, user_id, role)
        VALUES (?, ?, ?)
    ''', (group_id, user_id, 'super_admin'))
    
    conn.commit()
    conn.close()
    
    print("Test user created successfully")

if __name__ == "__main__":
    create_test_user()
