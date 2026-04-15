# HR App FastAPI Backend

This project exposes authenticated API endpoints backed by a MySQL database.

## Setup

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
uvicorn app.main:app --reload
```

## Docker

Build and run with Docker Compose:

```powershell
docker compose up --build
```

The API will be available at `http://localhost:8000`.

Container defaults:

- MySQL 8.0 database stored in the `db_data` Docker volume
- API exposed on port `8000`
- Configured with environment variables from `docker-compose.yml`

To override secrets and token settings, create a local `.env` file based on `.env.example` before starting the stack.

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

If no token env vars are set, default admin token is `dev-token`.

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
