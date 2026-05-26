from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.auth import get_current_user
from app.models import User, Role, Permission, Document

def get_user_permissions(user: User) -> list[str]:
    """Retrieve all permission names assigned to a user through their roles."""
    permissions = set()
    for role in user.roles:
    
        if role.name.lower() == "admin":
            return ["full_access"]
        for perm in role.permissions:
            permissions.add(perm.name)
    return list(permissions)

class PermissionChecker:
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    def __call__(self, user: User = Depends(get_current_user)) -> User:
        user_perms = get_user_permissions(user)
        
        
        if "full_access" in user_perms:
            return user
            
        if self.required_permission not in user_perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {self.required_permission}"
            )
        return user

def check_document_access(user: User, document: Document):
    """
    Ensures users can only access documents within their scope.
    Clients are restricted to viewing documents that match their own company.
    """
    user_roles = [r.name.lower() for r in user.roles]
    
    
    if "admin" in user_roles:
        return
        
    
    if "client" in user_roles:
        if document.company_name.lower() != user.company_name.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only view documents belonging to your company."
            )
