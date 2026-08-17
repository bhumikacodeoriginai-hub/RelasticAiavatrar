-- ==============================================
-- AI Receptionist Database - MySQL Schema
-- ==============================================
-- This script initializes the MySQL database.
-- Tables are also managed via SQLAlchemy ORM,
-- but this provides the authoritative DDL.
-- ==============================================

CREATE DATABASE IF NOT EXISTS ai_receptionist
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE ai_receptionist;

-- Visitors table: stores all recognized visitors
CREATE TABLE IF NOT EXISTS visitors (
    visitor_id CHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NULL,
    phone VARCHAR(50) NULL,
    company VARCHAR(255) NULL,
    role VARCHAR(255) NULL,
    profile_image_path VARCHAR(512) NULL,
    face_embedding JSON NULL COMMENT '512-dimensional float array',
    consent_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    consent_timestamp DATETIME NULL,
    notes TEXT NULL,
    first_seen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen DATETIME NULL,
    visit_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_visitors_name (name),
    INDEX idx_visitors_last_seen (last_seen),
    INDEX idx_visitors_consent (consent_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Employees table: internal office employees
CREATE TABLE IF NOT EXISTS employees (
    employee_id CHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(50) NULL,
    department VARCHAR(255) NULL,
    designation VARCHAR(255) NULL,
    office_location VARCHAR(255) NULL,
    availability VARCHAR(20) NOT NULL DEFAULT 'available',
    face_embedding JSON NULL COMMENT '512-dimensional float array',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_employees_name (name),
    INDEX idx_employees_department (department),
    INDEX idx_employees_availability (availability)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Appointments table: scheduled meetings
CREATE TABLE IF NOT EXISTS appointments (
    appointment_id CHAR(36) PRIMARY KEY,
    visitor_id CHAR(36) NULL,
    employee_id CHAR(36) NOT NULL,
    appointment_time DATETIME NOT NULL,
    purpose TEXT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (visitor_id) REFERENCES visitors(visitor_id) ON DELETE SET NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    INDEX idx_appointments_visitor (visitor_id),
    INDEX idx_appointments_employee (employee_id),
    INDEX idx_appointments_time (appointment_time),
    INDEX idx_appointments_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Visits table: tracks each physical visit
CREATE TABLE IF NOT EXISTS visits (
    visit_id CHAR(36) PRIMARY KEY,
    visitor_id CHAR(36) NOT NULL,
    employee_id CHAR(36) NULL,
    arrival_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    departure_time DATETIME NULL,
    purpose TEXT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'arrived',
    conversation_id CHAR(36) NULL,
    notes TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (visitor_id) REFERENCES visitors(visitor_id) ON DELETE CASCADE,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    INDEX idx_visits_visitor_id (visitor_id),
    INDEX idx_visits_arrival (arrival_time),
    INDEX idx_visits_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Conversations table: stores conversation sessions
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id CHAR(36) PRIMARY KEY,
    visitor_id CHAR(36) NULL,
    session_id VARCHAR(255) NOT NULL,
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME NULL,
    summary TEXT NULL,
    message_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (visitor_id) REFERENCES visitors(visitor_id) ON DELETE SET NULL,
    INDEX idx_conversations_visitor (visitor_id),
    INDEX idx_conversations_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Conversation messages table
CREATE TABLE IF NOT EXISTS conversation_messages (
    message_id CHAR(36) PRIMARY KEY,
    conversation_id CHAR(36) NOT NULL,
    role VARCHAR(20) NOT NULL COMMENT 'user, assistant, system',
    content TEXT NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    INDEX idx_messages_conversation (conversation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Notifications table
CREATE TABLE IF NOT EXISTS notifications (
    notification_id CHAR(36) PRIMARY KEY,
    employee_id CHAR(36) NOT NULL,
    visitor_id CHAR(36) NULL,
    notification_type VARCHAR(30) NOT NULL DEFAULT 'visitor_arrived',
    message TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    FOREIGN KEY (visitor_id) REFERENCES visitors(visitor_id) ON DELETE SET NULL,
    INDEX idx_notifications_employee (employee_id),
    INDEX idx_notifications_read (is_read)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Audit logs table
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id CHAR(36) PRIMARY KEY,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id CHAR(36) NULL,
    details TEXT NULL,
    performed_by VARCHAR(255) NULL,
    ip_address VARCHAR(45) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_action (action),
    INDEX idx_audit_entity (entity_type, entity_id),
    INDEX idx_audit_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==============================================
-- Seed data: Sample employees for Code Origin.AI
-- ==============================================

INSERT IGNORE INTO employees (employee_id, name, email, phone, department, designation, office_location, availability) VALUES
    (UUID(), 'Mr. Sharma', 'sharma@codeorigin.ai', '+91-9876543210', 'Management', 'Director', 'Room 101', 'available'),
    (UUID(), 'Priya Patel', 'priya@codeorigin.ai', '+91-9876543211', 'Engineering', 'Tech Lead', 'Room 205', 'available'),
    (UUID(), 'Arun Kumar', 'arun@codeorigin.ai', '+91-9876543212', 'Engineering', 'Senior Developer', 'Room 206', 'available'),
    (UUID(), 'Sneha Gupta', 'sneha@codeorigin.ai', '+91-9876543213', 'HR', 'HR Manager', 'Room 103', 'available'),
    (UUID(), 'Rajesh Mehta', 'rajesh@codeorigin.ai', '+91-9876543214', 'Sales', 'Sales Director', 'Room 301', 'available');
