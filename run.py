from app import app, socketio, init_db, create_status_table
from werkzeug.security import generate_password_hash
import sqlite3
import time  
import os,sys, logging
from logging.handlers import RotatingFileHandler
import werkzeug.serving as _serving
# Log file path
PREFERRED = r"G:\chatlog"
FALLBACK  = os.path.join(os.getcwd(), "chatlog")
WAIT_FOR_G_SECONDS = 0  # set to e.g. 60 to wait up to 60s for G:\ to appear

# Make sure the log directory exists
def pick_log_dir():
    if os.path.exists(r"G:\\"):
        return PREFERRED
    if WAIT_FOR_G_SECONDS > 0:
        deadline = time.time() + WAIT_FOR_G_SECONDS
        while time.time() < deadline:
            if os.path.exists(r"G:\\"):
                return PREFERRED
            time.sleep(2)
    return FALLBACK
log_dir = pick_log_dir()
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "chatapp.log")

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=5),
        logging.StreamHandler()
    ]
)
logging.info("=== Chat App starting, logging to: %s ===", log_file)

def create_sample_data():
    """Create sample data if it doesn't exist"""
    conn = sqlite3.connect('docktalk.db')
    cursor = conn.cursor()
    
    # Check if admin user exists
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
        
        # Create NIMASA community
        cursor.execute('''
            INSERT INTO communities (name, description, created_by)
            VALUES (?, ?, ?)
        ''', ('NIMASA Maritime Community', 
              'Official NIMASA community for maritime professionals across Nigeria', 
              admin_id))
        
        community_id = cursor.lastrowid
        
        # Add admin to community
        cursor.execute('''
            INSERT INTO community_members (community_id, user_id, role)
            VALUES (?, ?, ?)
        ''', (community_id, admin_id, 'admin'))
        
        # Create sample groups
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
            
            # Add admin to group
            cursor.execute('''
                INSERT INTO group_members (group_id, user_id, role)
                VALUES (?, ?, ?)
            ''', (group_id, admin_id, 'admin'))
        
        conn.commit()
        #print("✅ Sample data created successfully!")
        #print("🔑 Admin login: username='admin', password='admin123'")
    else:
        #print("✅ Database already initialized")
    
     conn.close()

if __name__ == '__main__':
    # # Silence werkzeug request logging
    # logging.getLogger("werkzeug").setLevel(logging.ERROR)
    # def _quiet_banner(*args, **kwargs):
    #  pass  # do nothing instead of printing the banner
    # _serving._log_startup = _quiet_banner
    #print("🚢 Initializing NIMASA DockTalk...")
    # Initialize database
    init_db()
    
    # Create sample data
    create_sample_data()
    create_status_table()
    
    #print("🌊 Starting DockTalk server...")
    #print("📱 Access the application at: http://localhost:5000")
    
    # Run the application
    socketio.run(app, host="0.0.0.0", port=600, debug=False, use_reloader=False,allow_unsafe_werkzeug=True)
