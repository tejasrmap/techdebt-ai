import uuid
import secrets
import hashlib
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.all_models import User, Organization, RevokedToken, OrganizationInvitation

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        pw_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pw_bytes, hash_bytes)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    pw_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Assign unique jti for revocation tracking
    jti = str(uuid.uuid4())
    to_encode.update({
        "exp": expire,
        "iat": now,
        "jti": jti
    })
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials or token expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

def revoke_token(token: str, db: Session) -> None:
    try:
        payload = decode_token(token)
        jti = payload.get("jti")
        exp_ts = payload.get("exp")
        if jti and exp_ts:
            exp_dt = datetime.utcfromtimestamp(exp_ts)
            # Only record if not already revoked
            existing = db.query(RevokedToken).filter(RevokedToken.jti == jti).first()
            if not existing:
                revoked = RevokedToken(jti=jti, expires_at=exp_dt)
                db.add(revoked)
                db.commit()
    except HTTPException:
        pass

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or token expired",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_token(token)
    user_id: Optional[str] = payload.get("sub")
    jti: Optional[str] = payload.get("jti")
    
    if user_id is None or jti is None:
        raise credentials_exception

    # Check if token was revoked
    revoked = db.query(RevokedToken).filter(RevokedToken.jti == jti).first()
    if revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if user is None:
        raise credentials_exception
    return user

class UserRole:
    SUPER_ADMIN = "SuperAdmin"
    OWNER = "Owner"
    ADMINISTRATOR = "Administrator"
    ENGINEERING_MANAGER = "Engineering Manager"
    DEVELOPER = "Developer"
    VIEWER = "Viewer"

    ALL_ROLES = [
        SUPER_ADMIN,
        OWNER,
        ADMINISTRATOR,
        ENGINEERING_MANAGER,
        DEVELOPER,
        VIEWER
    ]

ROLE_PERMISSIONS = {
    UserRole.SUPER_ADMIN: {
        "system:manage", "org:manage", "org:delete", "billing:manage",
        "teams:manage", "projects:create", "projects:edit", "projects:delete",
        "assessments:run", "repositories:manage", "risks:manage", "reports:export", "data:read"
    },
    UserRole.OWNER: {
        "org:manage", "org:delete", "billing:manage", "teams:manage",
        "projects:create", "projects:edit", "projects:delete",
        "assessments:run", "repositories:manage", "risks:manage", "reports:export", "data:read"
    },
    UserRole.ADMINISTRATOR: {
        "org:manage", "teams:manage",
        "projects:create", "projects:edit", "projects:delete",
        "assessments:run", "repositories:manage", "risks:manage", "reports:export", "data:read"
    },
    UserRole.ENGINEERING_MANAGER: {
        "teams:manage", "projects:create", "projects:edit",
        "assessments:run", "repositories:manage", "risks:manage", "reports:export", "data:read"
    },
    UserRole.DEVELOPER: {
        "projects:create", "assessments:run", "repositories:manage", "risks:manage", "reports:export", "data:read"
    },
    UserRole.VIEWER: {
        "reports:export", "data:read"
    }
}

def has_permission(role: str, permission: str) -> bool:
    if role == UserRole.SUPER_ADMIN:
        return True
    return permission in ROLE_PERMISSIONS.get(role, set())

def require_permission(permission: str):
    """Enforce fine-grained functional permission."""
    def perm_checker(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Missing required permission: '{permission}'"
            )
        return current_user
    return perm_checker

def require_roles(allowed_roles: List[str]):
    """Strict RBAC verification with role inheritance."""
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        # SuperAdmin inherits all roles
        if current_user.role == UserRole.SUPER_ADMIN:
            return current_user
        # Owner inherits Administrator and Engineering Manager roles
        if current_user.role == UserRole.OWNER and any(r in allowed_roles for r in [UserRole.ADMINISTRATOR, UserRole.ENGINEERING_MANAGER]):
            return current_user
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required roles: {', '.join(allowed_roles)}"
            )
        return current_user
    return role_checker

def generate_invitation_token() -> str:
    return secrets.token_urlsafe(32)

def hash_invitation_token(raw_token: str) -> str:
    """Hash invitation token using SHA-256 for secure storage."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()

def cleanup_expired_revoked_tokens(db: Session) -> int:
    """Purge expired tokens from the revocation list to keep table size bounded."""
    try:
        now = datetime.utcnow()
        deleted = db.query(RevokedToken).filter(RevokedToken.expires_at < now).delete(synchronize_session=False)
        db.commit()
        return deleted
    except Exception:
        db.rollback()
        return 0
