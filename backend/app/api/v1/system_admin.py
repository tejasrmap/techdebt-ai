from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.all_models import User
from app.services.auth_service import require_roles
from app.services.cache_service import CacheService
from app.services.disaster_recovery_service import DisasterRecoveryService

router = APIRouter(prefix="/system", tags=["System Administration & Disaster Recovery"])

class RestoreRequest(BaseModel):
    backup_id: str

@router.get("/cache/stats")
def get_cache_statistics(
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator"]))
):
    """Retrieve operational cache performance metrics (hits, misses, hit ratio)."""
    return CacheService.get_stats()

@router.post("/cache/clear")
def clear_system_cache(
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator"]))
):
    """Purge in-memory performance cache."""
    CacheService.clear()
    return {"message": "System cache purged successfully"}

@router.post("/disaster-recovery/backup")
def create_backup_snapshot(
    current_user: User = Depends(require_roles(["SuperAdmin"]))
):
    """Trigger an atomic point-in-time database backup snapshot (Platform SuperAdmin only)."""
    manifest = DisasterRecoveryService.create_backup()
    return {
        "message": "Point-in-time database backup created successfully",
        "backup": manifest
    }

@router.get("/disaster-recovery/backups")
def list_backup_snapshots(
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator"]))
):
    """List available disaster recovery snapshots with integrity status."""
    backups = DisasterRecoveryService.list_backups()
    return {"backups": backups}

@router.post("/disaster-recovery/restore")
def restore_backup_snapshot(
    req: RestoreRequest,
    current_user: User = Depends(require_roles(["SuperAdmin"]))
):
    """Restore database from point-in-time snapshot with integrity validation (Platform SuperAdmin only)."""
    try:
        success = DisasterRecoveryService.restore_backup(req.backup_id)
        return {"message": f"Database restored successfully from backup {req.backup_id}", "restored": success}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Disaster recovery restore failed: {e}")
