# app.py
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g
)
from functools import wraps

app = Flask(__name__)
app.secret_key = 'super-secret-key'          # change in production!

# ----------------------------------------------------------------------
# In-memory "DB" – replace with real DB later
USERS = {}                                   # email → {name, role}
PRESCRIPTIONS = [                           # sample data
    {
        'id': 1,
        'patient_name': 'John Doe',
        'patient_email': 'john@example.com',
        'doctor_name': 'Dr. Alice',
        'doctor_email': 'alice@clinic.com',
        'medication': 'Amoxicillin 500mg',
        'dosage': '1 tablet every 8 hours',
        'duration': '7 days',
        'status': 'Pending',            # Pending | Filled | Completed
        'date': '2025-10-27'
    },
    {
        'id': 2,
        'patient_name': 'Priya Singh',
        'patient_email': 'priya@example.com',
        'doctor_name': 'Dr. Alice',
        'doctor_email': 'alice@clinic.com',
        'medication': 'Ibuprofen 400mg',
        'dosage': '1 tablet as needed',
        'duration': '5 days',
        'status': 'Filled',
        'date': '2025-10-26'
    },
]

# ----------------------------------------------------------------------
@app.before_request
def load_user():
    """Make the logged-in user available as g.user in every request."""
    g.user = USERS.get(session.get('user')) if session.get('user') else None


# ----------------------------------------------------------------------
# PUBLIC PAGES
@app.route('/')
def landing():
    return render_template('landing.html')


@app.route('/getting-started')
def getting_started():
    return render_template('getting-started.html')


# ----------------------------------------------------------------------
# PROFILE CREATION
@app.route('/create-profile', methods=['GET', 'POST'])
def create_profile():
    if request.method == 'POST':
        name  = request.form['name']
        email = request.form['email']
        role  = request.form['role']

        USERS[email] = {'name': name, 'role': role}
        flash('Profile created – you can now log in.', 'success')
        return redirect(url_for('login'))

    return render_template('create-profile.html')


# ----------------------------------------------------------------------
# AUTHENTICATION
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        user = USERS.get(email)
        if user:
            session['user'] = email
            role = user['role']

            if role == 'Doctor':
                return redirect(url_for('doctor_home'))
            if role == 'Patient':
                return redirect(url_for('patient_prescriptions'))
            if role == 'Clinic / Hospital':
                return redirect(url_for('pharmacy_prescriptions'))

        flash('Invalid credentials.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('landing'))


# ----------------------------------------------------------------------
# ROLE-REQUIRED DECORATOR (works for any role)
def role_required(required_role):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not g.user or g.user['role'] != required_role:
                flash(f'You need to log in as a {required_role}.', 'warning')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ----------------------------------------------------------------------
# DOCTOR PAGES
@app.route('/doctor-home')
@role_required('Doctor')
def doctor_home():
    return render_template('doctor_home.html', user=g.user)


@app.route('/doctor-prescriptions')
@role_required('Doctor')
def doctor_prescriptions():
    my_rx = [p for p in PRESCRIPTIONS if p['doctor_email'] == session['user']]
    return render_template('doctor_prescriptions.html', prescriptions=my_rx)


# ----------------------------------------------------------------------
# PATIENT PAGES
@app.route('/patient-prescriptions')
@role_required('Patient')
def patient_prescriptions():
    my_rx = [p for p in PRESCRIPTIONS if p['patient_email'] == session['user']]
    return render_template('patient_prescriptions.html', prescriptions=my_rx)


# ----------------------------------------------------------------------
# PHARMACY (Clinic / Hospital) PAGES
@app.route('/pharmacy-prescriptions')
@role_required('Clinic / Hospital')
def pharmacy_prescriptions():
    # Pharmacy can see *all* prescriptions
    return render_template('pharmacy_prescriptions.html', prescriptions=PRESCRIPTIONS)


# ----------------------------------------------------------------------
# OTHER PAGES (unchanged)
@app.route('/workspace')
def workspace():
    return render_template('workspace.html')


@app.route('/queue')
def queue_dashboard():
    return render_template('queue-dashboard.html')


# ----------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True)