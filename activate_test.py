import sqlite3
db = r"C:\Users\Public\Downloads\my project about blood\Blood\blood_bank.db"
conn = sqlite3.connect(db)
c = conn.cursor()
c.execute("UPDATE users SET is_active = 1 WHERE username = ?", ("the_username",))
conn.commit()
conn.close()
import sqlite3
import os

DATABASE_PATH = os.path.join(os.path.dirname('app .py'), 'blood_bank.db')
conn = sqlite3.connect(DATABASE_PATH)
c = conn.cursor()

# Activate the test user (simulating admin action)
user_id = 5
c.execute('UPDATE users SET is_active = 1 WHERE id = ?', (user_id,))
conn.commit()

# Check the user status after activation
c.execute('SELECT id, username, is_active, is_admin FROM users WHERE id = ?', (user_id,))
user = c.fetchone()
print(f'After activation: ID={user[0]}, Username={user[1]}, Active={user[2]}, Admin={user[3]}')

conn.close()