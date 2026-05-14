# Production Deployment

## Target Architecture
- Frontend: Railway or Vercel
- Backend: Railway
- Primary database: PostgreSQL
- Graph database: Neo4j Aura

## Backend Environment
- Copy `app/backend/.env.production.example` into Railway variables.
- Set `DATABASE_URL` to your managed PostgreSQL connection string.
- Set `CORS_ORIGINS` to your deployed frontend origin.
- Set `NEO4J_URI`, `NEO4J_USERNAME`, and `NEO4J_PASSWORD` from Neo4j Aura.

## Frontend Environment
- Copy `app/frontend/.env.production.example` into the frontend deployment variables.
- Set `VITE_API_BASE_URL` to your deployed backend URL plus `/api`.

## Important Notes
- Rotate every secret currently stored in `app/backend/.env` before any public deployment.
- Do not deploy the local SQLite file in production.
- Rebuild backend dependencies after adding `psycopg[binary]`.
