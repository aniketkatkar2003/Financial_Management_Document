import os
import shutil
from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine, get_db, Base
from app.models import User, Role, Permission, Document, user_roles
from app.schemas import (
    UserRegister, UserOut, Token, RoleCreate, RoleOut, RoleAssign,
    UserRolesOut, UserPermissionsOut, DocumentOut, RAGSearchRequest,
    RAGSearchResponse, RAGContextResponse, RAGChunkResponse
)
from app.auth import get_password_hash, verify_password, create_access_token, get_current_user
from app.rbac import PermissionChecker, check_document_access, get_user_permissions
from app.rag import index_document_content, delete_document_content, search_semantic_chunks, generate_financial_insight, get_document_context_summary

app = FastAPI(
    title="Financial Document Management & Semantic Analysis API",
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_db_setup():
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        
        existing_permissions = db.query(Permission).all()
        if not existing_permissions:
            perms_dict = {
                "full_access": "Full administrator system access",
                "upload_document": "Ability to upload new financial documents",
                "edit_document": "Ability to edit document properties",
                "review_document": "Ability to review and audit documents",
                "view_document": "Ability to view and search documents"
            }
            for name, desc in perms_dict.items():
                db.add(Permission(name=name, description=desc))
            db.commit()

        
        existing_roles = db.query(Role).all()
        if not existing_roles:
            roles_dict = {
                "Admin": "System Administrator with unrestricted access",
                "Financial Analyst": "Analyst role for document operations",
                "Auditor": "Auditor role for document review and validation",
                "Client": "External client with access strictly bounded by company profile"
            }
            for name, desc in roles_dict.items():
                db.add(Role(name=name, description=desc))
            db.commit()

        
        admin_role = db.query(Role).filter(Role.name == "Admin").first()
        analyst_role = db.query(Role).filter(Role.name == "Financial Analyst").first()
        auditor_role = db.query(Role).filter(Role.name == "Auditor").first()
        client_role = db.query(Role).filter(Role.name == "Client").first()

        full_access_p = db.query(Permission).filter(Permission.name == "full_access").first()
        upload_p = db.query(Permission).filter(Permission.name == "upload_document").first()
        edit_p = db.query(Permission).filter(Permission.name == "edit_document").first()
        review_p = db.query(Permission).filter(Permission.name == "review_document").first()
        view_p = db.query(Permission).filter(Permission.name == "view_document").first()

        if admin_role and not admin_role.permissions:
            admin_role.permissions.append(full_access_p)
        if analyst_role and not analyst_role.permissions:
            analyst_role.permissions.extend([upload_p, edit_p, view_p])
        if auditor_role and not auditor_role.permissions:
            auditor_role.permissions.extend([review_p, view_p])
        if client_role and not client_role.permissions:
            client_role.permissions.append(view_p)

        db.commit()
    except Exception as e:
        print(f"Error seeding database: {e}")
    finally:
        db.close()


#  Authentication Endpoints 

@app.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    
    hashed_pwd = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_pwd,
        company_name=user_data.company_name
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    
    role_name = "Client"
    username_lower = user_data.username.lower()
    if "admin" in username_lower:
        role_name = "Admin"
    elif "analyst" in username_lower:
        role_name = "Financial Analyst"
    elif "auditor" in username_lower:
        role_name = "Auditor"

    default_role = db.query(Role).filter(Role.name == role_name).first()
    if default_role:
        new_user.roles.append(default_role)
        db.commit()

    return new_user

@app.post("/auth/login", response_model=Token)
def login(form_data: UserRegister, db: Session = Depends(get_db)):
    
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
        
    access_token = create_access_token(data={"sub": user.username, "user_id": user.id})
    return {"access_token": access_token, "token_type": "bearer"}


# Role & Permission Endpoints
@app.post("/roles/create", response_model=RoleOut)
def create_role(role_data: RoleCreate, db: Session = Depends(get_db), current_user: User = Depends(PermissionChecker("full_access"))):
    if db.query(Role).filter(Role.name == role_data.name).first():
        raise HTTPException(status_code=400, detail="Role already exists")
    new_role = Role(name=role_data.name, description=role_data.description)
    db.add(new_role)
    db.commit()
    db.refresh(new_role)
    return new_role

@app.post("/users/assign-role")
def assign_role(assignment: RoleAssign, db: Session = Depends(get_db), current_user: User = Depends(PermissionChecker("full_access"))):
    target_user = db.query(User).filter(User.id == assignment.user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    target_role = db.query(Role).filter(Role.name == assignment.role_name).first()
    if not target_role:
        raise HTTPException(status_code=404, detail="Role not found")
        
    if target_role not in target_user.roles:
        target_user.roles.append(target_role)
        db.commit()
    return {"message": f"Successfully assigned role {assignment.role_name} to user {target_user.username}"}

@app.get("/users/{id}/roles", response_model=UserRolesOut)
def get_user_roles(id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    target_user = db.query(User).filter(User.id == id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    
    if current_user.id != target_user.id and "admin" not in [r.name.lower() for r in current_user.roles]:
        raise HTTPException(status_code=403, detail="Unauthorized to view other users' roles")

    role_names = [role.name for role in target_user.roles]
    return {"user_id": target_user.id, "username": target_user.username, "roles": role_names}

@app.get("/users/{id}/permissions", response_model=UserPermissionsOut)
def get_user_permissions_endpoint(id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    target_user = db.query(User).filter(User.id == id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if current_user.id != target_user.id and "admin" not in [r.name.lower() for r in current_user.roles]:
        raise HTTPException(status_code=403, detail="Unauthorized to view other users' permissions")
        
    perms = get_user_permissions(target_user)
    return {"user_id": target_user.id, "username": target_user.username, "permissions": perms}


# Document Management Endpoints 

@app.post("/documents/upload", response_model=DocumentOut)
def upload_document(
    title: str = Form(...),
    company_name: str = Form(...),
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(PermissionChecker("upload_document"))
):
    
    user_roles_list = [r.name.lower() for r in current_user.roles]
    if "admin" not in user_roles_list and current_user.company_name.lower() != company_name.lower():
        
        raise HTTPException(status_code=403, detail="Analysts can only upload documents for their own company")

    doc_id = str(uuid.uuid4())
    filename = f"{doc_id}_{file.filename}"
    file_path = settings.UPLOAD_DIR / filename
    
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File saving failed: {e}")
        
    new_doc = Document(
        id=doc_id,
        title=title,
        company_name=company_name,
        document_type=document_type,
        filepath=str(file_path),
        uploaded_by=current_user.id
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)
    
    
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        metadata = {
            "title": title,
            "company_name": company_name,
            "document_type": document_type
        }
        index_document_content(doc_id, content, metadata)
    except Exception as e:
        print(f"Warning: Auto-indexing vectors failed for document {doc_id}: {e}")    
    return DocumentOut(
        document_id=new_doc.id,
        title=new_doc.title,
        company_name=new_doc.company_name,
        document_type=new_doc.document_type,
        uploaded_by=new_doc.uploaded_by,
        created_at=new_doc.created_at
    )

@app.get("/documents", response_model=List[DocumentOut])
def get_all_documents(db: Session = Depends(get_db), current_user: User = Depends(PermissionChecker("view_document"))):
    user_roles_list = [r.name.lower() for r in current_user.roles]
    
    
    if "client" in user_roles_list and "admin" not in user_roles_list:
        docs = db.query(Document).filter(Document.company_name.collate("NOCASE") == current_user.company_name).all()
    else:
        docs = db.query(Document).all()
        
    return [
        DocumentOut(
            document_id=d.id,
            title=d.title,
            company_name=d.company_name,
            document_type=d.document_type,
            uploaded_by=d.uploaded_by,
            created_at=d.created_at
        ) for d in docs
    ]

@app.get("/documents/{document_id}", response_model=DocumentOut)
def get_document_details(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(PermissionChecker("view_document"))):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    check_document_access(current_user, doc)
    
    return DocumentOut(
        document_id=doc.id,
        title=doc.title,
        company_name=doc.company_name,
        document_type=doc.document_type,
        uploaded_by=doc.uploaded_by,
        created_at=doc.created_at
    )

@app.delete("/documents/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(PermissionChecker("full_access"))):
    
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    
    try:
        delete_document_content(document_id)
    except Exception as e:
        print(f"Warning: Failed to delete Qdrant vectors for doc {document_id}: {e}")
        

    if os.path.exists(doc.filepath):
        try:
            os.remove(doc.filepath)
        except Exception as e:
            print(f"Warning: Failed to remove local file at {doc.filepath}: {e}")
            
    db.delete(doc)
    db.commit()
    return {"message": "Document successfully deleted and vectors purged"}

@app.get("/documents/search", response_model=List[DocumentOut])
def search_documents_by_metadata(
    title: Optional[str] = None,
    company_name: Optional[str] = None,
    document_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(PermissionChecker("view_document"))
):
    user_roles_list = [r.name.lower() for r in current_user.roles]
    query = db.query(Document)
    
    
    if "client" in user_roles_list and "admin" not in user_roles_list:
        query = query.filter(Document.company_name.collate("NOCASE") == current_user.company_name)
    elif company_name:
        query = query.filter(Document.company_name.like(f"%{company_name}%"))
        
    if title:
        query = query.filter(Document.title.like(f"%{title}%"))
    if document_type:
        query = query.filter(Document.document_type.like(f"%{document_type}%"))
        
    docs = query.all()
    return [
        DocumentOut(
            document_id=d.id,
            title=d.title,
            company_name=d.company_name,
            document_type=d.document_type,
            uploaded_by=d.uploaded_by,
            created_at=d.created_at
        ) for d in docs
    ]


# RAG & Semantic Analytics Endpoints 

@app.post("/rag/index-document")
def index_document(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(PermissionChecker("upload_document"))):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    check_document_access(current_user, doc)
    
    if not os.path.exists(doc.filepath):
        raise HTTPException(status_code=400, detail="Document physical file is missing from uploader storage")
        
    try:
        with open(doc.filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
        metadata = {
            "title": doc.title,
            "company_name": doc.company_name,
            "document_type": doc.document_type
        }
        chunks_count = index_document_content(doc.id, content, metadata)
        return {"message": f"Successfully vectorized {chunks_count} chunks inside Qdrant"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {e}")

@app.delete("/rag/remove-document/{id}")
def remove_document_embeddings(id: str, db: Session = Depends(get_db), current_user: User = Depends(PermissionChecker("full_access"))):
    try:
        delete_document_content(id)
        return {"message": "Document embeddings successfully purged from Qdrant vector database"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to purge vectors: {e}")

@app.post("/rag/search", response_model=RAGSearchResponse)
def semantic_search(search_req: RAGSearchRequest, db: Session = Depends(get_db), current_user: User = Depends(PermissionChecker("view_document"))):
    user_roles_list = [r.name.lower() for r in current_user.roles]
    
    
    company_filter = current_user.company_name if ("client" in user_roles_list and "admin" not in user_roles_list) else None
    
    try:
        chunks = search_semantic_chunks(search_req.query, company_name=company_filter)
        
        answer = generate_financial_insight(search_req.query, chunks)
        
        chunks_response = [
            RAGChunkResponse(
                chunk_id=c["chunk_id"],
                document_id=c["document_id"],
                text=c["text"],
                score=c["score"],
                title=c["title"],
                company_name=c["company_name"],
                document_type=c["document_type"]
            ) for c in chunks
        ]
        
        return RAGSearchResponse(
            query=search_req.query,
            answer=answer,
            chunks=chunks_response
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Semantic search operation failed: {e}")

@app.get("/rag/context/{document_id}", response_model=RAGContextResponse)
def get_related_document_context(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(PermissionChecker("view_document"))):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    check_document_access(current_user, doc)
    
    summary_data = get_document_context_summary(document_id)
    return RAGContextResponse(
        document_id=document_id,
        chunks_count=summary_data["chunks_count"],
        text_preview=summary_data["text_preview"]
    )


# Serve Single Page Application Frontend 

frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Financial Document Management API is running. Frontend static resources are initializing."}
