# Insighta API — Backend

The core FastAPI + PostgreSQL backend for the Insighta Labs Intelligence Query Engine (Stage 3).

---

## Live Demo

- **API:** https://your-app.onrender.com
- **Web Portal:** https://your-app.onrender.com/web/login.html
- **API Docs:** https://your-app.onrender.com/docs

---

## Related Repositories

- [insighta-cli](https://github.com/Ashbel11/insighta-cli) — Python CLI tool
- [insighta-web](https://github.com/Ashbel11/insighta-web) — Web portal source

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Clients                          │
│         CLI (insighta)    Web Portal                │
└────────────────┬──────────────┬────────────────────┘
                 │              │
                 ▼              ▼
┌─────────────────────────────────────────────────────┐
│              FastAPI Backend (Stage 3)              │
│                                                     │
│  /auth/*          GitHub OAuth + PKCE + JWT         │
│  /api/profiles    Filtering, Sorting, Pagination    │
│  /api/profiles/search   Natural Language Query      │
│  /api/profiles/export   CSV Export                  │
│  /web/*           Static web portal                 │
│                                                     │
│  Middleware: Version Check | Rate Limit | Logging   │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│              PostgreSQL Database                    │
│   profiles | users | refresh_tokens                 │
└─────────────────────────────────────────────────────┘
```

---

## Auth Flow (GitHub OAuth + PKCE)

### Browser Flow
1. User visits `/web/login.html` and clicks **Login with GitHub**
2. Portal generates `code_verifier` and `code_challenge` (S256)
3. Backend redirects to GitHub OAuth page
4. GitHub redirects back to `/web/auth/callback`
5. Backend issues `access_token` (3 min) + `refresh_token` (5 min)
6. Tokens stored in HTTP-only cookies

### CLI Flow
1. User runs `insighta login`
2. CLI generates PKCE values and starts local server on `localhost:8788`
3. Browser opens GitHub OAuth page
4. GitHub redirects to `localhost:8788/callback`
5. CLI exchanges code for tokens and stores them locally

### Token Rotation
- Access token: **3 minutes**
- Refresh token: **5 minutes**
- Old token invalidated on every refresh

---

## Role Logic

| Role | Permissions |
|---|---|
| `admin` | Read + Create profiles, Export |
| `analyst` | Read only |

- First user to log in is automatically assigned `admin`
- All subsequent users get `analyst`

---

## API Endpoints

### Auth

| Method | Endpoint | Description |
|---|---|---|
| GET | `/auth/github` | Initiate GitHub OAuth |
| GET | `/auth/github/callback` | GitHub OAuth callback |
| POST | `/auth/refresh` | Rotate refresh token |
| POST | `/auth/logout` | Invalidate refresh token |

### Profiles

All profile endpoints require:
```
Authorization: Bearer <access_token>
X-API-Version: 3
```

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/api/profiles` | analyst + admin | List with filters |
| GET | `/api/profiles/search` | analyst + admin | Natural language search |
| GET | `/api/profiles/{id}` | analyst + admin | Get single profile |
| GET | `/api/profiles/export?format=csv` | analyst + admin | Export CSV |
| POST | `/api/profiles` | admin only | Create profile |

---

## Query Parameters — `GET /api/profiles`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `gender` | string | — | `male` or `female` |
| `age_group` | string | — | `child`, `teenager`, `adult`, `senior` |
| `country_id` | string | — | ISO 3166-1 alpha-2 (e.g. `NG`) |
| `min_age` | int | — | Minimum age |
| `max_age` | int | — | Maximum age |
| `sort_by` | string | `created_at` | `age`, `created_at`, `gender_probability` |
| `order` | string | `asc` | `asc` or `desc` |
| `page` | int | `1` | Page number |
| `limit` | int | `10` | Results per page (max 50) |

---

## Pagination Response Format

```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 100,
  "total_pages": 10,
  "links": {
    "first": "/api/profiles?page=1&limit=10",
    "last": "/api/profiles?page=10&limit=10",
    "prev": null,
    "next": "/api/profiles?page=2&limit=10"
  },
  "data": [...]
}
```

---

## Rate Limits

| Endpoint | Limit |
|---|---|
| `/auth/github` | 20 req / 60s |
| `/auth/refresh` | 10 req / 60s |
| `/api/profiles` | 60 req / 60s |
| `/api/profiles/search` | 30 req / 60s |

---

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env

# Seed the database
python seed.py profiles_seed.json

# Run the server
uvicorn main:app --reload
```

Visit `http://localhost:8000/docs` for the interactive API docs.

---

## Environment Variables

```env
DATABASE_URL=postgresql://...
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
GITHUB_REDIRECT_URI=http://localhost:8000/auth/github/callback
GITHUB_REDIRECT_URI_WEB=http://localhost:8000/web/auth/callback
JWT_SECRET=...
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=3
REFRESH_TOKEN_EXPIRE_MINUTES=5
FRONTEND_URL=http://localhost:3000
ENVIRONMENT=development
```

---

## Deployment (Render)

1. Create PostgreSQL database on Render
2. Create Web Service pointing to this repo
3. Set all environment variables in Render dashboard
4. Set Start Command: `bash start.sh`
5. Add production callback URLs to your GitHub OAuth App

---

## Database Schema

```sql
CREATE TABLE profiles (
    id                  UUID PRIMARY KEY,
    name                VARCHAR UNIQUE NOT NULL,
    gender              VARCHAR NOT NULL,
    gender_probability  FLOAT NOT NULL,
    age                 INT NOT NULL,
    age_group           VARCHAR NOT NULL,
    country_id          VARCHAR(2) NOT NULL,
    country_name        VARCHAR NOT NULL,
    country_probability FLOAT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL
);

CREATE TABLE users (
    id              UUID PRIMARY KEY,
    github_id       VARCHAR UNIQUE NOT NULL,
    username        VARCHAR NOT NULL,
    email           VARCHAR,
    avatar_url      VARCHAR,
    role            VARCHAR NOT NULL DEFAULT 'analyst',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL
);

CREATE TABLE refresh_tokens (
    id          UUID PRIMARY KEY,
    token       VARCHAR UNIQUE NOT NULL,
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL
);
```

---

## Error Format

```json
{ "status": "error", "message": "<description>" }
```

| Code | Meaning |
|---|---|
| 400 | Missing/invalid parameter |
| 401 | Missing or invalid token |
| 403 | Insufficient role |
| 404 | Resource not found |
| 409 | Conflict (duplicate) |
| 422 | Invalid parameter type |
| 429 | Rate limit exceeded |
| 500 | Internal server error |