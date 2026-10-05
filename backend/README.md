# MapTiler Clone Backend

FastAPI geospatial-processing backend using psycopg transactions against Supabase
Postgres. Prisma owns the database schema and migrations from the project root.

## Local setup

1. From the project root, replace `[YOUR-PASSWORD]` in `.env.local` with the
   Supabase database password. Keep this file local.
2. Install and validate the pinned Prisma tooling:

   ```powershell
   npm.cmd install
   npm.cmd run prisma:validate
   npm.cmd run prisma:generate
   ```

3. Apply the Prisma migrations only after confirming the target Supabase project:

   ```powershell
   npm.cmd run prisma:deploy
   ```

4. Create and activate a Python virtual environment, then install dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

5. Start the API from this directory:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```

6. Open `http://127.0.0.1:8000/health`.

The application does not mutate the schema during startup. Schema changes belong
in `prisma/schema.prisma` and `prisma/migrations`.
