# CareConnect | Premium Healthcare Ecosystem

CareConnect is a modern, hyper-connected healthcare platform designed to unite patients, doctors, labs, and insurers into a single, transparent, and intelligent ecosystem.

Built with **Flask**, **SQLite**, **Tailwind CSS**, and **Authlib (Google OAuth 2.0)**, it provides a secure infrastructure for digital health management.

---

## 🏗️ Technical Stack
- **Backend**: Python / Flask
- **Database**: SQLite with Flask-SQLAlchemy & Flask-Migrate
- **Authentication**: Custom Email/Password + Google OAuth 2.0
- **Security**: Werkzeug hashing, Flask-Limiter (Rate Limiting), Flask-WTF (CSRF), and Marshmallow (Input Validation).
- **Frontend**: Vanilla HTML/JS with Tailwind CSS (CDN)
- **Monitoring**: Structured logging (RotatingFileHandler) and `/health` endpoint.

---

## 📂 File Directory & Breakdown

### 🛠️ Core Application Files
- **`app.py`**: Central logic, routes, and RBAC. Now includes rate limiting, CSRF protection, and audit logging.
- **`config.py`**: Centralized environment-specific configuration (`DevelopmentConfig`, `ProductionConfig`).
- **`models.py`**: Database schema with performance indexes and `AuditLog` for tracking security events.
- **`migrations/`**: Automatically generated folder for database version control (Alembic).
- **`requirements.txt`**: Project dependencies.
- **`.env`**: Stores sensitive keys and OAuth credentials.
- **`.env.example`**: Template for environment setup.

### 🎨 Static Assets
- **`static/css/style.css`**: Custom global styles (animations, custom utility classes).
- **`static/images/`**: UI assets and high-quality healthcare imagery.

### 📄 Templates (`/templates`)
- **`base.html`**: Master layout with dynamic navbar.
- **`landing.html`**: "Concept" page focal point.
- **`patients_info.html`** & **`providers_info.html`**: Targeted informational landing pages.
- **`getting-started.html`**: Sign-Up/Sign-In hub with CSRF protection.
- **`doctor_home.html`**, **`patient_prescriptions.html`**, **`pathology_lab_home.html`**: Specialized role dashboards.

---

## 🚀 Getting Started

1. **Install Dependencies**:
   ```bash
   py -m pip install -r requirements.txt
   ```

2. **Configure Environment**:
   - Create a `.env` file based on `.env.example`.
   - Add your Google OAuth credentials.

3. **Initialize Database & Migrations**:
   ```bash
   $env:FLASK_APP = "app.py"
   py -m flask db init
   py -m flask db migrate -m "Initial migration"
   py -m flask db upgrade
   ```

4. **Run Server**:
   ```bash
   py app.py
   ```

---

## 🔒 Security & Observability
- **Audit Logs**: Sensitive actions (Login, Register) are recorded in the `audit_log` table.
- **Rate Limiting**: Protects auth endpoints from brute-force attacks.
- **CSRF Protection**: Enabled globally via Flask-WTF.
- **Health Check**: Monitor system status at `/health`.
