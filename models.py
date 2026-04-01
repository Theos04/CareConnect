from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(256), nullable=True) # Nullable for OAuth-only users
    google_id = db.Column(db.String(120), unique=True, nullable=True)
    role = db.Column(db.String(50), nullable=False, default='Patient', index=True)
    # Lab / clinic display name; optional for patients and doctors
    organization = db.Column(db.String(120), nullable=True)
    # False until role-specific onboarding is completed (new signups)
    onboarding_complete = db.Column(db.Boolean, nullable=False, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)


class FacilityType(db.Model):
    __tablename__ = 'facility_type'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)


class DoctorProfile(db.Model):
    __tablename__ = 'doctor_profile'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    medical_license = db.Column(db.String(80), nullable=False)
    specialty = db.Column(db.String(120), nullable=False)
    council = db.Column(db.String(120), nullable=True)
    facility_type_id = db.Column(db.Integer, db.ForeignKey('facility_type.id'), nullable=True)

    user = db.relationship('User', backref=db.backref('doctor_profile', uselist=False))
    facility_type = db.relationship('FacilityType')


class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(200), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    ip_address = db.Column(db.String(45))
    details = db.Column(db.Text)

    user = db.relationship('User', backref=db.backref('audit_logs', lazy=True))
