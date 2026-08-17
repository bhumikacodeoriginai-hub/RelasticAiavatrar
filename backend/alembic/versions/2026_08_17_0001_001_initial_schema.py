"""Initial schema - all tables from ORM models

Revision ID: 001
Revises: None
Create Date: 2026-08-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === Roles table ===
    op.create_table('roles',
        sa.Column('role_id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(50), unique=True, nullable=False),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('permissions', sa.JSON(), nullable=True),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_roles_name', 'roles', ['name'])

    # === Users table ===
    op.create_table('users',
        sa.Column('user_id', sa.String(36), primary_key=True),
        sa.Column('username', sa.String(100), unique=True, nullable=False),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('role_id', sa.String(36), sa.ForeignKey('roles.role_id'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('is_locked', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('locked_until', sa.DateTime(), nullable=True),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.Column('password_changed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_users_username', 'users', ['username'])
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_role', 'users', ['role_id'])
    op.create_index('idx_users_active', 'users', ['is_active'])

    # === Visitors table ===
    op.create_table('visitors',
        sa.Column('visitor_id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('company', sa.String(255), nullable=True),
        sa.Column('role', sa.String(255), nullable=True),
        sa.Column('profile_image_path', sa.String(512), nullable=True),
        sa.Column('face_embedding', sa.JSON(), nullable=True),
        sa.Column('consent_status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('consent_timestamp', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('first_seen', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
        sa.Column('visit_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_visitors_name', 'visitors', ['name'])
    op.create_index('idx_visitors_last_seen', 'visitors', ['last_seen'])
    op.create_index('idx_visitors_consent', 'visitors', ['consent_status'])

    # === Employees table ===
    op.create_table('employees',
        sa.Column('employee_id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('department', sa.String(255), nullable=True),
        sa.Column('designation', sa.String(255), nullable=True),
        sa.Column('office_location', sa.String(255), nullable=True),
        sa.Column('availability', sa.String(20), nullable=False, server_default='available'),
        sa.Column('face_embedding', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_employees_name', 'employees', ['name'])
    op.create_index('idx_employees_department', 'employees', ['department'])
    op.create_index('idx_employees_availability', 'employees', ['availability'])

    # === Appointments table ===
    op.create_table('appointments',
        sa.Column('appointment_id', sa.String(36), primary_key=True),
        sa.Column('visitor_id', sa.String(36), sa.ForeignKey('visitors.visitor_id', ondelete='SET NULL'), nullable=True),
        sa.Column('employee_id', sa.String(36), sa.ForeignKey('employees.employee_id'), nullable=False),
        sa.Column('appointment_time', sa.DateTime(), nullable=False),
        sa.Column('purpose', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='scheduled'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_appointments_visitor', 'appointments', ['visitor_id'])
    op.create_index('idx_appointments_employee', 'appointments', ['employee_id'])
    op.create_index('idx_appointments_time', 'appointments', ['appointment_time'])
    op.create_index('idx_appointments_status', 'appointments', ['status'])

    # === Visits table ===
    op.create_table('visits',
        sa.Column('visit_id', sa.String(36), primary_key=True),
        sa.Column('visitor_id', sa.String(36), sa.ForeignKey('visitors.visitor_id', ondelete='CASCADE'), nullable=False),
        sa.Column('employee_id', sa.String(36), sa.ForeignKey('employees.employee_id'), nullable=True),
        sa.Column('arrival_time', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('departure_time', sa.DateTime(), nullable=True),
        sa.Column('purpose', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='arrived'),
        sa.Column('conversation_id', sa.String(36), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_visits_visitor_id', 'visits', ['visitor_id'])
    op.create_index('idx_visits_arrival', 'visits', ['arrival_time'])
    op.create_index('idx_visits_status', 'visits', ['status'])

    # === Conversations table ===
    op.create_table('conversations',
        sa.Column('conversation_id', sa.String(36), primary_key=True),
        sa.Column('visitor_id', sa.String(36), sa.ForeignKey('visitors.visitor_id', ondelete='SET NULL'), nullable=True),
        sa.Column('session_id', sa.String(255), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_conversations_visitor', 'conversations', ['visitor_id'])
    op.create_index('idx_conversations_session', 'conversations', ['session_id'])

    # === Conversation Messages table ===
    op.create_table('conversation_messages',
        sa.Column('message_id', sa.String(36), primary_key=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('conversations.conversation_id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_messages_conversation', 'conversation_messages', ['conversation_id'])

    # === Notifications table ===
    op.create_table('notifications',
        sa.Column('notification_id', sa.String(36), primary_key=True),
        sa.Column('employee_id', sa.String(36), sa.ForeignKey('employees.employee_id'), nullable=False),
        sa.Column('visitor_id', sa.String(36), sa.ForeignKey('visitors.visitor_id', ondelete='SET NULL'), nullable=True),
        sa.Column('notification_type', sa.String(30), nullable=False, server_default='visitor_arrived'),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_notifications_employee', 'notifications', ['employee_id'])
    op.create_index('idx_notifications_read', 'notifications', ['is_read'])

    # === Audit Logs table ===
    op.create_table('audit_logs',
        sa.Column('log_id', sa.String(36), primary_key=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', sa.String(36), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('performed_by', sa.String(255), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_audit_action', 'audit_logs', ['action'])
    op.create_index('idx_audit_entity', 'audit_logs', ['entity_type', 'entity_id'])
    op.create_index('idx_audit_created', 'audit_logs', ['created_at'])


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('notifications')
    op.drop_table('conversation_messages')
    op.drop_table('conversations')
    op.drop_table('visits')
    op.drop_table('appointments')
    op.drop_table('employees')
    op.drop_table('visitors')
    op.drop_table('users')
    op.drop_table('roles')
