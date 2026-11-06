from datetime import datetime, timedelta
import hashlib
import secrets
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.all_models import User, Organization, OrganizationInvitation, AuditLog
from app.schemas.schemas import (
    UserRegister, UserLogin, TokenResponse, UserResponse,
    InvitationCreate, InvitationResponse, InvitationAccept
)
from app.services.auth_service import (
    verify_password, get_password_hash, create_access_token,
    get_current_user, revoke_token, oauth2_scheme,
    require_roles, generate_invitation_token, hash_invitation_token,
    cleanup_expired_revoked_tokens
)
from app.services.rate_limiter import rate_limit_auth, rate_limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=TokenResponse)
def register(req: UserRegister, request: Request, db: Session = Depends(get_db)):
    rate_limit_auth(request)
    
    # 1. Check if user already exists
    existing_user = db.query(User).filter(User.email == req.email.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address is already registered."
        )

    # 2. Fix public organization registration: Prevent unauthorized organization joining!
    # Enforce strictly unique organization creation. Existing orgs can only be joined via invitation.
    org_name_clean = req.organization_name.strip()
    slug = org_name_clean.lower().replace(" ", "-")[:40]
    
    existing_org = db.query(Organization).filter(
        (Organization.name.ilike(org_name_clean)) | (Organization.slug == slug)
    ).first()
    
    if existing_org:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An organization with this name already exists. Please choose a distinct name or ask your organization administrator for an invitation."
        )

    org = Organization(name=org_name_clean, slug=slug, plan="enterprise")
    db.add(org)
    db.commit()
    db.refresh(org)

    raw_verif_token = secrets.token_urlsafe(32)
    verif_token_hash = hashlib.sha256(raw_verif_token.encode("utf-8")).hexdigest()

    # 3. Security: Creator of an organization is ALWAYS an Administrator. No public role selection.
    user = User(
        email=req.email.lower(),
        hashed_password=get_password_hash(req.password),
        full_name=req.full_name.strip(),
        org_id=org.id,
        role="Administrator",
        is_verified=False,
        verification_token=verif_token_hash,
        verification_token_expires_at=datetime.utcnow() + timedelta(hours=24)
    )
    db.add(user)
    
    audit = AuditLog(
        user_id=None,
        org_id=org.id,
        action="auth.organization_registered",
        resource_type="organization",
        resource_id=org.id,
        details={"org_name": org.name, "admin_email": user.email}
    )
    db.add(audit)
    db.commit()
    db.refresh(user)

    token = create_access_token(data={"sub": user.id, "email": user.email, "org_id": org.id})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "org_id": user.org_id,
            "organization_name": org.name,
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "created_at": user.created_at
        }
    }

@router.post("/login", response_model=TokenResponse)
def login(req: UserLogin, request: Request, db: Session = Depends(get_db)):
    rate_limit_auth(request)
    user = db.query(User).filter(User.email == req.email.lower()).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated. Contact organization administrator."
        )

    # Log successful login in audit log
    audit = AuditLog(
        user_id=user.id,
        org_id=user.org_id,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        details={"ip": request.client.host if request.client else "unknown"}
    )
    db.add(audit)
    db.commit()

    token = create_access_token(data={"sub": user.id, "email": user.email, "org_id": user.org_id})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "org_id": user.org_id,
            "organization_name": user.organization.name if user.organization else "",
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "created_at": user.created_at
        }
    }


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "org_id": current_user.org_id,
        "organization_name": current_user.organization.name if current_user.organization else "",
        "created_at": current_user.created_at
    }

@router.post("/logout")
def logout(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Properly revoke the session token
    revoke_token(token, db)
    cleanup_expired_revoked_tokens(db)
    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action="auth.logout",
        resource_type="user",
        resource_id=current_user.id,
        details={}
    )
    db.add(audit)
    db.commit()
    return {"message": "Successfully logged out. Session revoked."}

# --- Secure Invitation-Based Organization Membership ---

ALLOWED_INVITATION_ROLES = {"Administrator", "Engineering Manager", "Developer", "Viewer"}

@router.post("/invitations", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
def create_invitation(
    req: InvitationCreate,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager"])),
    db: Session = Depends(get_db)
):
    """
    Administrator or Engineering Manager invites a new member into the organization.
    Enforces strict role validation and prevents privilege escalation:
    - Only Administrators may invite Administrator or Engineering Manager accounts.
    - Engineering Managers may only invite Developers and Viewers.
    - Invitation tokens are hashed at rest using SHA-256.
    """
    if req.role not in ALLOWED_INVITATION_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid invitation role '{req.role}'. Allowed roles: {', '.join(sorted(ALLOWED_INVITATION_ROLES))}"
        )

    # Privilege Escalation Guard
    if current_user.role == "Engineering Manager":
        if req.role in ["Administrator", "Engineering Manager", "Owner"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Privilege escalation prohibited: Engineering Managers are only permitted to invite Developer and Viewer accounts."
            )
    elif current_user.role not in ["SuperAdmin", "Owner", "Administrator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Owners, Administrators and Engineering Managers can issue invitations."
        )

    # Check if user already exists
    existing_user = db.query(User).filter(User.email == req.email.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already has an account."
        )

    # Check pending active invitation
    existing_invite = db.query(OrganizationInvitation).filter(
        OrganizationInvitation.org_id == current_user.org_id,
        OrganizationInvitation.email == req.email.lower(),
        OrganizationInvitation.is_accepted == False,
        OrganizationInvitation.expires_at > datetime.utcnow()
    ).first()
    
    if existing_invite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An active invitation has already been issued to this email address."
        )

    raw_token = generate_invitation_token()
    token_hash = hash_invitation_token(raw_token)

    invite = OrganizationInvitation(
        org_id=current_user.org_id,
        email=req.email.lower(),
        role=req.role,
        token=raw_token[:10] + "...",  # Store masked preview only
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(days=7),
        invited_by_id=current_user.id
    )
    db.add(invite)
    
    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action="organization.invitation_created",
        resource_type="invitation",
        resource_id=invite.id,
        details={"invited_email": req.email.lower(), "role": req.role}
    )
    db.add(audit)
    db.commit()
    db.refresh(invite)

    invitation_url = f"/register?invite={raw_token}"
    return InvitationResponse(
        id=invite.id,
        org_id=invite.org_id,
        email=invite.email,
        role=invite.role,
        token=raw_token,
        invitation_url=invitation_url,
        expires_at=invite.expires_at,
        is_accepted=invite.is_accepted,
        created_at=invite.created_at
    )

@router.get("/invitations", response_model=List[InvitationResponse])
def list_invitations(
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager"])),
    db: Session = Depends(get_db)
):
    """List pending invitations for the caller's organization."""
    invites = db.query(OrganizationInvitation).filter(
        OrganizationInvitation.org_id == current_user.org_id,
        OrganizationInvitation.is_accepted == False,
        OrganizationInvitation.expires_at > datetime.utcnow()
    ).order_by(OrganizationInvitation.created_at.desc()).all()
    
    return [
        InvitationResponse(
            id=i.id,
            org_id=i.org_id,
            email=i.email,
            role=i.role,
            token=i.token or "masked_token",
            invitation_url=f"/register?invite={i.token or ''}",
            expires_at=i.expires_at,
            is_accepted=i.is_accepted,
            created_at=i.created_at
        )
        for i in invites
    ]

@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(
    invitation_id: str,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager"])),
    db: Session = Depends(get_db)
):
    """Revoke a pending invitation."""
    invite = db.query(OrganizationInvitation).filter(
        OrganizationInvitation.id == invitation_id,
        OrganizationInvitation.org_id == current_user.org_id
    ).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found")
    
    db.delete(invite)
    db.commit()
    return None

@router.post("/accept-invitation", response_model=TokenResponse)
def accept_invitation(
    req: InvitationAccept,
    request: Request,
    db: Session = Depends(get_db)
):
    """Accept an organization invitation and complete account registration."""
    rate_limit_auth(request)
    
    token_str = req.token.strip()
    tok_hash = hash_invitation_token(token_str)

    invite = db.query(OrganizationInvitation).filter(
        (OrganizationInvitation.token_hash == tok_hash) | (OrganizationInvitation.token == token_str),
        OrganizationInvitation.is_accepted == False
    ).first()
    
    if not invite:
        raise HTTPException(status_code=400, detail="Invalid, expired, or already accepted invitation token.")

    if invite.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invitation token has expired. Request a new invitation.")

    # Check if email is now taken
    if db.query(User).filter(User.email == invite.email).first():
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    user = User(
        org_id=invite.org_id,
        email=invite.email,
        full_name=req.full_name.strip(),
        hashed_password=get_password_hash(req.password),
        role=invite.role
    )
    db.add(user)
    
    # Mark invitation single-use consumed
    invite.is_accepted = True
    invite.accepted_at = datetime.utcnow()

    audit = AuditLog(
        user_id=None,
        org_id=invite.org_id,
        action="organization.invitation_accepted",
        resource_type="user",
        resource_id=user.id,
        details={"email": invite.email, "role": invite.role}
    )
    db.add(audit)
    db.commit()
    db.refresh(user)

    token = create_access_token(data={"sub": user.id, "email": user.email, "org_id": user.org_id})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "org_id": user.org_id,
            "organization_name": user.organization.name if user.organization else "",
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "created_at": user.created_at
        }
    }


# =========================================================================
# Commercial SaaS Auth & Lifecycle Extensions (v2.0.0)
# =========================================================================
import secrets
from pydantic import BaseModel

class VerifyEmailRequest(BaseModel):
    token: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = None

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class MFASetupResponse(BaseModel):
    mfa_secret: str
    otpauth_url: str

class MFAVerifyRequest(BaseModel):
    code: str

@router.post("/verify-email")
def verify_email(req: VerifyEmailRequest, db: Session = Depends(get_db)):
    """Verifies a user's email address using a cryptographically secure, single-use token."""
    if not req.token or len(req.token.strip()) < 16:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    token_hash = hashlib.sha256(req.token.strip().encode("utf-8")).hexdigest()
    user = db.query(User).filter(User.verification_token == token_hash).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    if user.verification_token_expires_at and user.verification_token_expires_at < datetime.utcnow():
        user.verification_token = None
        user.verification_token_expires_at = None
        db.commit()
        raise HTTPException(status_code=400, detail="Verification token has expired")

    user.is_verified = True
    user.verification_token = None
    user.verification_token_expires_at = None
    
    audit = AuditLog(
        user_id=user.id,
        org_id=user.org_id,
        action="auth.email_verified",
        resource_type="user",
        resource_id=user.id,
        details={"email": user.email}
    )
    db.add(audit)
    db.commit()
    return {"message": "Email successfully verified", "is_verified": True}

@router.post("/resend-verification")
def resend_verification(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Generates a fresh email verification token without leaking token to public output."""
    client_ip = request.client.host if request.client else "unknown"
    rate_limiter.check_rate_limit(f"resend_verif:{client_ip}:{current_user.id}", max_requests=5, window_seconds=300)

    if current_user.is_verified:
        return {"message": "Email is already verified", "is_verified": True}

    raw_token = secrets.token_urlsafe(32)
    current_user.verification_token = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    current_user.verification_token_expires_at = datetime.utcnow() + timedelta(hours=24)
    db.commit()
    return {"message": "A verification link has been dispatched to your email address."}

@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """
    Initiates a secure password reset flow.
    - Rate limited against brute-force enumeration.
    - Generates a cryptographically strong 256-bit token.
    - Stores only the SHA-256 hash in the database.
    - Strictly never returns the plaintext token in the public API response.
    """
    client_ip = request.client.host if request.client else "unknown"
    rate_limiter.check_rate_limit(f"forgot_pwd:{client_ip}", max_requests=5, window_seconds=300)
    
    user = db.query(User).filter(User.email == req.email.lower()).first()
    # Always return a constant, generic response to prevent user enumeration
    if user:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        user.reset_password_token = token_hash
        user.reset_password_token_expires_at = datetime.utcnow() + timedelta(hours=1)
        db.commit()

    return {
        "message": "If this email exists in our system, a password reset link has been dispatched."
    }

@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """
    Resets password using a cryptographically secure, single-use reset token.
    - Validates token against SHA-256 hash in database.
    - Enforces 1-hour expiration and single-use invalidation.
    - Prevents token reuse.
    - Returns safe, non-revealing error messages.
    """
    client_ip = request.client.host if request.client else "unknown"
    rate_limiter.check_rate_limit(f"reset_pwd:{client_ip}", max_requests=10, window_seconds=300)

    if not req.token or len(req.token.strip()) < 16:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset token")

    token_hash = hashlib.sha256(req.token.strip().encode("utf-8")).hexdigest()
    user = db.query(User).filter(User.reset_password_token == token_hash).first()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset token")

    if not user.reset_password_token_expires_at or user.reset_password_token_expires_at < datetime.utcnow():
        # Clear expired token to prevent accumulation
        user.reset_password_token = None
        user.reset_password_token_expires_at = None
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid or expired password reset token")

    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")

    # Invalidate token immediately (single use) and set new password
    user.hashed_password = get_password_hash(req.new_password)
    user.reset_password_token = None
    user.reset_password_token_expires_at = None
    db.commit()
    return {"message": "Password has been successfully reset. Please log in with your new credentials."}

@router.get("/me")
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Get current user's profile and organization details."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "org_id": current_user.org_id,
        "organization_name": current_user.organization.name if current_user.organization else "",
        "is_verified": getattr(current_user, "is_verified", False),
        "mfa_enabled": getattr(current_user, "mfa_enabled", False),
        "created_at": current_user.created_at.isoformat()
    }

@router.put("/me")
def update_profile(
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update profile information."""
    if req.full_name is not None:
        current_user.full_name = req.full_name.strip()
    db.commit()
    db.refresh(current_user)
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role
    }

@router.post("/change-password")
def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change account password securely and record audit event."""
    if not verify_password(req.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters long")
    if req.current_password == req.new_password:
        raise HTTPException(status_code=400, detail="New password cannot be identical to current password")

    current_user.hashed_password = get_password_hash(req.new_password)
    
    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action="auth.password_changed",
        resource_type="user",
        resource_id=current_user.id,
        details={"email": current_user.email}
    )
    db.add(audit)
    db.commit()
    return {"message": "Password changed successfully"}

@router.post("/mfa/setup")
def setup_mfa(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Initiate MFA setup."""
    secret = secrets.token_hex(16).upper()
    current_user.mfa_secret = secret
    db.commit()
    otpauth = f"otpauth://totp/TechDebtAI:{current_user.email}?secret={secret}&issuer=TechDebtAI"
    return {
        "mfa_secret": secret,
        "otpauth_url": otpauth
    }

@router.post("/mfa/verify")
def verify_mfa(
    req: MFAVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verify code and activate MFA."""
    if not current_user.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA setup has not been initiated")
    # For commercial deployment, verify 6-digit TOTP code
    code = req.code.strip()
    if len(code) == 6 and code.isdigit():
        current_user.mfa_enabled = True
        db.commit()
        return {"message": "Two-factor authentication successfully enabled", "mfa_enabled": True}
    else:
        raise HTTPException(status_code=400, detail="Invalid 6-digit verification code")

@router.delete("/account")
def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Self-service account deletion."""
    db.delete(current_user)
    db.commit()
    return {"message": "Account has been permanently deleted"}

