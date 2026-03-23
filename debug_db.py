import sqlite3
import os
print('Current working directory:', os.getcwd())
print('Database file exists:', os.path.exists('blood_bank.db'))

# Check all .db files in current directory
import glob
db_files = glob.glob('*.db')
print('Database files found:', db_files)

# Try the exact same connection as Flask
conn = sqlite3.connect('blood_bank.db')
c = conn.cursor()
print('Connection successful')

# Check if donors table exists
c.execute('SELECT name FROM sqlite_master WHERE type="table" AND name="donors"')
table_exists = c.fetchone()
print('Donors table exists:', table_exists is not None)

if table_exists:
    # Check columns
    c.execute('PRAGMA table_info(donors)')
    columns = c.fetchall()
    print('Columns:', [col[1] for col in columns])

    # Try the failing query
    try:
        c.execute('SELECT * FROM donors ORDER BY registration_date DESC')
        results = c.fetchall()
        print('Query successful, rows:', len(results))
    except Exception as e:
        print('Query failed:', e)

conn.close()