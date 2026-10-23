# Online Attendance Management System

Starter implementation for Sankar Matriculation School, Sankagiri West, Namakkal District, Tamil Nadu.

## Features
- Role-based login (administrator and teacher)
- Administrator can create teacher accounts, classes/sections, and student records
- Teachers and administrators can mark attendance as Present, Absent, or On Leave
- One attendance record per student per date; later saves update the existing record
- Search and filter student lists
- Date-range attendance reports and attendance percentage
- Responsive Bootstrap interface
- SQLite locally; PostgreSQL through `DATABASE_URL` in production

## 1. Run locally on Windows

Open this folder in VS Code, then in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
$env:SECRET_KEY = "use-a-long-random-development-secret"
$env:ADMIN_USERNAME = "schooladmin"
$env:ADMIN_PASSWORD = "Choose-A-Unique-Password-123!"
flask --app app create-admin
python app.py
```

Open http://127.0.0.1:5000 and sign in using the administrator username/password you configured.

If PowerShell blocks virtual environment activation, run this in the current terminal only, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## 2. Deploy to Vercel

1. Push this project to a GitHub repository.
2. Create a PostgreSQL database with a provider whose current free plan meets your needs.
3. Copy its connection string. Ensure it is a PostgreSQL URI and supports TLS as required by that provider.
4. Import the GitHub repository into Vercel.
5. Configure Vercel environment variables:
   - `SECRET_KEY`: a long, random secret value
   - `DATABASE_URL`: production PostgreSQL connection string
6. Deploy.

### Initialize production database and administrator

The application creates tables on startup. Do **not** put a default administrator password in source code. For first-time production setup, run the `flask --app app create-admin` command in a trusted environment with the production `DATABASE_URL`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD` set, then remove/unset the one-time admin password environment variable. If you cannot run a one-time command against the production database, use a trusted local environment configured with the production connection string and run the same command there. Never commit the `.env` file or share the credentials.

Vercel's serverless runtime is not a persistent server, and local filesystem writes are not a durable database. Always configure `DATABASE_URL` for deployment; do not rely on the local SQLite file in production.

## Important notes before real school use
- This is a project starter, not yet a production security audit.
- Add CSRF protection, login rate limiting, secure cookie settings, database backup/restore, audit logs, and a school-approved account provisioning/reset procedure before using real student records.
- Current report percentage is Present / all attendance records (including On Leave). Confirm the school's preferred policy before finalizing.
- The initial implementation lets both admins and teachers mark attendance for any class. Add teacher-to-class assignments and enforce them if required by the school.
- Review free-tier limits, data retention, and regional/data-protection needs of the selected hosting and database providers.
