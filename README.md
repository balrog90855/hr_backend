# HR App FastAPI Backend

This project exposes authenticated API endpoints backed by a MySQL database.

## Setup

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Supported runtime baseline:

- Python `3.10`
- Dependency pins selected from versions that were already available by April 2025
- MySQL `8.0`

## Run

```powershell
uvicorn app.main:app --reload
```

## Bootstrap The First Admin

`POST /api/users` is admin-only. Create the first admin user with the bootstrap command instead of leaving public signup open.

Set these environment variables before running the command:

- `HR_APP_BOOTSTRAP_ADMIN_EMAIL`
- `HR_APP_BOOTSTRAP_ADMIN_PASSWORD`
- `HR_APP_BOOTSTRAP_ADMIN_FULL_NAME`
- `HR_APP_BOOTSTRAP_ADMIN_TEAM` (optional)
- `HR_APP_BOOTSTRAP_ADMIN_JOB_TITLE` (optional)

Run:

```powershell
python -m app.bootstrap_admin
```

The command is idempotent for an already-active admin with the same email. If the email already exists for a non-admin user, it fails so that privilege changes stay explicit.

## Container And OpenShift

The image is built from [hr_backend/Dockerfile](c:/Users/Joe_E/Documents/coding/HR_APP/hr_backend/Dockerfile). Application settings such as database credentials, JWT secrets, static admin tokens, and bootstrap admin values are not baked into the image. The backend reads them at runtime with `os.getenv(...)`, so they must be supplied by the OpenShift deployment.

In practice that means:

- BuildConfig or image build settings affect the image build only.
- Deployment, DeploymentConfig, Secret, and ConfigMap environment variables affect the running app.
- [hr_backend/.env.example](c:/Users/Joe_E/Documents/coding/HR_APP/hr_backend/.env.example) is only a template for the variable names. It is not loaded automatically inside the container.

Typical OpenShift pattern:

- Put secrets such as `DB_PASSWORD`, `HR_APP_JWT_SECRET`, and `HR_APP_ADMIN_TOKENS` in a Secret.
- Put non-secret values such as `DB_HOST`, `DB_PORT`, and `DB_NAME` in a ConfigMap or directly on the Deployment.
- Attach them to the running Deployment as environment variables.

Example manifests are provided under [hr_backend/openshift](c:/Users/Joe_E/Documents/coding/HR_APP/hr_backend/openshift):

- [hr_backend/openshift/configmap.yaml](c:/Users/Joe_E/Documents/coding/HR_APP/hr_backend/openshift/configmap.yaml)
- [hr_backend/openshift/secret.example.yaml](c:/Users/Joe_E/Documents/coding/HR_APP/hr_backend/openshift/secret.example.yaml)
- [hr_backend/openshift/deployment.yaml](c:/Users/Joe_E/Documents/coding/HR_APP/hr_backend/openshift/deployment.yaml)
- [hr_backend/openshift/service.yaml](c:/Users/Joe_E/Documents/coding/HR_APP/hr_backend/openshift/service.yaml)
- [hr_backend/openshift/bootstrap-admin-job.yaml](c:/Users/Joe_E/Documents/coding/HR_APP/hr_backend/openshift/bootstrap-admin-job.yaml)

Apply them after replacing the placeholder image reference and secret values:

```powershell
oc apply -f openshift/configmap.yaml
oc apply -f openshift/secret.example.yaml
oc apply -f openshift/deployment.yaml
oc apply -f openshift/service.yaml
```

To bootstrap the first admin in OpenShift, run the image as a one-off command or Job with the bootstrap env vars set and execute:

```powershell
python -m app.bootstrap_admin
```

If you use the provided Job manifest, apply it once after the API image is available:

```powershell
oc apply -f openshift/bootstrap-admin-job.yaml
```

Delete the Job after it succeeds so it is not re-run accidentally.

The Docker image installs Python packages from `wheelhouse/openshift-py310/` and does not contact PyPI during the build.

The API will be available at `http://localhost:8000`.

Container defaults:

- Python 3.10 base image
- API exposed on port `8000`
- Configured with environment variables supplied by the container platform at runtime

## Offline Deployment Notes

The backend is pinned to a Python 3.10-compatible dependency set intended for environments that cannot rely on the latest package releases.

For fully offline builds, pre-download or mirror the pinned wheels for your target platform before deployment. The checked-in `wheelhouse/` directory currently contains Windows and newer-Python artifacts, so it should not be treated as a ready-to-use Linux Python 3.10 package source.

For a Linux offline build target, prepare wheels for the versions in `requirements.txt` using a Python 3.10 environment on the target architecture, then install from that mirrored source during deployment.

An OpenShift-oriented wheel set is now available under `wheelhouse/openshift-py310/`.

Offline install example:

```powershell
pip install --no-index --find-links wheelhouse/openshift-py310 -r requirements.txt
```

This wheelhouse targets Linux `x86_64` with Python `3.10` and `manylinux2014`-compatible wheels, which aligns with common Red Hat OpenShift deployments.

For local development, you can still export variables from a local `.env` file or your shell, but OpenShift will not load `.env` automatically unless you explicitly mount or transform it into runtime environment variables.

## Project Structure

```
app/
  main.py          # FastAPI app, middleware, router registration
	database.py      # MySQL helpers and schema initialization
  schemas.py       # Pydantic request/response models
  security.py      # JWT, hashing, auth dependencies
  api/
    routes.py      # General: /health, /tables
    auth.py        # Auth: /auth/login, /token, /refresh, /logout
    employees.py   # Employees: /employees CRUD
    jobs.py        # Jobs: /jobs CRUD
    users.py       # Users: /users CRUD
```

## Endpoints

- `GET /api/health`
- `POST /api/auth/login`
- `POST /api/auth/token` (OAuth2 form endpoint for Swagger Docs)
- `POST /api/auth/refresh`
- `POST /api/auth/logout`
- `GET /api/tables`
- `GET /api/tables/{table_name}?limit=50&offset=0`
- `GET /api/jobs?limit=50&offset=0&vacant_only=true&search=manager`
- `GET /api/employees?limit=50&offset=0&status=active&team=Engineering&location=HQ&search=manager`
- `GET /api/employees/{employee_id}`
- `POST /api/employees`
- `PATCH /api/employees/{employee_id}`
- `DELETE /api/employees/{employee_id}`
- `GET /api/users?limit=50&offset=0&status=active&team=Engineering&email=@example.com&job_title=Engineer&search=joe`
- `GET /api/users/{user_id}`
- `POST /api/users`
- `PATCH /api/users/{user_id}`
- `DELETE /api/users/{user_id}`

All endpoints except `/api/health` require bearer token authentication.

Read endpoints accept either admin or read-only tokens.
Write endpoints (POST/PATCH/DELETE) require an admin token.

Use header:

- `Authorization: Bearer <token>`

## Employees And Jobs

Employee records now reference `jobs` by `job_number`.

- `job_title` is read from the `jobs` table.
- `POST /api/employees` should send `job_number` (not `job_title`).
- `PATCH /api/employees/{employee_id}` can send `job_number` and can also send `job_title` to update the related record in `jobs`.
- `jobs.is_vacant` is synchronized automatically when employees are created, reassigned, or deleted: `0` when a job has at least one assigned employee, `1` when no employee is assigned.

Create employee example:

```json
{
	"job_number": "ENG-001",
	"full_name": "Jane Doe",
	"team": "Engineering",
	"location": "HQ",
	"avatar_url": "https://example.com/avatar.jpg",
	"status": "active"
}
```

Patch employee example:

```json
{
	"job_number": "ENG-002",
	"team": "Platform",
	"status": "active"
}
```

List jobs example:

`GET /api/jobs?vacant_only=true`

Response rows include:

- `job_number`
- `job_title`
- `is_vacant` (`1` for vacant, `0` for occupied)

## Username/Password Login

`POST /api/auth/login` expects:

```json
{
	"username": "user@example.com",
	"password": "your-password"
}
```

Response includes:

- `access_token` (JWT bearer token)
- `access_token_expires_in` (seconds)
- `refresh_token`

Use refresh endpoint:

`POST /api/auth/refresh`

```json
{
	"refresh_token": "rt_..."
}
```

Refresh tokens are rotated on refresh.

## Authorize In Swagger Docs

Open `/docs`, click **Authorize**, then use the OAuth2 password flow.

- `username`: user email
- `password`: user password

Swagger calls `POST /api/auth/token` and stores the returned bearer access token automatically.

Token configuration:

- `HR_APP_ADMIN_TOKENS`: comma-separated admin tokens
- `HR_APP_READONLY_TOKENS`: comma-separated read-only tokens
- `HR_APP_API_TOKEN`: legacy single token; treated as admin for backward compatibility
- `HR_APP_JWT_SECRET`: signing secret for JWT access tokens (use 32+ chars)
- `HR_APP_ACCESS_TOKEN_MINUTES`: access token lifetime in minutes (default `30`)
- `HR_APP_REFRESH_TOKEN_DAYS`: refresh token lifetime in days (default `7`)


There is no default admin token fallback. For first-time setup, use `python -m app.bootstrap_admin` to create the initial admin user, then log in through the normal auth flow.

## Database Configuration

By default, the app connects to the MySQL service defined in `docker-compose.yml`.

Database environment variables:

- `DB_HOST`
- `DB_PORT`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `HR_APP_API_TOKEN`
- `HR_APP_ADMIN_TOKENS`
- `HR_APP_READONLY_TOKENS`
- `HR_APP_JWT_SECRET`
- `HR_APP_ACCESS_TOKEN_MINUTES`
- `HR_APP_REFRESH_TOKEN_DAYS`
- `HR_APP_BOOTSTRAP_ADMIN_EMAIL`
- `HR_APP_BOOTSTRAP_ADMIN_PASSWORD`
- `HR_APP_BOOTSTRAP_ADMIN_FULL_NAME`
- `HR_APP_BOOTSTRAP_ADMIN_TEAM`
- `HR_APP_BOOTSTRAP_ADMIN_JOB_TITLE`
