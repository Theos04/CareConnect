from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g
)
from functools import wraps
import os
import json
import logging
import datetime
import uuid
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from sqlalchemy import inspect, text
from models import db, User, FacilityType, DoctorProfile, Prescription, LabOrder, AuditLog
from models import Conversation, Message, Appointment, MedicationReminder, PromResponse
from fhir_integration import fhir_bp
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

# Suppress noisy health probe logs from platform monitors
import logging as _logging
_wz_log = _logging.getLogger('werkzeug')
_wz_log.addFilter(lambda r: not (
    r.getMessage().find('/health') != -1 or
    r.getMessage().find('/upload') != -1
))

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

# Register blueprints
app.register_blueprint(fhir_bp)
csrf.exempt(fhir_bp)   # FHIR endpoints use Bearer tokens, not CSRF cookies

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


def _seed_demo_data():
    """Insert sample prescriptions and lab orders for guest demo accounts.
    Idempotent â€” skips if records already exist."""
    if Prescription.query.count() > 0:
        return

    guest_doctor  = User.query.filter_by(email='guest_doctor@careconnect.dev').first()
    guest_patient = User.query.filter_by(email='guest_patient@careconnect.dev').first()
    if not guest_doctor:
        return

    import datetime as _dt
    samples = [
        Prescription(
            doctor_id=guest_doctor.id,
            patient_id=guest_patient.id if guest_patient else None,
            patient_name='John Doe',
            patient_email='john@example.com',
            medication='Amoxicillin 500mg',
            dosage='1 tablet every 8 hours',
            duration='7 days',
            status='Pending',
            created_at=_dt.datetime(2025, 10, 27),
        ),
        Prescription(
            doctor_id=guest_doctor.id,
            patient_name='Priya Singh',
            patient_email='priya@example.com',
            medication='Ibuprofen 400mg',
            dosage='1 tablet as needed',
            duration='5 days',
            status='Filled',
            created_at=_dt.datetime(2025, 10, 26),
        ),
        Prescription(
            doctor_id=guest_doctor.id,
            patient_name='Alex Kim',
            patient_email='alex@example.com',
            medication='Metformin 850mg',
            dosage='1 tablet twice daily',
            duration='30 days',
            status='Completed',
            notes='Monitor blood sugar weekly',
            created_at=_dt.datetime(2025, 10, 20),
        ),
    ]
    db.session.add_all(samples)

    if LabOrder.query.count() == 0:
        labs = [
            LabOrder(order_ref='LAB-1001', doctor_id=guest_doctor.id,
                     patient_name='John Doe',    test='CBC + metabolic panel',
                     priority='Routine', status='Sample received',
                     ordered_at=_dt.datetime(2026, 3, 28)),
            LabOrder(order_ref='LAB-1002', doctor_id=guest_doctor.id,
                     patient_name='Priya Singh', test='HbA1c',
                     priority='Urgent',  status='Processing',
                     ordered_at=_dt.datetime(2026, 3, 29)),
            LabOrder(order_ref='LAB-1003', doctor_id=guest_doctor.id,
                     patient_name='Alex Kim',    test='Lipid profile',
                     priority='Routine', status='Report ready',
                     ordered_at=_dt.datetime(2026, 3, 30)),
        ]
        db.session.add_all(labs)

    db.session.commit()




with app.app_context():
    db.create_all()
    _migrate_user_columns()
    _seed_facility_types()
    _seed_demo_data()

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# READ REPLICA HELPER
# If REPLICA_DATABASE_URL is set, reporting/read-heavy queries can use a
# separate session bound to the replica engine.  Falls back to primary silently.
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_replica_engine = None

def _get_replica_session():
    """Return a SQLAlchemy session pointed at the read replica (or primary)."""
    global _replica_engine
    replica_url = app.config.get('REPLICA_DATABASE_URL')
    if replica_url and _replica_engine is None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        _replica_engine = create_engine(
            replica_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
    if _replica_engine:
        from sqlalchemy.orm import Session as _Session
        return _Session(bind=_replica_engine)
    return db.session   # fall back to primary


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SEED HELPER â€” populate demo prescriptions & lab orders for guest accounts
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Canonical roles used in User.role
ROLE_PATIENT = 'Patient'
ROLE_DOCTOR = 'Doctor'
ROLE_PATHOLOGY = 'Pathology Lab'
ROLE_PHARMACY = 'Clinic / Hospital'
ROLE_ADMIN = 'Administrator'
# New Google OAuth user until they pick an account type
ROLE_PENDING = 'Pending'

# Map signup form values â†’ canonical role strings
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
        db.session.execute(text('SELECT 1'))
        return {
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.datetime.utcnow().isoformat()
        }, 200
    except Exception as e:
        app.logger.error(f"Health check failed: {str(e)}")
        return {'status': 'unhealthy', 'error': 'Database connection failed'}, 500

@app.route('/upload', methods=['POST'])
def upload():
    """Stub endpoint â€” satisfies platform health probes."""
    return {'status': 'ok'}, 200

@app.route('/getting-started')
def getting_started():
    return render_template('getting-started.html')

@app.route('/guest-login')
def guest_login():
    """One-click guest session for testing â€” creates/reuses a guest account."""
    role = request.args.get('role', 'patient').lower()
    role_map = {
        'patient':   ROLE_PATIENT,
        'doctor':    ROLE_DOCTOR,
        'pathology': ROLE_PATHOLOGY,
        'admin':     ROLE_ADMIN,
        'hospital':  ROLE_PHARMACY,
    }
    canonical = role_map.get(role, ROLE_PATIENT)
    guest_email = f'guest_{role}@careconnect.dev'

    user = User.query.filter_by(email=guest_email).first()
    if not user:
        user = User(
            name=f'Guest {canonical}',
            email=guest_email,
            role=canonical,
            onboarding_complete=True,
        )
        user.set_password('guest_demo_2026')
        db.session.add(user)
        db.session.commit()

    session['user_id'] = user.id
    flash(f'Logged in as Guest {canonical} â€” demo mode.', 'info')
    return redirect(home_url_for_user(user))

@app.route('/for-patients')
def patients_info():
    return render_template('patients_info.html')

@app.route('/for-providers')
def providers_info():
    return render_template('providers_info.html')

@app.route('/marketplace')
def marketplace():
    return render_template('marketplace.html')


@app.route('/api/marketplace/products')
def api_marketplace_products():
    """Serve the products catalogue with categories extracted."""
    products_path = os.path.join(app.static_folder, 'data', 'marketplace', 'products.json')
    # fallback to old path
    if not os.path.exists(products_path):
        products_path = os.path.join(app.static_folder, 'data', 'products.json')

    if not os.path.exists(products_path):
        return jsonify({'products': [], 'categories': []})

    with open(products_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # data may be {"products": [...]} or a bare list
    products = data.get('products', data) if isinstance(data, dict) else data

    # apply optional query filters
    q        = (request.args.get('q') or '').lower().strip()
    category = (request.args.get('category') or '').lower().strip()
    rx_only  = request.args.get('prescription_required')

    if q:
        products = [p for p in products if
                    q in p.get('name', '').lower() or
                    q in p.get('generic_name', '').lower() or
                    q in p.get('manufacturer', '').lower()]
    if category and category != 'all':
        products = [p for p in products if
                    p.get('category', '').lower() == category]
    if rx_only is not None:
        flag = rx_only.lower() in ('true', '1')
        products = [p for p in products if p.get('prescription_required') == flag]

    # derive unique sorted categories from the full catalogue
    with open(products_path, 'r', encoding='utf-8') as f:
        all_data = json.load(f)
    all_products = all_data.get('products', all_data) if isinstance(all_data, dict) else all_data
    categories = sorted({p.get('category', '') for p in all_products if p.get('category')})

    return jsonify({'products': products, 'categories': categories})


@app.route('/api/marketplace/checkout', methods=['POST'])
def api_marketplace_checkout():
    """Simple order stub — logs the order and returns a reference ID."""
    data  = request.get_json(silent=True) or {}
    items = data.get('items', [])
    total = data.get('total', 0)

    if not items:
        return jsonify({'success': False, 'error': 'Cart is empty'}), 400

    order_id = f'ORD-{uuid.uuid4().hex[:8].upper()}'
    log_action('Marketplace.checkout',
               f'Order {order_id} — {len(items)} items — ₹{total:.2f}')

    return jsonify({'success': True, 'order_id': order_id,
                    'message': f'Order {order_id} placed successfully'})

# â”€â”€â”€ OpenFDA Pharma Intelligence API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
from flask import jsonify

_openfda_cache = None          # in-memory cache so JSON is only read once

def _load_openfda():
    """Load openfda_drugs.json once, preferring MongoDB if available."""
    global _openfda_cache
    if _openfda_cache is not None:
        return _openfda_cache

    # 1ï¸âƒ£  Try MongoDB
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

    # 2ï¸âƒ£  Fall back to JSON file
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
# GOOGLE OAUTH â€” account type (new users start as Pending until they choose)
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
        flash('Welcome â€” your patient hub is ready.', 'success')
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
        flash('Lab profile saved â€” welcome to the network.', 'success')
        return redirect(url_for('pathology_lab_home'))
    return render_template('onboarding_pathology.html', user=g.user)


# ----------------------------------------------------------------------
# PATHOLOGY LAB
@app.route('/pathology-lab')
@roles_required(ROLE_PATHOLOGY)
def pathology_lab_home():
    lab_orders = LabOrder.query.order_by(LabOrder.ordered_at.desc()).all()
    return render_template(
        'pathology_lab_home.html',
        user=g.user,
        lab_orders=[o.to_dict() for o in lab_orders],
    )


# ----------------------------------------------------------------------
# DOCTOR PAGES
@app.route('/doctor-home')
@roles_required(ROLE_DOCTOR)
def doctor_home():
    # Appointments today
    today = datetime.datetime.now().date()
    today_start = datetime.datetime.combine(today, datetime.time.min)
    today_end = datetime.datetime.combine(today, datetime.time.max)
    
    appointments_today = Appointment.query.filter(
        Appointment.provider_id == g.user.id,
        Appointment.appointment_date >= today_start,
        Appointment.appointment_date <= today_end
    ).order_by(Appointment.appointment_date.asc()).all()

    # Pending lab orders
    pending_labs = LabOrder.query.filter(
        LabOrder.doctor_id == g.user.id,
        LabOrder.status.notin_(['Completed', 'Cancelled'])
    ).all()
    
    # Active prescriptions/patients
    active_prescriptions = Prescription.query.filter(
        Prescription.doctor_id == g.user.id,
        Prescription.status.in_(['Pending', 'Active'])
    ).all()
    
    unique_patients = set(rx.patient_name for rx in active_prescriptions if rx.patient_name)
    
    context = {
        'user': g.user,
        'appointments_count': len(appointments_today),
        'appointments': appointments_today,
        'pending_labs_count': len(pending_labs),
        'active_patients_count': len(unique_patients)
    }
    
    return render_template('doctor_home.html', **context)


@app.route('/doctor-prescriptions')
@roles_required(ROLE_DOCTOR)
def doctor_prescriptions():
    my_rx = (Prescription.query
             .filter_by(doctor_id=g.user.id)
             .order_by(Prescription.created_at.desc())
             .all())
             
    # Fetch all registered patients to populate the roster
    patients = User.query.filter_by(role=ROLE_PATIENT).all()
    
    return render_template('doctor_prescriptions.html',
                           prescriptions=[p.to_dict() for p in my_rx],
                           patients=[{'id': p.id, 'name': p.name, 'email': p.email} for p in patients])


# â”€â”€ Prescription CRUD API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.route('/api/prescriptions', methods=['GET'])
@roles_required(ROLE_DOCTOR)
def api_list_prescriptions():
    """GET /api/prescriptions  â€” doctor's own prescriptions (JSON)."""
    status = request.args.get('status')
    q      = request.args.get('q', '').strip().lower()
    query  = Prescription.query.filter_by(doctor_id=g.user.id)
    if status:
        query = query.filter_by(status=status)
    if q:
        query = query.filter(
            Prescription.patient_name.ilike(f'%{q}%') |
            Prescription.medication.ilike(f'%{q}%')
        )
    rxs = query.order_by(Prescription.created_at.desc()).all()
    return jsonify([p.to_dict() for p in rxs])


@app.route('/api/prescriptions', methods=['POST'])
@roles_required(ROLE_DOCTOR)
def api_create_prescription():
    """POST /api/prescriptions  â€” issue a new prescription."""
    data = request.get_json(silent=True) or request.form
    patient_name  = (data.get('patient_name') or '').strip()
    medication    = (data.get('medication')    or '').strip()
    if not patient_name or not medication:
        return jsonify({'error': 'patient_name and medication are required'}), 400

    rx = Prescription(
        doctor_id     = g.user.id,
        patient_name  = patient_name,
        patient_email = (data.get('patient_email') or '').strip() or None,
        medication    = medication,
        dosage        = (data.get('dosage')    or '').strip() or None,
        duration      = (data.get('duration')  or '').strip() or None,
        notes         = (data.get('notes')     or '').strip() or None,
        status        = 'Pending',
    )
    db.session.add(rx)
    db.session.commit()
    log_action('Prescription.create', f'Rx #{rx.id} for {patient_name}')
    return jsonify(rx.to_dict()), 201


@app.route('/api/prescriptions/<int:rx_id>', methods=['GET'])
@roles_required(ROLE_DOCTOR, ROLE_PATIENT, ROLE_PHARMACY)
def api_get_prescription(rx_id):
    """GET /api/prescriptions/<id>  â€” fetch one prescription."""
    rx = db.session.get(Prescription, rx_id)
    if not rx:
        return jsonify({'error': 'Not found'}), 404
    # Doctors see only their own; patients see only theirs; pharmacy sees all
    if g.user.role == ROLE_DOCTOR   and rx.doctor_id  != g.user.id:
        return jsonify({'error': 'Forbidden'}), 403
    if g.user.role == ROLE_PATIENT  and rx.patient_email != g.user.email:
        return jsonify({'error': 'Forbidden'}), 403
    return jsonify(rx.to_dict())


@app.route('/api/prescriptions/<int:rx_id>', methods=['PATCH'])
@roles_required(ROLE_DOCTOR, ROLE_PHARMACY)
def api_update_prescription(rx_id):
    """PATCH /api/prescriptions/<id>  â€” update status or fields."""
    rx = db.session.get(Prescription, rx_id)
    if not rx:
        return jsonify({'error': 'Not found'}), 404
    if g.user.role == ROLE_DOCTOR and rx.doctor_id != g.user.id:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json(silent=True) or request.form
    allowed_statuses = {'Pending', 'Filled', 'Completed', 'Cancelled'}
    if 'status' in data and data['status'] in allowed_statuses:
        rx.status = data['status']
    for field in ('dosage', 'duration', 'notes', 'medication'):
        if field in data:
            setattr(rx, field, data[field])
    db.session.commit()
    log_action('Prescription.update', f'Rx #{rx_id} â†’ {rx.status}')
    return jsonify(rx.to_dict())


@app.route('/api/prescriptions/<int:rx_id>', methods=['DELETE'])
@roles_required(ROLE_DOCTOR)
def api_delete_prescription(rx_id):
    """DELETE /api/prescriptions/<id>  â€” doctor can delete own prescriptions."""
    rx = db.session.get(Prescription, rx_id)
    if not rx:
        return jsonify({'error': 'Not found'}), 404
    if rx.doctor_id != g.user.id:
        return jsonify({'error': 'Forbidden'}), 403
    db.session.delete(rx)
    db.session.commit()
    log_action('Prescription.delete', f'Rx #{rx_id} deleted')
    return jsonify({'deleted': rx_id})


# â”€â”€ Lab Order CRUD API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.route('/api/lab-orders', methods=['GET'])
@roles_required(ROLE_DOCTOR, ROLE_PATHOLOGY)
def api_list_lab_orders():
    """GET /api/lab-orders  â€” doctor sees own orders; pathology sees all."""
    query = LabOrder.query
    if g.user.role == ROLE_DOCTOR:
        query = query.filter_by(doctor_id=g.user.id)
    orders = query.order_by(LabOrder.ordered_at.desc()).all()
    return jsonify([o.to_dict() for o in orders])


@app.route('/api/lab-orders', methods=['POST'])
@roles_required(ROLE_DOCTOR)
def api_create_lab_order():
    """POST /api/lab-orders  â€” doctor creates a lab requisition."""
    data = request.get_json(silent=True) or request.form
    patient_name = (data.get('patient_name') or '').strip()
    test         = (data.get('test')         or '').strip()
    if not patient_name or not test:
        return jsonify({'error': 'patient_name and test are required'}), 400

    # Generate sequential order_ref
    last = LabOrder.query.order_by(LabOrder.id.desc()).first()
    next_num = (last.id + 1) if last else 1001
    order_ref = f'LAB-{next_num}'

    order = LabOrder(
        order_ref    = order_ref,
        doctor_id    = g.user.id,
        patient_name = patient_name,
        test         = test,
        priority     = data.get('priority', 'Routine'),
        notes        = (data.get('notes') or '').strip() or None,
        status       = 'Sample received',
    )
    db.session.add(order)
    db.session.commit()
    log_action('LabOrder.create', f'{order_ref} for {patient_name}')
    return jsonify(order.to_dict()), 201


@app.route('/api/lab-orders/<int:order_id>', methods=['PATCH'])
@roles_required(ROLE_DOCTOR, ROLE_PATHOLOGY)
def api_update_lab_order(order_id):
    """PATCH /api/lab-orders/<id>  â€” update status or notes."""
    order = db.session.get(LabOrder, order_id)
    if not order:
        return jsonify({'error': 'Not found'}), 404
    if g.user.role == ROLE_DOCTOR and order.doctor_id != g.user.id:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json(silent=True) or request.form
    allowed = {'Sample received', 'Processing', 'Report ready', 'Cancelled'}
    if 'status' in data and data['status'] in allowed:
        order.status = data['status']
    if 'notes' in data:
        order.notes = data['notes']
    db.session.commit()
    log_action('LabOrder.update', f'{order.order_ref} â†’ {order.status}')
    return jsonify(order.to_dict())


@app.route('/api/lab-orders/<int:order_id>', methods=['DELETE'])
@roles_required(ROLE_DOCTOR)
def api_delete_lab_order(order_id):
    """DELETE /api/lab-orders/<id>  â€” doctor cancels own order."""
    order = db.session.get(LabOrder, order_id)
    if not order:
        return jsonify({'error': 'Not found'}), 404
    if order.doctor_id != g.user.id:
        return jsonify({'error': 'Forbidden'}), 403
    db.session.delete(order)
    db.session.commit()
    log_action('LabOrder.delete', f'{order.order_ref} deleted')
    return jsonify({'deleted': order_id})


# ----------------------------------------------------------------------
# PATIENT PAGES
@app.route('/patient-prescriptions')
@roles_required(ROLE_PATIENT)
def patient_prescriptions():
    my_rx = (Prescription.query
             .filter_by(patient_email=g.user.email)
             .order_by(Prescription.created_at.desc())
             .all())
    return render_template('patient_prescriptions.html',
                           prescriptions=[p.to_dict() for p in my_rx])


# ----------------------------------------------------------------------
# PHARMACY (Clinic / Hospital) PAGES
@app.route('/pharmacy-prescriptions')
@roles_required(ROLE_PHARMACY)
def pharmacy_prescriptions():
    all_rx = (Prescription.query
              .order_by(Prescription.created_at.desc())
              .all())
    return render_template('pharmacy_prescriptions.html',
                           prescriptions=[p.to_dict() for p in all_rx])

# ----------------------------------------------------------------------
# OTHER PAGES (unchanged)
@app.route('/workspace')
@roles_required(ROLE_DOCTOR)
def workspace():
    # Fetch comprehensive clinic data
    appointments = Appointment.query.filter_by(provider_id=g.user.id).order_by(Appointment.appointment_date.desc()).all()
    lab_orders = LabOrder.query.filter_by(doctor_id=g.user.id).order_by(LabOrder.ordered_at.desc()).all()
    prescriptions = Prescription.query.filter_by(doctor_id=g.user.id).order_by(Prescription.created_at.desc()).all()
    
    context = {
        'user': g.user,
        'appointments': appointments,
        'lab_orders': lab_orders,
        'prescriptions': prescriptions
    }
    return render_template('workspace.html', **context)

@app.route('/queue')
@roles_required(ROLE_DOCTOR)
def queue_dashboard():
    # 1. Fetch today's actual appointments queue
    today = datetime.datetime.now().date()
    today_start = datetime.datetime.combine(today, datetime.time.min)
    today_end = datetime.datetime.combine(today, datetime.time.max)
    
    appointments = Appointment.query.filter(
        Appointment.provider_id == g.user.id,
        Appointment.appointment_date >= today_start,
        Appointment.appointment_date <= today_end
    ).order_by(Appointment.appointment_date.asc()).all()
    
    # 2. Enrich and pair with Prescriptions
    queue_data = []
    
    # Simple deterministic mock data generator based on ID
    providers = ['BlueCross BlueShield', 'Aetna', 'Cigna', 'UnitedHealthcare', 'Medicare']
    
    for appt in appointments:
        patient_name = appt.patient.name if appt.patient else 'Unknown'
        
        # Lookup latest active prescription for pairing
        rx = Prescription.query.filter(
            Prescription.patient_name == patient_name,
            Prescription.doctor_id == g.user.id
        ).order_by(Prescription.created_at.desc()).first()
        
        # Generate stable mock billing data
        pid = appt.patient_id if appt.patient_id else 0
        insurance = providers[pid % len(providers)]
        copay = 25 if (pid % 2 == 0) else 50
        billing_status = 'Cleared' if copay == 25 else 'Pending Copay'
        
        queue_data.append({
            'appointment': appt.to_dict() if hasattr(appt, 'to_dict') else {'id': appt.id, 'time': appt.appointment_date.strftime('%H:%M'), 'type': appt.appt_type, 'reason': appt.reason, 'status': appt.status},
            'patient_name': patient_name,
            'insurance': {
                'provider': insurance,
                'policy_id': f'POL-{10000 + pid}',
                'copay': copay,
                'billing_status': billing_status
            },
            'prescription': rx.to_dict() if rx and hasattr(rx, 'to_dict') else (
                {
                    'id': rx.id,
                    'medication': rx.medication,
                    'dosage': rx.dosage,
                    'status': rx.status,
                    'duration': rx.duration,
                    'notes': rx.notes
                } if rx else None
            )
        })

    return render_template('queue-dashboard.html', user=g.user, queue_data=queue_data)


# ══════════════════════════════════════════════════════════════════════════════
# SECURE MESSAGING
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/messaging')
@roles_required(ROLE_PATIENT, ROLE_DOCTOR)
def secure_messaging():
    return render_template('secure_messaging.html', user=g.user)


@app.route('/api/messaging/conversations', methods=['GET'])
@roles_required(ROLE_PATIENT, ROLE_DOCTOR)
def api_list_conversations():
    if g.user.role == ROLE_PATIENT:
        convs = Conversation.query.filter_by(patient_id=g.user.id).all()
    else:
        convs = Conversation.query.filter_by(provider_id=g.user.id).all()

    result = []
    for c in convs:
        last = c.last_message_dict()
        result.append({
            'id':                c.id,
            'provider_name':     c.provider.name,
            'patient_name':      c.patient.name,
            'last_message':      last['text'],
            'last_message_time': last['time'],
            'unread_count':      c.unread_count_for_patient,
        })
    return jsonify(result)


@app.route('/api/messaging/conversations', methods=['POST'])
@roles_required(ROLE_PATIENT)
def api_create_conversation():
    data        = request.get_json(silent=True) or {}
    provider_id = data.get('provider_id')
    if not provider_id:
        return jsonify({'error': 'provider_id required'}), 400
    existing = Conversation.query.filter_by(
        patient_id=g.user.id, provider_id=provider_id).first()
    if existing:
        return jsonify({'id': existing.id}), 200
    conv = Conversation(patient_id=g.user.id, provider_id=provider_id)
    db.session.add(conv)
    db.session.commit()
    return jsonify({'id': conv.id}), 201


@app.route('/api/messaging/conversations/<int:conv_id>', methods=['GET'])
@roles_required(ROLE_PATIENT, ROLE_DOCTOR)
def api_get_conversation(conv_id):
    conv = db.session.get(Conversation, conv_id)
    if not conv:
        return jsonify({'error': 'Not found'}), 404
    if g.user.id not in (conv.patient_id, conv.provider_id):
        return jsonify({'error': 'Forbidden'}), 403
    # Mark messages as read
    conv.messages.filter_by(read=False).update({'read': True})
    db.session.commit()
    return jsonify({
        'id':            conv.id,
        'provider_name': conv.provider.name,
        'patient_name':  conv.patient.name,
        'messages':      [m.to_dict() for m in conv.messages],
    })


@app.route('/api/messaging/send', methods=['POST'])
@roles_required(ROLE_PATIENT, ROLE_DOCTOR)
def api_send_message():
    data    = request.get_json(silent=True) or {}
    conv_id = data.get('conversationId')
    content = (data.get('content') or '').strip()
    if not conv_id or not content:
        return jsonify({'error': 'conversationId and content required'}), 400
    conv = db.session.get(Conversation, conv_id)
    if not conv or g.user.id not in (conv.patient_id, conv.provider_id):
        return jsonify({'error': 'Forbidden'}), 403
    role = 'patient' if g.user.id == conv.patient_id else 'provider'
    msg  = Message(conversation_id=conv_id, sender_id=g.user.id,
                   sender_role=role, content=content)
    db.session.add(msg)
    db.session.commit()
    return jsonify(msg.to_dict()), 201


# ══════════════════════════════════════════════════════════════════════════════
# APPOINTMENT SCHEDULING
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/appointments')
@roles_required(ROLE_PATIENT, ROLE_DOCTOR)
def appointment_scheduling():
    providers = User.query.filter_by(role=ROLE_DOCTOR).all()
    return render_template('appointment_scheduling.html',
                           user=g.user, providers=providers)


@app.route('/api/appointments/slots', methods=['GET'])
@roles_required(ROLE_PATIENT)
def api_appointment_slots():
    """Return available 30-min slots for a provider on a given date."""
    from datetime import date as _date, timedelta, time as _time
    date_str    = request.args.get('date', '')
    provider_id = request.args.get('provider_id')
    try:
        day = datetime.fromisoformat(date_str).date()
    except (ValueError, TypeError):
        day = datetime.utcnow().date()

    # All slots 09:00–17:00 in 30-min increments
    all_slots = []
    t = datetime.combine(day, datetime.min.time().replace(hour=9))
    end = datetime.combine(day, datetime.min.time().replace(hour=17))
    while t < end:
        all_slots.append(t)
        t += __import__('datetime').timedelta(minutes=30)

    # Find booked slots
    booked = set()
    if provider_id:
        appts = Appointment.query.filter(
            Appointment.provider_id == provider_id,
            Appointment.appointment_date >= datetime.combine(day, datetime.min.time()),
            Appointment.appointment_date <  datetime.combine(day, datetime.min.time()) + __import__('datetime').timedelta(days=1),
            Appointment.status != 'cancelled',
        ).all()
        booked = {a.appointment_date.strftime('%H:%M') for a in appts}

    return jsonify([{
        'time':   s.strftime('%H:%M'),
        'booked': s.strftime('%H:%M') in booked,
    } for s in all_slots])


@app.route('/api/appointments/book', methods=['POST'])
@roles_required(ROLE_PATIENT)
def api_book_appointment():
    data        = request.get_json(silent=True) or {}
    provider_id = data.get('providerId')
    date_str    = data.get('date', '')
    time_str    = data.get('time', '')
    appt_type   = data.get('type', 'virtual')
    reason      = data.get('reason', '')

    if not provider_id or not date_str or not time_str:
        return jsonify({'error': 'providerId, date, and time are required'}), 400

    try:
        appt_dt = datetime.fromisoformat(f"{date_str[:10]}T{time_str}")
    except ValueError:
        return jsonify({'error': 'Invalid date/time format'}), 400

    room_id = f'room-{uuid.uuid4().hex[:8]}' if appt_type == 'virtual' else None
    appt = Appointment(
        patient_id=g.user.id, provider_id=int(provider_id),
        appointment_date=appt_dt, appt_type=appt_type,
        reason=reason, status='scheduled', video_room_id=room_id,
    )
    db.session.add(appt)
    db.session.commit()
    log_action('Appointment.book', f'Appt #{appt.id} on {appt_dt}')
    return jsonify(appt.to_dict()), 201


@app.route('/api/appointments', methods=['GET'])
@roles_required(ROLE_PATIENT, ROLE_DOCTOR)
def api_list_appointments():
    if g.user.role == ROLE_PATIENT:
        appts = Appointment.query.filter_by(patient_id=g.user.id)
    else:
        appts = Appointment.query.filter_by(provider_id=g.user.id)
    appts = appts.order_by(Appointment.appointment_date.asc()).all()
    return jsonify([a.to_dict() for a in appts])


@app.route('/api/appointments/<int:appt_id>', methods=['PATCH'])
@roles_required(ROLE_PATIENT, ROLE_DOCTOR)
def api_update_appointment(appt_id):
    appt = db.session.get(Appointment, appt_id)
    if not appt:
        return jsonify({'error': 'Not found'}), 404
    if g.user.id not in (appt.patient_id, appt.provider_id):
        return jsonify({'error': 'Forbidden'}), 403
    data = request.get_json(silent=True) or {}
    if 'status' in data and data['status'] in ('scheduled', 'completed', 'cancelled', 'no-show'):
        appt.status = data['status']
    db.session.commit()
    return jsonify(appt.to_dict())


# ══════════════════════════════════════════════════════════════════════════════
# MEDICATION ADHERENCE
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/adherence')
@roles_required(ROLE_PATIENT)
def adherence_tracking():
    return render_template('adherence_tracking.html', user=g.user)


@app.route('/api/medications/today', methods=['GET'])
@roles_required(ROLE_PATIENT)
def api_medications_today():
    today = datetime.utcnow().date()
    reminders = MedicationReminder.query.filter_by(
        patient_id=g.user.id, date=today).all()
    return jsonify([r.to_dict() for r in reminders])


@app.route('/api/medications/take', methods=['POST'])
@roles_required(ROLE_PATIENT)
def api_mark_taken():
    data   = request.get_json(silent=True) or {}
    med_id = data.get('medicationId')
    if not med_id:
        return jsonify({'error': 'medicationId required'}), 400
    reminder = db.session.get(MedicationReminder, med_id)
    if not reminder or reminder.patient_id != g.user.id:
        return jsonify({'error': 'Not found'}), 404
    reminder.taken    = True
    reminder.taken_at = datetime.utcnow()
    db.session.commit()
    return jsonify(reminder.to_dict())


@app.route('/api/medications/reminders', methods=['POST'])
@roles_required(ROLE_PATIENT)
def api_add_reminder():
    data = request.get_json(silent=True) or {}
    name = (data.get('medication_name') or '').strip()
    time_str = data.get('scheduled_time', '09:00')
    if not name:
        return jsonify({'error': 'medication_name required'}), 400
    from datetime import time as _time
    h, m = map(int, time_str.split(':'))
    reminder = MedicationReminder(
        patient_id=g.user.id,
        medication_name=name,
        dosage=data.get('dosage', ''),
        scheduled_time=_time(h, m),
        date=datetime.utcnow().date(),
    )
    db.session.add(reminder)
    db.session.commit()
    return jsonify(reminder.to_dict()), 201


# ══════════════════════════════════════════════════════════════════════════════
# PATIENT-REPORTED OUTCOMES (PROMs)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/proms')
@roles_required(ROLE_PATIENT)
def proms_questionnaire():
    return render_template('proms_questionnaire.html', user=g.user)


@app.route('/api/proms/submit', methods=['POST'])
@roles_required(ROLE_PATIENT)
def api_proms_submit():
    data      = request.get_json(silent=True) or {}
    responses = data.get('responses', {})
    if not responses:
        return jsonify({'error': 'responses required'}), 400
    score = sum(int(v) for v in responses.values()) / max(len(responses), 1)
    prom  = PromResponse(patient_id=g.user.id, responses=responses, total_score=round(score, 2))
    db.session.add(prom)
    db.session.commit()
    return jsonify(prom.to_dict()), 201


@app.route('/api/proms/history', methods=['GET'])
@roles_required(ROLE_PATIENT)
def api_proms_history():
    history = (PromResponse.query
               .filter_by(patient_id=g.user.id)
               .order_by(PromResponse.submitted_at.asc())
               .all())
    return jsonify({
        'dates':  [p.submitted_at.strftime('%Y-%m-%d') for p in history],
        'scores': [p.total_score for p in history],
        'raw':    [p.to_dict() for p in history],
    })


# ══════════════════════════════════════════════════════════════════════════════
# TELEHEALTH
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/telehealth/<room_id>')
@roles_required(ROLE_PATIENT, ROLE_DOCTOR)
def telehealth(room_id):
    return render_template('telehealth.html', user=g.user, room_id=room_id)


# ──────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)