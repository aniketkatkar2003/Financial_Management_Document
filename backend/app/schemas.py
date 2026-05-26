from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime


class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str
    company_name: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    company_name: str
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None

#Role & Permission Schemas

class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None

class RoleOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True

class RoleAssign(BaseModel):
    user_id: int
    role_name: str

class UserRolesOut(BaseModel):
    user_id: int
    username: str
    roles: List[str]

class PermissionOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True

class UserPermissionsOut(BaseModel):
    user_id: int
    username: str
    permissions: List[str]



class DocumentOut(BaseModel):
    document_id: str
    title: str
    company_name: str
    document_type: str
    uploaded_by: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RAGSearchRequest(BaseModel):
    query: str

class RAGChunkResponse(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    title: str
    company_name: str
    document_type: str

class RAGSearchResponse(BaseModel):
    query: str
    answer: str
    chunks: List[RAGChunkResponse]

class RAGContextResponse(BaseModel):
    document_id: str
    chunks_count: int
    text_preview: str
