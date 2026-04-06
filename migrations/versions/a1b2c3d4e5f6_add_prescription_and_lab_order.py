"""Add prescription and lab_order tables

Revision ID: a1b2c3d4e5f6
Revises: 6b73bb9a67f1
Create Date: 2026-04-04 00:00:00.000000

Zero-downtime strategy:
  - New tables are additive — no existing columns are dropped or renamed.
  - Run `flask db upgrade` while the app is live; old code still works
    because it never references these tables.
  - Deploy new code after upgrade completes.
"""
from alembic import op
import sqlalchemy as sa


revision      = 'a1b2c3d4e5f6'
down_revision = '6b73bb9a67f1'
branch_labels = None
depends_on    = None


def upgrade():
    # ── prescription ──────────────────────────────────────────────────────────
    op.create_table(
        'prescription',
        sa.Column('id',            sa.Integer(),     nullable=False),
        sa.Column('doctor_id',     sa.Integer(),     nullable=False),
        sa.Column('patient_id',    sa.Integer(),     nullable=True),
        sa.Column('patient_name',  sa.String(120),   nullable=False),
        sa.Column('patient_email', sa.String(120),   nullable=True),
        sa.Column('medication',    sa.String(200),   nullable=False),
        sa.Column('dosage',        sa.String(200),   nullable=True),
        sa.Column('duration',      sa.String(100),   nullable=True),
        sa.Column('notes',         sa.Text(),        nullable=True),
        sa.Column('status',        sa.String(20),    nullable=False, server_default='Pending'),
        sa.Column('created_at',    sa.DateTime(),    nullable=False),
        sa.Column('updated_at',    sa.DateTime(),    nullable=False),
        sa.ForeignKeyConstraint(['doctor_id'],  ['user.id']),
        sa.ForeignKeyConstraint(['patient_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_rx_doctor_id',    'prescription', ['doctor_id'])
    op.create_index('ix_rx_patient_id',   'prescription', ['patient_id'])
    op.create_index('ix_rx_status',       'prescription', ['status'])
    op.create_index('ix_rx_created_at',   'prescription', ['created_at'])
    op.create_index('ix_rx_patient_email','prescription', ['patient_email'])

    # ── lab_order ─────────────────────────────────────────────────────────────
    op.create_table(
        'lab_order',
        sa.Column('id',           sa.Integer(),    nullable=False),
        sa.Column('order_ref',    sa.String(20),   nullable=False),
        sa.Column('doctor_id',    sa.Integer(),    nullable=False),
        sa.Column('patient_name', sa.String(120),  nullable=False),
        sa.Column('test',         sa.String(200),  nullable=False),
        sa.Column('priority',     sa.String(20),   nullable=False, server_default='Routine'),
        sa.Column('status',       sa.String(40),   nullable=False, server_default='Sample received'),
        sa.Column('notes',        sa.Text(),       nullable=True),
        sa.Column('ordered_at',   sa.DateTime(),   nullable=False),
        sa.Column('updated_at',   sa.DateTime(),   nullable=False),
        sa.ForeignKeyConstraint(['doctor_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_ref'),
    )
    op.create_index('ix_lab_doctor_id',    'lab_order', ['doctor_id'])
    op.create_index('ix_lab_patient_name', 'lab_order', ['patient_name'])
    op.create_index('ix_lab_status',       'lab_order', ['status'])
    op.create_index('ix_lab_ordered_at',   'lab_order', ['ordered_at'])

    # ── conversation ──────────────────────────────────────────────────────────
    op.create_table(
        'conversation',
        sa.Column('id',          sa.Integer(),  nullable=False),
        sa.Column('patient_id',  sa.Integer(),  nullable=False),
        sa.Column('provider_id', sa.Integer(),  nullable=False),
        sa.Column('created_at',  sa.DateTime(), nullable=True),
        sa.Column('updated_at',  sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['patient_id'],  ['user.id']),
        sa.ForeignKeyConstraint(['provider_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_conv_patient_id',  'conversation', ['patient_id'])
    op.create_index('ix_conv_provider_id', 'conversation', ['provider_id'])

    # ── message ───────────────────────────────────────────────────────────────
    op.create_table(
        'message',
        sa.Column('id',              sa.Integer(),    nullable=False),
        sa.Column('conversation_id', sa.Integer(),    nullable=False),
        sa.Column('sender_id',       sa.Integer(),    nullable=False),
        sa.Column('sender_role',     sa.String(20),   nullable=False),
        sa.Column('content',         sa.Text(),       nullable=False),
        sa.Column('read',            sa.Boolean(),    nullable=False, server_default='0'),
        sa.Column('timestamp',       sa.DateTime(),   nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversation.id']),
        sa.ForeignKeyConstraint(['sender_id'],       ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_msg_conversation_id', 'message', ['conversation_id'])
    op.create_index('ix_msg_timestamp',       'message', ['timestamp'])

    # ── appointment ───────────────────────────────────────────────────────────
    op.create_table(
        'appointment',
        sa.Column('id',               sa.Integer(),    nullable=False),
        sa.Column('patient_id',       sa.Integer(),    nullable=False),
        sa.Column('provider_id',      sa.Integer(),    nullable=False),
        sa.Column('appointment_date', sa.DateTime(),   nullable=False),
        sa.Column('appt_type',        sa.String(20),   nullable=False, server_default='virtual'),
        sa.Column('reason',           sa.Text(),       nullable=True),
        sa.Column('status',           sa.String(20),   nullable=False, server_default='scheduled'),
        sa.Column('video_room_id',    sa.String(100),  nullable=True),
        sa.Column('created_at',       sa.DateTime(),   nullable=True),
        sa.ForeignKeyConstraint(['patient_id'],  ['user.id']),
        sa.ForeignKeyConstraint(['provider_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_appt_patient_id',  'appointment', ['patient_id'])
    op.create_index('ix_appt_provider_id', 'appointment', ['provider_id'])
    op.create_index('ix_appt_date',        'appointment', ['appointment_date'])
    op.create_index('ix_appt_status',      'appointment', ['status'])

    # ── medication_reminder ───────────────────────────────────────────────────
    op.create_table(
        'medication_reminder',
        sa.Column('id',              sa.Integer(),    nullable=False),
        sa.Column('patient_id',      sa.Integer(),    nullable=False),
        sa.Column('prescription_id', sa.Integer(),    nullable=True),
        sa.Column('medication_name', sa.String(200),  nullable=False),
        sa.Column('dosage',          sa.String(100),  nullable=True),
        sa.Column('scheduled_time',  sa.Time(),       nullable=False),
        sa.Column('taken',           sa.Boolean(),    nullable=False, server_default='0'),
        sa.Column('taken_at',        sa.DateTime(),   nullable=True),
        sa.Column('date',            sa.Date(),       nullable=False),
        sa.ForeignKeyConstraint(['patient_id'],      ['user.id']),
        sa.ForeignKeyConstraint(['prescription_id'], ['prescription.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_reminder_patient_date', 'medication_reminder', ['patient_id', 'date'])

    # ── prom_response ─────────────────────────────────────────────────────────
    op.create_table(
        'prom_response',
        sa.Column('id',           sa.Integer(),  nullable=False),
        sa.Column('patient_id',   sa.Integer(),  nullable=False),
        sa.Column('responses',    sa.JSON(),     nullable=False),
        sa.Column('total_score',  sa.Float(),    nullable=True),
        sa.Column('submitted_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['patient_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_prom_patient_date', 'prom_response', ['patient_id', 'submitted_at'])


def downgrade():
    op.drop_table('prom_response')
    op.drop_table('medication_reminder')
    op.drop_table('appointment')
    op.drop_table('message')
    op.drop_table('conversation')
    op.drop_table('lab_order')
    op.drop_table('prescription')
