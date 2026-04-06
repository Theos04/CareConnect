from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import datetime

db = SQLAlchemy()

# ─────────────────────────────────────────────────────────────────────────────
# USER
# ─────────────────────────────────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = 'user'

    id               = db.Column(db.Integer, primary_key=True)
    email            = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name             = db.Column(db.String(100), nullable=False)
    password_hash    = db.Column(db.String(256), nullable=True)
    google_id        = db.Column(db.String(120), unique=True, nullable=True)
    role             = db.Column(db.String(50),  nullable=False, default='Patient', index=True)
    organization     = db.Column(db.String(120), nullable=True)
    onboarding_complete = db.Column(db.Boolean, nullable=False, default=True)

    # relationships (back-populated by child models)
    prescriptions_as_doctor  = db.relationship(
        'Prescription', foreign_keys='Prescription.doctor_id',
        backref=db.backref('doctor', lazy='joined'), lazy='dynamic'
    )
    prescriptions_as_patient = db.relationship(
        'Prescription', foreign_keys='Prescription.patient_id',
        backref=db.backref('patient', lazy='joined'), lazy='dynamic'
    )
    lab_orders_issued = db.relationship(
        'LabOrder', foreign_keys='LabOrder.doctor_id',
        backref=db.backref('doctor', lazy='joined'), lazy='dynamic'
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email} [{self.role}]>'


# ─────────────────────────────────────────────────────────────────────────────
# FACILITY TYPE
# ─────────────────────────────────────────────────────────────────────────────
class FacilityType(db.Model):
    __tablename__ = 'facility_type'

    id   = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)


# ─────────────────────────────────────────────────────────────────────────────
# DOCTOR PROFILE
# ─────────────────────────────────────────────────────────────────────────────
class DoctorProfile(db.Model):
    __tablename__ = 'doctor_profile'

    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    medical_license  = db.Column(db.String(80),  nullable=False)
    specialty        = db.Column(db.String(120), nullable=False)
    council          = db.Column(db.String(120), nullable=True)
    facility_type_id = db.Column(db.Integer, db.ForeignKey('facility_type.id'), nullable=True)

    user          = db.relationship('User', backref=db.backref('doctor_profile', uselist=False))
    facility_type = db.relationship('FacilityType')


# ─────────────────────────────────────────────────────────────────────────────
# PRESCRIPTION
# ─────────────────────────────────────────────────────────────────────────────
class Prescription(db.Model):
    __tablename__ = 'prescription'

    # Composite indexes for the two most common query patterns
    __table_args__ = (
        db.Index('ix_rx_doctor_id',  'doctor_id'),
        db.Index('ix_rx_patient_id', 'patient_id'),
        db.Index('ix_rx_status',     'status'),
        db.Index('ix_rx_created_at', 'created_at'),
    )

    id             = db.Column(db.Integer, primary_key=True)
    doctor_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    patient_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    # Denormalised patient name/email for cases where patient has no account
    patient_name   = db.Column(db.String(120), nullable=False)
    patient_email  = db.Column(db.String(120), nullable=True,  index=True)
    medication     = db.Column(db.String(200), nullable=False)
    dosage         = db.Column(db.String(200), nullable=True)
    duration       = db.Column(db.String(100), nullable=True)
    notes          = db.Column(db.Text,        nullable=True)
    status         = db.Column(
        db.String(20), nullable=False, default='Pending',
        # Pending | Filled | Completed | Cancelled
    )
    created_at     = db.Column(db.DateTime, nullable=False,
                               default=datetime.datetime.utcnow)
    updated_at     = db.Column(db.DateTime, nullable=False,
                               default=datetime.datetime.utcnow,
                               onupdate=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            'id':            self.id,
            'doctor_name':   self.doctor.name  if self.doctor  else '',
            'doctor_email':  self.doctor.email if self.doctor  else '',
            'patient_name':  self.patient_name,
            'patient_email': self.patient_email or '',
            'medication':    self.medication,
            'dosage':        self.dosage   or '',
            'duration':      self.duration or '',
            'notes':         self.notes    or '',
            'status':        self.status,
            'date':          self.created_at.strftime('%Y-%m-%d'),
        }

    def __repr__(self):
        return f'<Prescription #{self.id} {self.medication} [{self.status}]>'


# ─────────────────────────────────────────────────────────────────────────────
# LAB ORDER
# ─────────────────────────────────────────────────────────────────────────────
class LabOrder(db.Model):
    __tablename__ = 'lab_order'

    __table_args__ = (
        db.Index('ix_lab_doctor_id',    'doctor_id'),
        db.Index('ix_lab_patient_name', 'patient_name'),
        db.Index('ix_lab_status',       'status'),
        db.Index('ix_lab_ordered_at',   'ordered_at'),
    )

    id           = db.Column(db.Integer, primary_key=True)
    order_ref    = db.Column(db.String(20), unique=True, nullable=False)  # e.g. LAB-1001
    doctor_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    patient_name = db.Column(db.String(120), nullable=False)
    test         = db.Column(db.String(200), nullable=False)
    priority     = db.Column(db.String(20),  nullable=False, default='Routine')
    status       = db.Column(db.String(40),  nullable=False, default='Sample received')
    notes        = db.Column(db.Text,        nullable=True)
    ordered_at   = db.Column(db.DateTime, nullable=False,
                             default=datetime.datetime.utcnow)
    updated_at   = db.Column(db.DateTime, nullable=False,
                             default=datetime.datetime.utcnow,
                             onupdate=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            'id':           self.order_ref,
            'patient_name': self.patient_name,
            'test':         self.test,
            'priority':     self.priority,
            'status':       self.status,
            'ordered_at':   self.ordered_at.strftime('%Y-%m-%d'),
            'notes':        self.notes or '',
        }

    def __repr__(self):
        return f'<LabOrder {self.order_ref} [{self.status}]>'


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT LOG
# ─────────────────────────────────────────────────────────────────────────────
class AuditLog(db.Model):
    __tablename__ = 'audit_log'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action     = db.Column(db.String(200), nullable=False)
    timestamp  = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)
    ip_address = db.Column(db.String(45))
    details    = db.Column(db.Text)

    user = db.relationship('User', backref=db.backref('audit_logs', lazy=True))


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSATION & MESSAGE  (Secure Messaging)
# ─────────────────────────────────────────────────────────────────────────────
class Conversation(db.Model):
    __tablename__ = 'conversation'
    __table_args__ = (
        db.Index('ix_conv_patient_id',  'patient_id'),
        db.Index('ix_conv_provider_id', 'provider_id'),
    )

    id          = db.Column(db.Integer, primary_key=True)
    patient_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    provider_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.datetime.utcnow,
                            onupdate=datetime.datetime.utcnow)

    patient  = db.relationship('User', foreign_keys=[patient_id],
                               backref=db.backref('conversations_as_patient', lazy='dynamic'))
    provider = db.relationship('User', foreign_keys=[provider_id],
                               backref=db.backref('conversations_as_provider', lazy='dynamic'))
    messages = db.relationship('Message', backref='conversation',
                               lazy='dynamic', order_by='Message.timestamp')

    @property
    def unread_count_for_patient(self):
        return self.messages.filter_by(sender_role='provider', read=False).count()

    def last_message_dict(self):
        msg = self.messages.order_by(Message.timestamp.desc()).first()
        return {
            'text': msg.content[:60] if msg else '',
            'time': msg.timestamp.strftime('%H:%M') if msg else '',
        }


class Message(db.Model):
    __tablename__ = 'message'
    __table_args__ = (
        db.Index('ix_msg_conversation_id', 'conversation_id'),
        db.Index('ix_msg_timestamp',       'timestamp'),
    )

    id              = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    sender_id       = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sender_role     = db.Column(db.String(20), nullable=False)  # 'patient' | 'provider'
    content         = db.Column(db.Text, nullable=False)
    read            = db.Column(db.Boolean, default=False, nullable=False)
    timestamp       = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)

    sender = db.relationship('User', foreign_keys=[sender_id])

    def to_dict(self):
        return {
            'id':          self.id,
            'sender':      self.sender_role,
            'sender_name': self.sender.name if self.sender else '',
            'content':     self.content,
            'read':        self.read,
            'timestamp':   self.timestamp.isoformat(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# APPOINTMENT
# ─────────────────────────────────────────────────────────────────────────────
class Appointment(db.Model):
    __tablename__ = 'appointment'
    __table_args__ = (
        db.Index('ix_appt_patient_id',  'patient_id'),
        db.Index('ix_appt_provider_id', 'provider_id'),
        db.Index('ix_appt_date',        'appointment_date'),
        db.Index('ix_appt_status',      'status'),
    )

    id               = db.Column(db.Integer, primary_key=True)
    patient_id       = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    provider_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    appointment_date = db.Column(db.DateTime, nullable=False)
    appt_type        = db.Column(db.String(20), nullable=False, default='virtual')
    reason           = db.Column(db.Text, nullable=True)
    status           = db.Column(db.String(20), nullable=False, default='scheduled')
    video_room_id    = db.Column(db.String(100), nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    patient  = db.relationship('User', foreign_keys=[patient_id],
                               backref=db.backref('appointments_as_patient', lazy='dynamic'))
    provider = db.relationship('User', foreign_keys=[provider_id],
                               backref=db.backref('appointments_as_provider', lazy='dynamic'))

    def to_dict(self):
        return {
            'id':               self.id,
            'patient_name':     self.patient.name  if self.patient  else '',
            'provider_name':    self.provider.name if self.provider else '',
            'appointment_date': self.appointment_date.isoformat(),
            'type':             self.appt_type,
            'reason':           self.reason or '',
            'status':           self.status,
            'video_room_id':    self.video_room_id or '',
        }


# ─────────────────────────────────────────────────────────────────────────────
# MEDICATION REMINDER  (Adherence Tracking)
# ─────────────────────────────────────────────────────────────────────────────
class MedicationReminder(db.Model):
    __tablename__ = 'medication_reminder'
    __table_args__ = (
        db.Index('ix_reminder_patient_date', 'patient_id', 'date'),
    )

    id              = db.Column(db.Integer, primary_key=True)
    patient_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    prescription_id = db.Column(db.Integer, db.ForeignKey('prescription.id'), nullable=True)
    medication_name = db.Column(db.String(200), nullable=False)
    dosage          = db.Column(db.String(100), nullable=True)
    scheduled_time  = db.Column(db.Time, nullable=False)
    taken           = db.Column(db.Boolean, default=False, nullable=False)
    taken_at        = db.Column(db.DateTime, nullable=True)
    date            = db.Column(db.Date, nullable=False,
                                default=lambda: datetime.datetime.utcnow().date())

    patient      = db.relationship('User', backref=db.backref('reminders', lazy='dynamic'))
    prescription = db.relationship('Prescription', backref=db.backref('reminders', lazy='dynamic'))

    def to_dict(self):
        return {
            'id':              self.id,
            'medication_name': self.medication_name,
            'dosage':          self.dosage or '',
            'scheduled_time':  self.scheduled_time.strftime('%H:%M'),
            'taken':           self.taken,
            'taken_at':        self.taken_at.isoformat() if self.taken_at else None,
            'date':            self.date.isoformat(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# PROM RESPONSE  (Patient-Reported Outcome Measures)
# ─────────────────────────────────────────────────────────────────────────────
class PromResponse(db.Model):
    __tablename__ = 'prom_response'
    __table_args__ = (
        db.Index('ix_prom_patient_date', 'patient_id', 'submitted_at'),
    )

    id           = db.Column(db.Integer, primary_key=True)
    patient_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    responses    = db.Column(db.JSON, nullable=False)   # {question_id: value, ...}
    total_score  = db.Column(db.Float, nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)

    patient = db.relationship('User', backref=db.backref('prom_responses', lazy='dynamic'))

    def to_dict(self):
        return {
            'id':           self.id,
            'responses':    self.responses,
            'total_score':  self.total_score,
            'submitted_at': self.submitted_at.isoformat(),
        }
