import sqlite3
import random
import pyotp
import qrcode
import io
import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Admin access required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function
DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'blood_bank.db')

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change this to a random secret key
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            phone TEXT,
            mfa_secret TEXT,
            confirmation_code TEXT,
            is_active INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Ensure new columns exist for users table migrations
    c.execute("PRAGMA table_info(users)")
    existing_cols = [row[1] for row in c.fetchall()]
    if 'phone' not in existing_cols:
        c.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    if 'confirmation_code' not in existing_cols:
        c.execute("ALTER TABLE users ADD COLUMN confirmation_code TEXT")

    c.execute('''
        CREATE TABLE IF NOT EXISTS donors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age INTEGER,
            gender TEXT,
            blood_type TEXT NOT NULL,
            contact TEXT NOT NULL,
            email TEXT,
            address TEXT,
            emergency_contact TEXT,
            medical_history TEXT,
            last_donation_date TEXT,
            donation_count INTEGER DEFAULT 0,
            registration_date TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS blood_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blood_type TEXT NOT NULL,
            available_units INTEGER NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            blood_type TEXT NOT NULL,
            contact TEXT NOT NULL,
            address TEXT,
            medical_condition TEXT,
            required_blood_units INTEGER NOT NULL,
            urgency_level TEXT NOT NULL,
            registration_date TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS blood_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blood_type TEXT NOT NULL,
            donor_id INTEGER,
            donation_date TEXT DEFAULT CURRENT_TIMESTAMP,
            expiry_date TEXT NOT NULL,
            status TEXT DEFAULT 'available',
            units INTEGER DEFAULT 1,
            storage_location TEXT,
            FOREIGN KEY (donor_id) REFERENCES donors (id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS blood_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            blood_inventory_id INTEGER NOT NULL,
            transaction_type TEXT NOT NULL,
            units_used INTEGER NOT NULL,
            transaction_date TEXT DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients (id),
            FOREIGN KEY (blood_inventory_id) REFERENCES blood_inventory (id)
        )
    ''')
    conn.commit()
    conn.close()

class User(UserMixin):
    def __init__(self, id, username, mfa_secret, is_active=True, is_admin=False):
        self.id = str(id)
        self.username = username
        self.mfa_secret = mfa_secret
        self._is_active = is_active
        self.is_admin = is_admin
    
    @property
    def is_active(self):
        return self._is_active

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('SELECT id, username, mfa_secret, is_active, is_admin FROM users WHERE id = ? AND is_active = 1', (int(user_id),))
    user = c.fetchone()
    conn.close()
    if user:
        return User(user[0], user[1], user[2], user[3], user[4])
    return None

@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        phone = request.form.get('phone', '')
        password = request.form.get('password', '')

        if not password:
            flash('Password is required to register.', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        confirmation_code = str(random.randint(100000, 999999))
        mfa_secret = pyotp.random_base32()
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        try:
            c.execute(
                'INSERT INTO users (username, password, phone, mfa_secret, confirmation_code, is_active) VALUES (?, ?, ?, ?, ?, 0)',
                (username, hashed_password, phone, mfa_secret, confirmation_code)
            )
            conn.commit()
            flash(f'Registration successful! Your confirmation code is {confirmation_code}. Please wait for admin activation.', 'info')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists. Please choose a different one.', 'danger')
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        otp = request.form['otp']

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('SELECT id, username, password, is_active, is_admin, confirmation_code FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            if user[3] == 0:  # is_active check
                flash('Your account is pending admin approval. Please wait for activation.', 'warning')
                return redirect(url_for('login'))

            if otp != user[5]:
                flash('Invalid confirmation code.', 'danger')
                return redirect(url_for('login'))

            user_obj = User(user[0], user[1], None, user[3], user[4])
            login_user(user_obj)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for ('index'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    # Fetch database data
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    
    # Get all donors
    c.execute('SELECT * FROM donors ORDER BY id DESC')
    donors = c.fetchall()
    
    # Get all blood groups
    c.execute('SELECT * FROM blood_groups ORDER BY blood_type')
    blood_groups = c.fetchall()
    
    # Get all patients
    c.execute('SELECT * FROM patients ORDER BY registration_date DESC')
    patients = c.fetchall()
    
    # Get detailed blood inventory
    c.execute('SELECT blood_type, COUNT(*) as total_units FROM blood_inventory WHERE status = "available" GROUP BY blood_type')
    blood_inventory_details = c.fetchall()
    
    conn.close()
    
    return render_template('profile.html', donors=donors, blood_groups=blood_groups, patients=patients, blood_inventory_details=blood_inventory_details)

@app.route('/qr_code/<username>')
def qr_code(username):
    import base64
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('SELECT mfa_secret FROM users WHERE username = ?', (username,))
    mfa_secret = c.fetchone()[0]
    conn.close()
    
    totp = pyotp.TOTP(mfa_secret)
    uri = totp.provisioning_uri(name=username, issuer_name='BloodBankSystem')
    img = qrcode.make(uri)
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    img_base64 = base64.b64encode(img_io.getvalue()).decode()
    current_otp = totp.now()
    
    return render_template('qr_code.html', username=username, qr_code=img_base64, otp=current_otp)

@app.route('/add_patient', methods=['GET', 'POST'])
@login_required
def add_patient():
    if request.method == 'POST':
        name = request.form['name']
        age = request.form['age']
        blood_type = request.form['blood_type']
        contact = request.form['contact']
        address = request.form.get('address', '')
        medical_condition = request.form.get('medical_condition', '')
        required_blood_units = request.form['required_blood_units']
        urgency_level = request.form['urgency_level']
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT INTO patients (name, age, blood_type, contact, address, medical_condition, required_blood_units, urgency_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, age, blood_type, contact, address, medical_condition, required_blood_units, urgency_level))
        conn.commit()
        conn.close()
        
        flash('Patient registered successfully!', 'success')
        return redirect(url_for('patients'))
    
    return render_template('add_patient.html')

@app.route('/patients')
@login_required
def patients():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM patients ORDER BY registration_date DESC')
    patients_list = c.fetchall()
    conn.close()
    
    return render_template('patients.html', patients=patients_list)

@app.route('/add_blood_unit', methods=['GET', 'POST'])
@login_required
def add_blood_unit():
    if request.method == 'POST':
        blood_type = request.form['blood_type']
        donor_id = request.form.get('donor_id')
        units = int(request.form['units'])
        storage_location = request.form.get('storage_location', 'Main Storage')
        
        # Calculate expiry date (42 days from donation)
        from datetime import datetime, timedelta
        donation_date = datetime.now()
        expiry_date = donation_date + timedelta(days=42)
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        # Add blood units to inventory
        for _ in range(units):
            c.execute('''
                INSERT INTO blood_inventory (blood_type, donor_id, donation_date, expiry_date, storage_location)
                VALUES (?, ?, ?, ?, ?)
            ''', (blood_type, donor_id, donation_date.strftime('%Y-%m-%d %H:%M:%S'), 
                  expiry_date.strftime('%Y-%m-%d'), storage_location))
        
        # Update blood_groups table
        c.execute('SELECT available_units FROM blood_groups WHERE blood_type = ?', (blood_type,))
        result = c.fetchone()
        if result:
            new_units = result[0] + units
            c.execute('UPDATE blood_groups SET available_units = ? WHERE blood_type = ?', (new_units, blood_type))
        else:
            c.execute('INSERT INTO blood_groups (blood_type, available_units) VALUES (?, ?)', (blood_type, units))
        
        conn.commit()
        conn.close()
        
        flash(f'Successfully added {units} unit(s) of {blood_type} blood to inventory!', 'success')
        return redirect(url_for('blood_inventory'))
    
    # Get donors for dropdown
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('SELECT id, name, blood_type FROM donors ORDER BY name')
    donors = c.fetchall()
    conn.close()
    
    return render_template('add_blood_unit.html', donors=donors)

@app.route('/blood_inventory')
@login_required
def blood_inventory():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    
    # Get detailed inventory
    c.execute('''
        SELECT bi.*, d.name as donor_name 
        FROM blood_inventory bi 
        LEFT JOIN donors d ON bi.donor_id = d.id 
        ORDER BY bi.expiry_date ASC
    ''')
    inventory_raw = c.fetchall()
    
    # Calculate days left for each item
    from datetime import datetime
    inventory = []
    for item in inventory_raw:
        expiry_date = datetime.strptime(item[4], '%Y-%m-%d').date()
        today = datetime.now().date()
        days_left = (expiry_date - today).days
        inventory.append(item + (days_left,))
    
    # Get summary by blood type
    c.execute('SELECT blood_type, COUNT(*) as total_units FROM blood_inventory WHERE status = "available" GROUP BY blood_type')
    summary = c.fetchall()
    
    # Get expiring blood (within 7 days)
    from datetime import datetime, timedelta
    expiry_threshold = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    c.execute('SELECT * FROM blood_inventory WHERE expiry_date <= ? AND status = "available"', (expiry_threshold,))
    expiring_blood = c.fetchall()
    
    conn.close()
    
    return render_template('blood_inventory.html', inventory=inventory, summary=summary, expiring_blood=expiring_blood)

@app.route('/issue_blood/<int:patient_id>', methods=['GET', 'POST'])
@login_required
def issue_blood(patient_id):
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    
    # Get patient details
    c.execute('SELECT * FROM patients WHERE id = ?', (patient_id,))
    patient = c.fetchone()
    
    if not patient:
        flash('Patient not found!', 'danger')
        return redirect(url_for('patients'))
    
    if request.method == 'POST':
        blood_inventory_id = request.form['blood_inventory_id']
        units_used = int(request.form['units_used'])
        notes = request.form.get('notes', '')
        
        # Check if blood is available
        c.execute('SELECT * FROM blood_inventory WHERE id = ? AND status = "available"', (blood_inventory_id,))
        blood_unit = c.fetchone()
        
        if not blood_unit:
            flash('Blood unit not available!', 'danger')
            conn.close()
            return redirect(url_for('issue_blood', patient_id=patient_id))
        
        # Record transaction
        c.execute('''
            INSERT INTO blood_transactions (patient_id, blood_inventory_id, transaction_type, units_used, notes)
            VALUES (?, ?, 'issued', ?, ?)
        ''', (patient_id, blood_inventory_id, units_used, notes))
        
        # Update blood status
        c.execute('UPDATE blood_inventory SET status = "issued" WHERE id = ?', (blood_inventory_id,))
        
        # Update blood_groups count
        c.execute('UPDATE blood_groups SET available_units = available_units - 1 WHERE blood_type = ?', (blood_unit[1],))
        
        conn.commit()
        conn.close()
        
        flash(f'Successfully issued {units_used} unit(s) of {blood_unit[1]} blood to {patient[1]}!', 'success')
        return redirect(url_for('patients'))
    
    # Get compatible blood types
    patient_blood_type = patient[3]
    compatible_types = get_compatible_blood_types(patient_blood_type)
    
    # Get available blood units
    placeholders = ','.join('?' * len(compatible_types))
    c.execute(f'SELECT * FROM blood_inventory WHERE blood_type IN ({placeholders}) AND status = "available" ORDER BY expiry_date ASC', compatible_types)
    available_blood = c.fetchall()
    
    conn.close()
    
    return render_template('issue_blood.html', patient=patient, available_blood=available_blood)

def get_compatible_blood_types(patient_blood_type):
    """Return compatible blood types for transfusion"""
    compatibility = {
        'O-': ['O-'],
        'O+': ['O-', 'O+'],
        'A-': ['O-', 'A-'],
        'A+': ['O-', 'O+', 'A-', 'A+'],
        'B-': ['O-', 'B-'],
        'B+': ['O-', 'O+', 'B-', 'B+'],
        'AB-': ['O-', 'A-', 'B-', 'AB-'],
        'AB+': ['O-', 'O+', 'A-', 'A+', 'B-', 'B+', 'AB-', 'AB+']
    }
    return compatibility.get(patient_blood_type, [patient_blood_type])

@app.route('/blood_transactions')
@login_required
def blood_transactions():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    
    c.execute('''
        SELECT bt.*, p.name as patient_name, bi.blood_type, bi.donation_date
        FROM blood_transactions bt
        JOIN patients p ON bt.patient_id = p.id
        JOIN blood_inventory bi ON bt.blood_inventory_id = bi.id
        ORDER BY bt.transaction_date DESC
    ''')
    transactions = c.fetchall()
    
    conn.close()
    
    return render_template('blood_transactions.html', transactions=transactions)

@app.route('/donors')
@login_required
def donors():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM donors ORDER BY registration_date DESC')
    donors_list = c.fetchall()
    conn.close()
    
    return render_template('donors.html', donors=donors_list)

@app.route('/add_donor', methods=['GET', 'POST'])
@login_required
def add_donor():
    if request.method == 'POST':
        name = request.form['name']
        age = request.form.get('age')
        gender = request.form.get('gender')
        blood_type = request.form['blood_type']
        contact = request.form['contact']
        email = request.form.get('email')
        address = request.form.get('address')
        emergency_contact = request.form.get('emergency_contact')
        medical_history = request.form.get('medical_history')
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT INTO donors (name, age, gender, blood_type, contact, email, address, emergency_contact, medical_history)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, age, gender, blood_type, contact, email, address, emergency_contact, medical_history))
        conn.commit()
        conn.close()
        
        flash('Donor registered successfully!', 'success')
        return redirect(url_for('donors'))
    
    return render_template('add_donor.html')

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('SELECT id, username, phone, confirmation_code, is_active, is_admin, created_at FROM users ORDER BY created_at DESC')
    users = c.fetchall()
    conn.close()
    
    return render_template('admin_users.html', users=users)

@app.route('/admin/activate_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def activate_user(user_id):
    confirmation_code = str(random.randint(100000, 999999))
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET is_active = 1, confirmation_code = ? WHERE id = ?', (confirmation_code, user_id))
    conn.commit()
    conn.close()
    
    flash(f'User activated successfully! Confirmation code: {confirmation_code}', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/deactivate_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def deactivate_user(user_id):
    # Don't allow deactivating yourself
    if user_id == current_user.id:
        flash('Cannot deactivate your own account.', 'danger')
        return redirect(url_for('admin_users'))
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET is_active = 0 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    flash('User deactivated successfully!', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/toggle_admin/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_admin(user_id):
    # Don't allow removing admin from yourself if you're the only admin
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
    admin_count = c.fetchone()[0]
    
    if admin_count == 1 and user_id == current_user.id:
        conn.close()
        flash('Cannot remove admin privileges from the only admin account.', 'danger')
        return redirect(url_for('admin_users'))
    
    c.execute('UPDATE users SET is_admin = CASE WHEN is_admin = 1 THEN 0 ELSE 1 END WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    flash('Admin privileges updated!', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    # Don't allow deleting yourself
    if user_id == current_user.id:
        flash('Cannot delete your own account.', 'danger')
        return redirect(url_for('admin_users'))
    
    # Don't allow deleting the only admin
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('SELECT is_admin FROM users WHERE id = ?', (user_id,))
    user_to_delete = c.fetchone()
    if user_to_delete and user_to_delete[0] == 1:
        c.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
        admin_count = c.fetchone()[0]
        if admin_count == 1:
            conn.close()
            flash('Cannot delete the only admin account.', 'danger')
            return redirect(url_for('admin_users'))
    
    # Delete the user
    c.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    flash('User deleted successfully!', 'success')
    return redirect(url_for('admin_users'))

@app.route('/account_settings', methods=['GET', 'POST'])
@login_required
def account_settings():
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        if new_password:
            hashed_password = generate_password_hash(new_password)
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, current_user.id))
            conn.commit()
            conn.close()
            flash('Password updated successfully!', 'success')
        
        if 'regenerate_mfa' in request.form:
            new_mfa_secret = pyotp.random_base32()
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute('UPDATE users SET mfa_secret = ? WHERE id = ?', (new_mfa_secret, current_user.id))
            conn.commit()
            conn.close()
            flash('MFA secret regenerated! Please set up your authenticator app again.', 'success')
            return redirect(url_for('qr_code', username=current_user.username))
        
        return redirect(url_for('account_settings'))
    
    return render_template('account_settings.html')

# Initialize the database
init_db()

if __name__ == '__main__':
    app.run(debug=True)
