from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g
)
from functools import wraps
import os
import json
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from sqlalchemy import inspect, text
from models import db, User, FacilityType, DoctorProfile
from authlib.integrations.flask_client import OAuth
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf import CSRFProtect
from flask_marshmallow import Marshmallow
from marshmallow import fields, validate
from config import get_config

load_dotenv()

app = Flask(__name__)
app.config.from_object(get_config())

# Logging Configuration
if not app.debug:
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/careconnect.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('CareConnect startup')

# Extension Initialization
db.init_app(app)
migrate = Migrate(app, db)
csrf = CSRFProtect(app)
ma = Marshmallow(app)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=app.config.get('GOOGLE_CLIENT_ID'),
    client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url=app.config.get('GOOGLE_DISCOVERY_URL'),
    client_kwargs={'scope': 'openid email profile'},
)

def _migrate_user_columns():
    """Add new columns to SQLite `user` when the DB already exists."""
    insp = inspect(db.engine)
    if 'user' not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns('user')}
    with db.engine.begin() as conn:
        if 'organization' not in cols:
            conn.execute(text('ALTER TABLE user ADD COLUMN organization VARCHAR(120)'))
        if 'onboarding_complete' not in cols:
            conn.execute(text(
                'ALTER TABLE user ADD COLUMN onboarding_complete BOOLEAN NOT NULL DEFAULT 1'
            ))

FACILITY_TYPES = [
    'Anesthesiology Hospital',
    'Ayurvedic Hospital',
    'Cancer Hospital',
    'Cardiology Hospital',
    'Children Hospital',
    'Cosmetic & Plastic Surgery Hospital',
    'Dental Hospital',
    'Dermatology Hospital',
    'ENT Hospital',
    'Gastroenterologist Hospital',
    'General Hospital',
    'Gynecology Hospital',
    'Homeopathy Hospital',
    'Neurology Hospital',
    'Oncology Hospital',
    'Orthopaedic Hospital',
    'Private Hospital',
    'Psychiatric Hospital',
    'Radiology Hospital',
    'Diabetes Hospital',
    'Emergency Hospital',
    'Maternity Hospital',
    'Urology Hospital',
    'Nephrology Hospital',
    'Opthalmology Hospital',
    'Eye Hospital',
    'Rheumatology Hospital',
    'Hematology Hospital',
    'Immunology Hospital',
    'Mental Hospital',
    'Public Hospital',
    'Government Hospital',
    'Veterinary Hospital',
    'Multispeciality Hospital',
    'Cardiac Hospital',
    'Charitable Hospital',
    'Esis Hospital',
    'Pet Clinics',
    'Public Veterinary Hospital',
    'Orthodontic Hospitals',
    'Dental Implants Center',
    'Medical Store',
    '24 Hours Chemists',
]


def _seed_facility_types():
    """Insert facility types once (idempotent)."""
    existing = {r[0] for r in db.session.query(FacilityType.name).all()}
    to_add = [FacilityType(name=n) for n in FACILITY_TYPES if n not in existing]
    if to_add:
        db.session.add_all(to_add)
        db.session.commit()


with app.app_context():
    db.create_all()
    _migrate_user_columns()
    _seed_facility_types()

# ----------------------------------------------------------------------
# In-memory PRESCRIPTIONS mock – replace later
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

# Mock lab requisitions for pathology dashboard (replace with DB later)
LAB_ORDERS = [
    {
        'id': 'LAB-1001',
        'patient_name': 'John Doe',
        'test': 'CBC + metabolic panel',
        'status': 'Sample received',
        'priority': 'Routine',
        'ordered_at': '2026-03-28',
    },
    {
        'id': 'LAB-1002',
        'patient_name': 'Priya Singh',
        'test': 'HbA1c',
        'status': 'Processing',
        'priority': 'Urgent',
        'ordered_at': '2026-03-29',
    },
    {
        'id': 'LAB-1003',
        'patient_name': 'Alex Kim',
        'test': 'Lipid profile',
        'status': 'Report ready',
        'priority': 'Routine',
        'ordered_at': '2026-03-30',
    },
]

# Canonical roles used in User.role
ROLE_PATIENT = 'Patient'
ROLE_DOCTOR = 'Doctor'
ROLE_PATHOLOGY = 'Pathology Lab'
ROLE_PHARMACY = 'Clinic / Hospital'
ROLE_ADMIN = 'Administrator'
# New Google OAuth user until they pick an account type
ROLE_PENDING = 'Pending'

# Map signup form values → canonical role strings
ROLE_ALIASES = {
    'patient': ROLE_PATIENT,
    'doctor': ROLE_DOCTOR,
    'hospital': ROLE_PHARMACY,
    'clinic': ROLE_PHARMACY,
    'clinic / hospital': ROLE_PHARMACY,
    'pathology': ROLE_PATHOLOGY,
    'pathology_lab': ROLE_PATHOLOGY,
    'pathology lab': ROLE_PATHOLOGY,
    'administrator': ROLE_ADMIN,
    'admin': ROLE_ADMIN,
    'administrators': ROLE_ADMIN,
}


def normalize_role(raw):
    if not raw:
        return ROLE_PATIENT
    t = raw.strip()
    tl = t.lower()
    if tl in ('patient', 'patients'):
        return ROLE_PATIENT
    if tl in ('doctor', 'doctors'):
        return ROLE_DOCTOR
    if 'pathology' in tl:
        return ROLE_PATHOLOGY
    if tl in ('administrator', 'admin', 'administrators'):
        return ROLE_ADMIN
    if ('clinic' in tl and 'hospital' in tl) or tl in ('hospital', 'pharmacy'):
        return ROLE_PHARMACY
    key = tl.replace(' ', '_').replace('/', '_')
    while '__' in key:
        key = key.replace('__', '_')
    if key in ROLE_ALIASES:
        return ROLE_ALIASES[key]
    if t in (ROLE_PATIENT, ROLE_DOCTOR, ROLE_PATHOLOGY, ROLE_PHARMACY, ROLE_ADMIN, 'Hospital'):
        return ROLE_PHARMACY if t == 'Hospital' else t
    return t.title()


def home_url_for_user(user):
    if user.role == ROLE_PENDING:
        return url_for('oauth_choose_role')
    if user.role == ROLE_DOCTOR:
        return url_for('doctor_home')
    if user.role == ROLE_PATIENT:
        return url_for('patient_prescriptions')
    if user.role == ROLE_PATHOLOGY:
        return url_for('pathology_lab_home')
    if user.role == ROLE_ADMIN:
        return url_for('admin_home')
    if user.role in (ROLE_PHARMACY, 'Hospital'):
        return url_for('pharmacy_prescriptions')
    return url_for('landing')


def onboarding_url_for_role(role):
    if role == ROLE_PATIENT:
        return url_for('onboarding_patient')
    if role == ROLE_DOCTOR:
        return url_for('onboarding_doctor')
    if role == ROLE_PATHOLOGY:
        return url_for('onboarding_pathology')
    if role in (ROLE_PHARMACY, 'Hospital'):
        return url_for('pharmacy_prescriptions')
    if role == ROLE_ADMIN:
        return url_for('admin_home')
    if role == ROLE_PENDING:
        return url_for('oauth_choose_role')
    return url_for('landing')


# ----------------------------------------------------------------------
# SCHEMAS (Validation)
class UserRegistrationSchema(ma.Schema):
    name = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=8))
    role = fields.Str(required=True)

registration_schema = UserRegistrationSchema()


def log_action(action, details=None):
    """Utility to record administrative or security events."""
    try:
        user_id = session.get('user_id')
        log = AuditLog(
            user_id=user_id,
            action=action,
            ip_address=request.remote_addr,
            details=details
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        app.logger.error(f"Failed to write audit log: {str(e)}")


# ----------------------------------------------------------------------
@app.before_request
def load_user():
    """Make the logged-in user available as g.user in every request."""
    if session.get('user_id'):
        uid = session.get('user_id')
        g.user = db.session.get(User, uid) if uid else None
    else:
        g.user = None


@app.before_request
def ensure_onboarding_complete():
    """Pending Google users must pick a role; others complete role-specific onboarding."""
    if not g.user:
        return
    ep = request.endpoint
    if not ep or ep == 'static':
        return

    if g.user.role == ROLE_PENDING:
        if ep in ('oauth_choose_role', 'logout'):
            return
        return redirect(url_for('oauth_choose_role'))

    if getattr(g.user, 'onboarding_complete', True):
        return
    allowed = {'onboarding_patient', 'onboarding_doctor', 'onboarding_pathology', 'logout'}
    if ep in allowed:
        return
    return redirect(onboarding_url_for_role(g.user.role))


# ----------------------------------------------------------------------
# PUBLIC PAGES
@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/health')
def health_check():
    """Service health monitoring."""
    try:
        # Check database connectivity
        db.session.execute(text('SELECT 1'))
        return {
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.datetime.utcnow().isoformat()
        }, 200
    except Exception as e:
        app.logger.error(f"Health check failed: {str(e)}")
        return {
            'status': 'unhealthy',
            'error': 'Database connection failed'
        }, 500

@app.route('/getting-started')
def getting_started():
    return render_template('getting-started.html')

@app.route('/for-patients')
def patients_info():
    return render_template('patients_info.html')

@app.route('/for-providers')
def providers_info():
    return render_template('providers_info.html')

@app.route('/marketplace')
def marketplace():
    products_path = os.path.join(app.static_folder, 'data', 'products.json')
    products = []
    if os.path.exists(products_path):
        with open(products_path, 'r', encoding='utf-8') as f:
            products = json.load(f)
    return render_template('marketplace.html', products=products)

# ─── OpenFDA Pharma Intelligence API ──────────────────────────────────────────
from flask import jsonify

_openfda_cache = None          # in-memory cache so JSON is only read once

def _load_openfda():
    """Load openfda_drugs.json once, preferring MongoDB if available."""
    global _openfda_cache
    if _openfda_cache is not None:
        return _openfda_cache

    # 1️⃣  Try MongoDB
    try:
        from pymongo import MongoClient
        client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=1500)
        client.server_info()
        coll = client["pharma_db"]["drugs"]
        _openfda_cache = list(coll.find({}, {"_id": 0}))
        app.logger.info("OpenFDA: loaded %d docs from MongoDB", len(_openfda_cache))
        return _openfda_cache
    except Exception:
        pass

    # 2️⃣  Fall back to JSON file
    fda_path = os.path.join(app.static_folder, "data", "openfda_drugs.json")
    if os.path.exists(fda_path):
        with open(fda_path, "r", encoding="utf-8") as f:
            _openfda_cache = json.load(f)
        app.logger.info("OpenFDA: loaded %d docs from JSON fallback", len(_openfda_cache))
        return _openfda_cache

    _openfda_cache = []
    return _openfda_cache


@app.route("/api/pharma/search")
def pharma_search():
    """Search drug profiles.  ?q=<query>&limit=<n>"""
    q     = (request.args.get("q", "") or "").lower().strip()
    limit = min(int(request.args.get("limit", 20)), 100)
    docs  = _load_openfda()

    if not q:
        results = docs[:limit]
    else:
        results = [
            d for d in docs
            if q in d.get("drug_name", "")
            or any(q in b.lower() for b in d.get("brand_names", []))
            or any(q in s.lower() for s in d.get("side_effects", []))
        ][:limit]

    return jsonify({
        "query":   q,
        "total":   len(results),
        "results": results
    })


@app.route("/api/pharma/drug/<name>")
def pharma_drug(name):
    """Full profile for one drug by canonical name."""
    docs = _load_openfda()
    name_lower = name.lower()
    match = next(
        (d for d in docs if d.get("drug_name", "") == name_lower),
        None
    )
    if match:
        return jsonify(match)
    return jsonify({"error": "Drug not found", "name": name}), 404


@app.route('/doctors')
def doctors():
    return render_template('doctors.html')

@app.route('/insurance')
def insurance():
    return render_template('insurance.html')


@app.route('/onboarding')
def onboarding_hub():
    """Choose how you will use CareConnect before sign-up."""
    return render_template('onboarding_hub.html')

# ----------------------------------------------------------------------
# PROFILE CREATION
@app.route('/create-profile', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
def create_profile():
    if request.method == 'POST':
        # Validate Input
        errors = registration_schema.validate(request.form)
        if errors:
            for field, msgs in errors.items():
                flash(f"{field.capitalize()}: {', '.join(msgs)}", 'danger')
            return redirect(url_for('getting_started'))

        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        role = normalize_role(request.form.get('role'))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered', 'danger')
            return redirect(url_for('getting_started'))

        needs_onboarding = role in (ROLE_PATIENT, ROLE_DOCTOR, ROLE_PATHOLOGY)
        new_user = User(
            name=name,
            email=email,
            role=role,
            onboarding_complete=not needs_onboarding,
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        session['user_id'] = new_user.id
        log_action("Register", f"New account created for {email} as {role}")
        flash('Account created.', 'success')
        if needs_onboarding:
            flash('Complete the short onboarding for your account type.', 'info')
            return redirect(onboarding_url_for_role(role))
        return redirect(home_url_for_user(new_user))

    return render_template('create-profile.html')

# ----------------------------------------------------------------------
# AUTHENTICATION
@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            log_action("Login", "Standard credentials login")
            if user.role == ROLE_PENDING:
                flash('Choose how you will use CareConnect to continue.', 'info')
                return redirect(url_for('oauth_choose_role'))
            if not getattr(user, 'onboarding_complete', True):
                return redirect(onboarding_url_for_role(user.role))
            return redirect(home_url_for_user(user))

        flash('Invalid credentials.', 'danger')
        return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/google-login')
def google_login():
    redirect_uri = url_for('google_auth', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/google/auth')
def google_auth():
    try:
        token = google.authorize_access_token()
    except Exception as e:
        flash('Authentication session expired or failed. Please try again.', 'danger')
        return redirect(url_for('login'))
        
    user_info = token.get('userinfo')
    
    if user_info:
        user = User.query.filter_by(email=user_info['email']).first()
        if not user:
            user = User(
                email=user_info['email'],
                name=user_info.get('name', user_info['email']),
                google_id=user_info['sub'],
                role=ROLE_PENDING,
                onboarding_complete=False,
            )
            db.session.add(user)
            db.session.commit()

        session['user_id'] = user.id

        if user.role == ROLE_PENDING:
            flash('Please choose how you will use CareConnect.', 'info')
            return redirect(url_for('oauth_choose_role'))
        if not getattr(user, 'onboarding_complete', True):
            return redirect(onboarding_url_for_role(user.role))
        return redirect(home_url_for_user(user))

    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('landing'))

# ----------------------------------------------------------------------
def roles_required(*allowed_roles):
    """Require login and one of the given roles (Clinic / Hospital matches Hospital)."""
    allowed = set(allowed_roles)

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not g.user:
                flash('You need to log in to continue.', 'warning')
                return redirect(url_for('login'))
            r = g.user.role
            ok = r in allowed
            if not ok and ROLE_PHARMACY in allowed and r in ('Clinic / Hospital', 'Hospital'):
                ok = True
            if not ok:
                flash('You do not have access to this page.', 'warning')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return wrapper
    return decorator


def role_required(required_role):
    return roles_required(required_role)


# ----------------------------------------------------------------------
# GOOGLE OAUTH — account type (new users start as Pending until they choose)
@app.route('/oauth/choose-role', methods=['GET', 'POST'])
@roles_required(ROLE_PENDING)
def oauth_choose_role():
    if request.method == 'POST':
        raw = request.form.get('role', '').strip()
        if not raw:
            flash('Select whether you are a patient, doctor, pathology lab, hospital, or administrator.', 'warning')
            return redirect(url_for('oauth_choose_role'))
        chosen = normalize_role(raw)
        if chosen == ROLE_PENDING:
            flash('Invalid account type.', 'danger')
            return redirect(url_for('oauth_choose_role'))
        g.user.role = chosen
        if chosen in (ROLE_ADMIN, ROLE_PHARMACY):
            g.user.onboarding_complete = True
        else:
            g.user.onboarding_complete = False
        db.session.commit()
        flash('Account type saved.', 'success')
        if g.user.onboarding_complete:
            return redirect(home_url_for_user(g.user))
        return redirect(onboarding_url_for_role(chosen))

    return render_template('oauth_choose_role.html', user=g.user)


# ----------------------------------------------------------------------
# ADMINISTRATOR
@app.route('/admin')
@roles_required(ROLE_ADMIN)
def admin_home():
    return render_template('admin_home.html', user=g.user)


# ----------------------------------------------------------------------
# ONBOARDING (role-specific first-time setup)
@app.route('/onboarding/patient', methods=['GET', 'POST'])
@roles_required(ROLE_PATIENT)
def onboarding_patient():
    if request.method == 'POST':
        g.user.onboarding_complete = True
        db.session.commit()
        flash('Welcome — your patient hub is ready.', 'success')
        return redirect(url_for('patient_prescriptions'))
    return render_template('onboarding_patient.html', user=g.user)


@app.route('/onboarding/doctor', methods=['GET', 'POST'])
@roles_required(ROLE_DOCTOR)
def onboarding_doctor():
    if request.method == 'POST':
        license_id = request.form.get('medical_license', '').strip()
        specialty = request.form.get('specialty', '').strip()
        facility_type_id = request.form.get('facility_type_id')
        if not license_id or not specialty:
            flash('Please enter your license number and specialty.', 'warning')
            return redirect(url_for('onboarding_doctor'))
        council = request.form.get('council', '').strip() or None
        ft = None
        if facility_type_id:
            try:
                ft = db.session.get(FacilityType, int(facility_type_id))
            except Exception:
                ft = None
        profile = DoctorProfile.query.filter_by(user_id=g.user.id).first()
        if not profile:
            profile = DoctorProfile(user_id=g.user.id, medical_license=license_id, specialty=specialty)
            db.session.add(profile)
        profile.medical_license = license_id
        profile.specialty = specialty
        profile.council = council
        profile.facility_type_id = ft.id if ft else None
        g.user.onboarding_complete = True
        db.session.commit()
        flash('Provider profile saved. Credential verification can be added in production.', 'success')
        return redirect(url_for('doctor_home'))
    facility_types = FacilityType.query.order_by(FacilityType.name.asc()).all()
    return render_template('onboarding_doctor.html', user=g.user, facility_types=facility_types)


# ----------------------------------------------------------------------
# PATIENT DIRECTORY: browse doctors + facility types
@app.route('/find-care')
@roles_required(ROLE_PATIENT)
def find_care():
    q = (request.args.get('q') or '').strip().lower()
    facility_type_id = request.args.get('facility_type_id')

    query = DoctorProfile.query.join(User, DoctorProfile.user_id == User.id)
    if facility_type_id:
        try:
            ftid = int(facility_type_id)
            query = query.filter(DoctorProfile.facility_type_id == ftid)
        except Exception:
            pass
    if q:
        like = f"%{q}%"
        query = query.filter(
            (User.name.ilike(like)) |
            (DoctorProfile.specialty.ilike(like))
        )

    doctors = query.order_by(User.name.asc()).all()
    facility_types = FacilityType.query.order_by(FacilityType.name.asc()).all()
    return render_template(
        'find_care.html',
        doctors=doctors,
        facility_types=facility_types,
        q=request.args.get('q', ''),
        facility_type_id=str(facility_type_id or ''),
    )


@app.route('/onboarding/pathology', methods=['GET', 'POST'])
@roles_required(ROLE_PATHOLOGY)
def onboarding_pathology():
    if request.method == 'POST':
        lab_name = request.form.get('lab_name', '').strip()
        city = request.form.get('city', '').strip()
        if not lab_name or not city:
            flash('Please enter your lab name and city.', 'warning')
            return redirect(url_for('onboarding_pathology'))
        g.user.organization = lab_name
        g.user.onboarding_complete = True
        db.session.commit()
        flash('Lab profile saved — welcome to the network.', 'success')
        return redirect(url_for('pathology_lab_home'))
    return render_template('onboarding_pathology.html', user=g.user)


# ----------------------------------------------------------------------
# PATHOLOGY LAB
@app.route('/pathology-lab')
@roles_required(ROLE_PATHOLOGY)
def pathology_lab_home():
    return render_template(
        'pathology_lab_home.html',
        user=g.user,
        lab_orders=LAB_ORDERS,
    )


# ----------------------------------------------------------------------
# DOCTOR PAGES
@app.route('/doctor-home')
@roles_required(ROLE_DOCTOR)
def doctor_home():
    return render_template('doctor_home.html', user=g.user)

@app.route('/doctor-prescriptions')
@roles_required(ROLE_DOCTOR)
def doctor_prescriptions():
    my_rx = [p for p in PRESCRIPTIONS if p['doctor_email'] == g.user.email]
    return render_template('doctor_prescriptions.html', prescriptions=my_rx)

# ----------------------------------------------------------------------
# PATIENT PAGES
@app.route('/patient-prescriptions')
@roles_required(ROLE_PATIENT)
def patient_prescriptions():
    my_rx = [p for p in PRESCRIPTIONS if p['patient_email'] == g.user.email]
    return render_template('patient_prescriptions.html', prescriptions=my_rx)

# ----------------------------------------------------------------------
# PHARMACY (Clinic / Hospital) PAGES
@app.route('/pharmacy-prescriptions')
@roles_required(ROLE_PHARMACY)
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