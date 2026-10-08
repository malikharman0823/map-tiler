# map-tiler

FastAPI and React/Vite map tiling workspace.

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
