# Cloud-Based Bus Pass System

A responsive Flask/MySQL-ready bus-pass demo for passengers, administrators, and conductors. **Payments are simulated only**; this project never processes money or stores card details.

## Architecture

```text
Browser (Bootstrap 5) -> Flask app / Gunicorn -> SQLAlchemy -> SQLite locally or MySQL / Cloud SQL
                                      |-> session auth + CSRF protection
                                      |-> server fare lookup, approvals, demo payments, QR verification
```

The Flask app is created by `app.create_app()`. Models are in `app/models.py`; routes, access checks and CLI commands are in `app/__init__.py`. Cloud Run can scale app instances with demand, but Cloud SQL connection limits, database capacity, quotas and cost must be configured too. QR codes contain a random token; validity is always checked server-side.

## Database schema

`init-db` creates normalized SQLAlchemy tables: `user` (users), `bus_routes`, `pass_types`, `fare_rules`, `pass_applications`, `bus_passes`, `payments`, `verification_logs`, and `notifications`. The model definitions include foreign keys, unique constraints, status fields, timestamps and indexes. The migration-friendly SQL reference is `schema.sql`.

## Local setup (Windows PowerShell)

```powershell
cd cloud-based-bus-pass-system
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and set SECRET_KEY to a unique random value.
$env:FLASK_APP = "app.py"
flask init-db
flask create-user   # create admin, verifier, or passenger interactively
python app.py
```

Open http://127.0.0.1:5000. On Linux/macOS, use `python3 -m venv .venv`, `source .venv/bin/activate`, `export FLASK_APP=app.py`, then the same pip/Flask commands. Passenger accounts can also be created using Register. Create demo admin/verifier accounts interactively with `flask create-user`; no credentials are hardcoded.

Sample catalogue seeded by `init-db`: route R-01, Central Station to University Campus; student/general/employee monthly (30 days) and quarterly (90 days) passes; demo fares ₹450 and ₹1200 respectively. Change these in Admin.

## Workflow

1. Register as a passenger and log in.
2. Apply for a route/pass; the fare is resolved from the database.
3. An administrator approves or rejects the application. Approved applications can proceed to the clearly labelled payment demo.
4. Choose simulated success or failure. Only successful payment after approval creates and activates a digital pass. The QR token is random and verified by an authorized conductor at `/verify`.
5. Admin manages applications, routes and fares from `/admin`; accounts are created through the Flask CLI.

## Docker

```powershell
$env:SECRET_KEY = "use-a-unique-local-secret"
docker compose up --build
```

Open http://localhost:8080. The compose file starts a local MySQL database. Initialize it and create your first account with `docker compose exec web flask --app app.py init-db` and `docker compose exec web flask --app app.py create-user`. Compose credentials are for local development only.

## Google Cloud deployment outline

1. Create a Google Cloud project, enable billing, Cloud Run, Artifact Registry and Cloud SQL Admin APIs.
2. Create a Cloud SQL MySQL instance and database/user with a strong secret. Enable automated backups and point-in-time recovery as appropriate.
3. Create an Artifact Registry Docker repository and build/push this container (`gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/REPO/bus-pass`).
4. Deploy to Cloud Run with the Cloud SQL instance attached, a dedicated service account, `DATABASE_URL` secret, `SECRET_KEY` secret, and a bounded max instance count appropriate to database connection limits. Require HTTPS (Cloud Run URL).
5. Initialize schema and create admin/verifier users with a controlled one-off task using the same image and Cloud SQL connection. Never place secrets in source or image.
6. Check `/health`, Cloud Run logs, Cloud SQL metrics and backups. Set alerts for errors, latency, CPU, storage and connection saturation. Test restore procedures.

Cloud Run can add application instances automatically; each instance can consume database connections. Select SQLAlchemy pool size/overflow and Cloud Run max instances together with Cloud SQL capacity. Load-test in a staging project, increase concurrency gradually, observe p95 latency and connection counts, and set budgets/quotas before production. Do not store uploads, sessions, or durable data on the container filesystem.

## GitHub

Create a private/public repository, then run `git init`, `git add .`, `git commit -m "Build bus pass system"`, `git branch -M main`, `git remote add origin <repository-url>`, and `git push -u origin main`. Keep `.env`, database files and secrets out of Git.

## Checks and limitations

Run `pytest`. The included smoke tests cover health, registration, role protection, and fare/payment/pass workflow. They are not a full security audit or load test. For basic concurrent load validation, use a staging deployment and a load tool such as Locust or k6; document virtual users, duration, error rate, p95 latency and DB connection usage. No claim of production readiness should be inferred from smoke tests. Document uploads, user profile editing/cancellation, detailed paginated search, renewal flow, email reminders, payment-provider integration, and automated monitoring are not implemented in this demo. Admin actions and verification are recorded in verification logs where applicable; a separate comprehensive admin audit log is future work.

## Troubleshooting

- `SECRET_KEY` warning: replace the development example with a random secret before deployment.
- MySQL connection error: check `DATABASE_URL`, network/Cloud SQL attachment, user privileges and database availability.
- CSRF error: submit forms from the application page and do not reuse expired forms.
- No fares displayed: run `flask init-db` and check active route/fare records in Admin.
- Pass not issued: application must be approved and the demo payment must succeed.
- QR invalid: submit the complete token from the QR; revoked and expired passes cannot validate.
