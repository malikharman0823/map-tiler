# MapTiler Clone Backend

FastAPI geospatial-processing backend with temporary, session-scoped storage.
There is no persistent application database. Each session keeps its metadata in
memory and JSON manifests, while uploads, tiles, intermediates, and exports live
under `backend/temp/sessions/` until the session expires or is ended.

## Local setup

1. Create and activate a Python virtual environment, then install dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. Start the API from this directory:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```

3. Open `http://127.0.0.1:8000/health`.

Session lifetime, upload limits, and cleanup intervals are configured in
`config.py` and may be overridden through `.env.local`.
