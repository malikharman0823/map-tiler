# map-tiler

FastAPI and React/Vite map tiling workspace.

The backend uses temporary session repositories rather than a persistent
database. Session manifests and generated files live under
`backend/temp/sessions/` and are removed when a session ends or expires.

## How to Run

### Backend

1. Navigate to the `backend` directory:
   ```powershell
   cd backend
   ```
2. Create a Python virtual environment:
   ```powershell
   py -m venv .venv
   ```
3. Install dependencies:
   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
4. Start the API:
   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```

Runtime limits and cleanup intervals can be configured through `.env.local`;
see `.env.example` for the supported settings.

### Frontend

1. Navigate to the `frontend` directory:
   ```powershell
   cd frontend
   ```
2. Install dependencies:
   ```powershell
   npm install
   ```
3. Start the development server:
   ```powershell
   npm run dev
   ```
