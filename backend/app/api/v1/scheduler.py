from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.database import get_db
from app.models.all_models import ScheduledReview, ReviewJob, Project, User, AuditLog
from app.schemas.schemas import ScheduledReviewCreate, ScheduledReviewUpdate, ScheduledReviewResponse
from app.services.auth_service import get_current_user, require_roles
from app.services.scheduler_service import (
    execute_project_review,
    validate_and_compute_next_run,
    register_job_in_scheduler,
    unregister_job_from_scheduler
)

router = APIRouter(prefix="/scheduler", tags=["Review Scheduler"])

@router.get("", response_model=List[ScheduledReviewResponse])
def get_schedules(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    schedules = (
        db.query(ScheduledReview)
        .join(Project)
        .filter(Project.org_id == current_user.org_id)
        .all()
    )
    return [
        {
            "id": s.id,
            "project_id": s.project_id,
            "project_name": s.project.name if s.project else "",
            "frequency": s.frequency,
            "cron_expression": s.cron_expression,
            "is_active": s.is_active,
            "last_run_at": s.last_run_at,
            "next_run_at": s.next_run_at,
            "created_at": s.created_at
        }
        for s in schedules
    ]

@router.post("", response_model=ScheduledReviewResponse, status_code=status.HTTP_201_CREATED)
def create_schedule(
    req: ScheduledReviewCreate,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager"])),
    db: Session = Depends(get_db)
):
    # 1. Enforce organization ownership check on project
    project = db.query(Project).filter(Project.id == req.project_id, Project.org_id == current_user.org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or unauthorized")

    cron = req.cron_expression or "0 0 * * 1"
    if req.frequency == "Weekly":
        cron = "0 0 * * 1"
    elif req.frequency == "Monthly":
        cron = "0 0 1 * *"
    elif req.frequency == "Daily":
        cron = "0 0 * * *"

    # 2. Validate cron expression & compute next execution time
    try:
        next_run = validate_and_compute_next_run(cron)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    schedule = ScheduledReview(
        project_id=req.project_id,
        frequency=req.frequency,
        cron_expression=cron,
        is_active=req.is_active if req.is_active is not None else True,
        next_run_at=next_run
    )
    db.add(schedule)
    db.flush()

    # 3. Register recurring job in APScheduler with failure handling
    try:
        register_job_in_scheduler(schedule)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Schedule registration failed: {str(e)}"
        )

    audit = AuditLog(
        user_id=current_user.id,
        org_id=current_user.org_id,
        action="scheduler.create",
        resource_type="scheduled_review",
        resource_id=schedule.id,
        details={"frequency": schedule.frequency, "cron": cron}
    )
    db.add(audit)
    db.commit()
    db.refresh(schedule)

    return {
        "id": schedule.id,
        "project_id": schedule.project_id,
        "project_name": project.name,
        "frequency": schedule.frequency,
        "cron_expression": schedule.cron_expression,
        "is_active": schedule.is_active,
        "last_run_at": None,
        "next_run_at": schedule.next_run_at,
        "created_at": schedule.created_at
    }

@router.patch("/{schedule_id}", response_model=ScheduledReviewResponse)
def update_schedule(
    schedule_id: str,
    req: ScheduledReviewUpdate,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager"])),
    db: Session = Depends(get_db)
):
    """Update or disable/enable a recurring schedule."""
    schedule = (
        db.query(ScheduledReview)
        .join(Project)
        .filter(ScheduledReview.id == schedule_id, Project.org_id == current_user.org_id)
        .first()
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found or unauthorized")

    if req.frequency is not None:
        schedule.frequency = req.frequency
        if req.frequency == "Weekly":
            schedule.cron_expression = "0 0 * * 1"
        elif req.frequency == "Monthly":
            schedule.cron_expression = "0 0 1 * *"
        elif req.frequency == "Daily":
            schedule.cron_expression = "0 0 * * *"

    if req.cron_expression is not None:
        schedule.cron_expression = req.cron_expression

    if req.is_active is not None:
        schedule.is_active = req.is_active

    if schedule.is_active:
        try:
            schedule.next_run_at = validate_and_compute_next_run(schedule.cron_expression)
            register_job_in_scheduler(schedule)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        unregister_job_from_scheduler(schedule.id)
        schedule.next_run_at = None

    db.commit()
    db.refresh(schedule)

    return {
        "id": schedule.id,
        "project_id": schedule.project_id,
        "project_name": schedule.project.name if schedule.project else "",
        "frequency": schedule.frequency,
        "cron_expression": schedule.cron_expression,
        "is_active": schedule.is_active,
        "last_run_at": schedule.last_run_at,
        "next_run_at": schedule.next_run_at,
        "created_at": schedule.created_at
    }

@router.post("/trigger/{schedule_id}")
async def trigger_schedule_now(
    schedule_id: str,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager"])),
    db: Session = Depends(get_db)
):
    s = (
        db.query(ScheduledReview)
        .join(Project)
        .filter(ScheduledReview.id == schedule_id, Project.org_id == current_user.org_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found or unauthorized")

    job = ReviewJob(
        scheduled_review_id=s.id,
        status="Running",
        started_at=datetime.utcnow()
    )
    db.add(job)
    db.commit()

    try:
        assessment = await execute_project_review(
            s.project_id,
            trigger_type="scheduled",
            db_session=db,
            enforce_org_id=current_user.org_id
        )
        job.status = "Completed"
        job.completed_at = datetime.utcnow()
        s.last_run_at = datetime.utcnow()
        s.next_run_at = validate_and_compute_next_run(s.cron_expression)
        db.commit()
        return {"message": "Scheduled review executed successfully", "assessment_id": assessment.id}
    except Exception as e:
        job.status = "Failed"
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=500, detail=f"Review execution failed: {str(e)}")

@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    schedule_id: str,
    current_user: User = Depends(require_roles(["Administrator", "Engineering Manager"])),
    db: Session = Depends(get_db)
):
    s = (
        db.query(ScheduledReview)
        .join(Project)
        .filter(ScheduledReview.id == schedule_id, Project.org_id == current_user.org_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found or unauthorized")
    
    unregister_job_from_scheduler(s.id)
    db.delete(s)
    db.commit()
    return None
