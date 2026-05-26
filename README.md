# Financial Document RAG

A document management system using Retrieval-Augmented Generation (RAG) for semantic search, automated insights, and role-based access control across financial audits and reports.

## Features
- **Semantic Search (RAG):** Query financial datasets and get context-aware answers.
- **Role-Based Access Control (RBAC):** Granular permissions for Admins, Analysts, Auditors, and Clients.
- **Document Management:** Upload, parse, and manage financial spread sheets and contracts.
- **Secure Authentication:** JWT-based user sessions and hashed passwords.

## Tech Stack
- **Backend:** FastAPI, SQLAlchemy, SQLite, Qdrant (Vector DB), Sentence Transformers
- **Frontend:** HTML, CSS, Vanilla JavaScript

## Setup Instructions

### 1. Backend

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Seed the database with default roles, users, and documents:
   ```bash
   python3 seed.py
   ```
5. Start the backend server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

### 2. Frontend

1. Open a new terminal and navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Start a local server:
   ```bash
   python3 -m http.server 3000
   ```
3. Open `http://localhost:3000` in your browser.

## Default Accounts
If you ran `seed.py`, you can log in with:
- **Admin:** `admin` / `adminpassword`
- **Client:** `client` / `clientpassword`
