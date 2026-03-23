import sqlite3
import os
from werkzeug.security import generate_password_hash
import pyotp

DATABASE_PATH = os.path.join(os.path.dirname('app .py'), 'blood_bank.db')
conn = sqlite3.connect(DATABASE_PATH)
c = conn.cursor()

# Create a test user (inactive)
username = 'testuser'
password = 'testpass123'
hashed_password = generate_password_hash(password)
mfa_secret = pyotp.random_base32()

c.execute('INSERT INTO users (username, password, mfa_secret, is_active, is_admin, created_at) VALUES (?, ?, ?, 0, 0, datetime("now"))', (username, hashed_password, mfa_secret))
conn.commit()

# Check the user
c.execute('SELECT id, username, is_active, is_admin FROM users WHERE username = ?', (username,))
user = c.fetchone()
print(f'Created test user: ID={user[0]}, Username={user[1]}, Active={user[2]}, Admin={user[3]}')

conn.close()