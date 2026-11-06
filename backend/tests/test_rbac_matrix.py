import pytest
from app.services.auth_service import UserRole, ROLE_PERMISSIONS, has_permission

def test_rbac_roles_defined():
    """Verify all 6 commercial roles are properly defined in UserRole."""
    assert UserRole.SUPER_ADMIN == "SuperAdmin"
    assert UserRole.OWNER == "Owner"
    assert UserRole.ADMINISTRATOR == "Administrator"
    assert UserRole.ENGINEERING_MANAGER == "Engineering Manager"
    assert UserRole.DEVELOPER == "Developer"
    assert UserRole.VIEWER == "Viewer"
    assert len(UserRole.ALL_ROLES) == 6

def test_super_admin_permissions():
    """Verify SuperAdmin possesses universal permissions."""
    assert has_permission(UserRole.SUPER_ADMIN, "system:manage")
    assert has_permission(UserRole.SUPER_ADMIN, "org:delete")
    assert has_permission(UserRole.SUPER_ADMIN, "billing:manage")
    assert has_permission(UserRole.SUPER_ADMIN, "arbitrary:permission") is True

def test_owner_permissions():
    """Verify Owner has complete organization management including billing and deletion."""
    assert has_permission(UserRole.OWNER, "org:manage")
    assert has_permission(UserRole.OWNER, "org:delete")
    assert has_permission(UserRole.OWNER, "billing:manage")
    assert has_permission(UserRole.OWNER, "projects:create")
    assert not has_permission(UserRole.OWNER, "system:manage")

def test_administrator_permissions():
    """Verify Administrator cannot delete organization or access system-level admin."""
    assert has_permission(UserRole.ADMINISTRATOR, "org:manage")
    assert has_permission(UserRole.ADMINISTRATOR, "teams:manage")
    assert has_permission(UserRole.ADMINISTRATOR, "projects:create")
    assert not has_permission(UserRole.ADMINISTRATOR, "org:delete")
    assert not has_permission(UserRole.ADMINISTRATOR, "system:manage")

def test_engineering_manager_permissions():
    """Verify Engineering Manager cannot modify billing or organization settings."""
    assert has_permission(UserRole.ENGINEERING_MANAGER, "projects:create")
    assert has_permission(UserRole.ENGINEERING_MANAGER, "assessments:run")
    assert has_permission(UserRole.ENGINEERING_MANAGER, "teams:manage")
    assert not has_permission(UserRole.ENGINEERING_MANAGER, "billing:manage")
    assert not has_permission(UserRole.ENGINEERING_MANAGER, "org:manage")

def test_developer_permissions():
    """Verify Developer can contribute to projects and assessments but not manage teams."""
    assert has_permission(UserRole.DEVELOPER, "projects:create")
    assert has_permission(UserRole.DEVELOPER, "assessments:run")
    assert has_permission(UserRole.DEVELOPER, "risks:manage")
    assert not has_permission(UserRole.DEVELOPER, "teams:manage")
    assert not has_permission(UserRole.DEVELOPER, "billing:manage")

def test_viewer_permissions():
    """Verify Viewer is strictly read-only."""
    assert has_permission(UserRole.VIEWER, "data:read")
    assert has_permission(UserRole.VIEWER, "reports:export")
    assert not has_permission(UserRole.VIEWER, "projects:create")
    assert not has_permission(UserRole.VIEWER, "assessments:run")
    assert not has_permission(UserRole.VIEWER, "risks:manage")
    assert not has_permission(UserRole.VIEWER, "teams:manage")
