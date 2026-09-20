from datetime import datetime, timedelta
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from sqlalchemy import func

from extensions import db
from models import (
    Lead, User, FollowUp, Enrollment, STATUS_ENROLLED, STATUS_READY_PAYMENT,
    STATUS_INTERESTED, STATUS_NOT_INTERESTED, ALL_STATUSES,
)
from permissions import leads_query_for_user, visible_employees_query_for

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@dashboard_bp.route("/dashboard")
@login_required
def index():
    base_query = leads_query_for_user(current_user)

    total_leads = base_query.count()
    unassigned_leads = base_query.filter(Lead.assigned_to_id.is_(None)).count()
    assigned_leads = total_leads - unassigned_leads

    status_counts = {}
    for status in ALL_STATUSES:
        status_counts[status] = base_query.filter(Lead.status == status).count()

    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = today_start + timedelta(days=1)

    visible_employee_ids = None
    emp_q = visible_employees_query_for(current_user)
    visible_employee_ids = [u.id for u in emp_q.all()]

    follow_ups_today = (
        FollowUp.query.filter(
            FollowUp.is_completed.is_(False),
            FollowUp.follow_up_date >= today_start,
            FollowUp.follow_up_date < today_end,
            FollowUp.employee_id.in_(visible_employee_ids) if visible_employee_ids else True,
        ).count()
    )

    overdue_follow_ups = (
        FollowUp.query.filter(
            FollowUp.is_completed.is_(False),
            FollowUp.follow_up_date < today_start,
            FollowUp.employee_id.in_(visible_employee_ids) if visible_employee_ids else True,
        ).count()
    )

    enrolled_count = status_counts.get(STATUS_ENROLLED, 0)

    employee_count = None
    if current_user.is_management():
        employee_count = visible_employees_query_for(current_user).filter(
            User.is_active_employee.is_(True)
        ).count()

    # Simple leaderboard: calls-to-status changes per employee this month (management view only)
    leaderboard = []
    if current_user.is_management():
        month_start = today.replace(day=1)
        rows = (
            db.session.query(User.name, func.count(Lead.id))
            .join(Lead, Lead.assigned_to_id == User.id)
            .filter(User.id.in_(visible_employee_ids))
            .filter(Lead.updated_at >= month_start)
            .group_by(User.name)
            .order_by(func.count(Lead.id).desc())
            .limit(8)
            .all()
        )
        leaderboard = rows

    return render_template(
        "dashboard.html",
        total_leads=total_leads,
        unassigned_leads=unassigned_leads,
        assigned_leads=assigned_leads,
        status_counts=status_counts,
        follow_ups_today=follow_ups_today,
        overdue_follow_ups=overdue_follow_ups,
        enrolled_count=enrolled_count,
        employee_count=employee_count,
        leaderboard=leaderboard,
    )
