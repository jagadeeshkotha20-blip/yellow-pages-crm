import csv
import io
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, Response
from flask_login import login_required, current_user
from sqlalchemy import func

from extensions import db
from models import User, Lead, CallLog, FollowUp, AssignmentHistory, Enrollment
from permissions import management_required, visible_employees_query_for, visible_user_ids_for

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route("/activity")
@management_required
def activity():
    employee_ids = [u.id for u in visible_employees_query_for(current_user).all()]

    rows = []
    for emp in visible_employees_query_for(current_user).order_by(User.name).all():
        calls = CallLog.query.filter_by(employee_id=emp.id).count()
        followups_set = FollowUp.query.filter_by(employee_id=emp.id).count()
        followups_pending = FollowUp.query.filter_by(employee_id=emp.id, is_completed=False).count()
        leads_assigned = Lead.query.filter_by(assigned_to_id=emp.id).count()
        enrollments = Enrollment.query.filter_by(created_by_id=emp.id).count()
        rows.append(dict(
            employee=emp, calls=calls, followups_set=followups_set,
            followups_pending=followups_pending, leads_assigned=leads_assigned,
            enrollments=enrollments,
        ))

    return render_template("reports_activity.html", rows=rows)


@reports_bp.route("/activity/export.csv")
@management_required
def activity_export():
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Employee", "Role", "Calls Made", "Follow-ups Set",
                      "Follow-ups Pending", "Leads Currently Assigned", "Enrollments"])
    for emp in visible_employees_query_for(current_user).order_by(User.name).all():
        writer.writerow([
            emp.name, emp.role_label,
            CallLog.query.filter_by(employee_id=emp.id).count(),
            FollowUp.query.filter_by(employee_id=emp.id).count(),
            FollowUp.query.filter_by(employee_id=emp.id, is_completed=False).count(),
            Lead.query.filter_by(assigned_to_id=emp.id).count(),
            Enrollment.query.filter_by(created_by_id=emp.id).count(),
        ])
    return Response(buffer.getvalue(), mimetype="text/csv",
                     headers={"Content-Disposition": "attachment; filename=activity_report.csv"})


@reports_bp.route("/followups")
@management_required
def followups():
    employee_ids = [u.id for u in visible_employees_query_for(current_user).all()]

    status = request.args.get("status", "pending")  # pending | overdue | completed | all
    query = FollowUp.query.filter(FollowUp.employee_id.in_(employee_ids))

    now = datetime.utcnow()
    if status == "pending":
        query = query.filter(FollowUp.is_completed.is_(False), FollowUp.follow_up_date >= now)
    elif status == "overdue":
        query = query.filter(FollowUp.is_completed.is_(False), FollowUp.follow_up_date < now)
    elif status == "completed":
        query = query.filter(FollowUp.is_completed.is_(True))
    # "all" applies no extra filter

    items = query.order_by(FollowUp.follow_up_date.asc()).limit(500).all()
    return render_template("reports_followups.html", items=items, status=status, now=now)


@reports_bp.route("/reassignments")
@management_required
def reassignments():
    employee_ids = set(u.id for u in visible_employees_query_for(current_user).all())

    query = AssignmentHistory.query.order_by(AssignmentHistory.changed_at.desc())
    items = query.limit(1000).all()

    # Scope to events touching someone in this manager's visibility (from, to, or changed_by)
    if current_user.role not in ("super_admin", "admin", "hr_admin"):
        items = [
            a for a in items
            if (a.from_employee_id in employee_ids or a.to_employee_id in employee_ids
                or a.changed_by_id in employee_ids)
        ]

    return render_template("reports_reassignments.html", items=items[:300])
