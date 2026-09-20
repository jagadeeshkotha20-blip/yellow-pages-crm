from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_required, current_user

from extensions import db
from models import User, Lead, Team, AssignmentHistory, ALL_ROLES, SUPER_ADMIN, ADMIN, HR_ADMIN, INDIAN_STATES
from permissions import management_required, can_manage_employee, visible_employees_query_for
from validators import is_valid_email, is_strong_enough_password

employees_bp = Blueprint("employees", __name__, url_prefix="/employees")

# Only the Super Admin may create or promote someone into these admin-tier
# roles (Requirement #6: "Super Admin... manage admins"). HR Admin is
# admin-tier too — a Team Lead or another non-super-admin manager granting
# HR Admin (or Admin) rights to anyone, including themselves, would be a
# privilege escalation.
ADMIN_TIER_ROLES = (SUPER_ADMIN, ADMIN, HR_ADMIN)


@employees_bp.route("/")
@management_required
def list_employees():
    query = visible_employees_query_for(current_user)

    role_filter = request.args.get("role", "").strip()
    active_filter = request.args.get("active", "").strip()
    search = request.args.get("q", "").strip()

    if role_filter:
        query = query.filter(User.role == role_filter)
    if active_filter == "active":
        query = query.filter(User.is_active_employee.is_(True))
    elif active_filter == "inactive":
        query = query.filter(User.is_active_employee.is_(False))
    if search:
        like = f"%{search}%"
        query = query.filter(db.or_(User.name.ilike(like), User.email.ilike(like)))

    query = query.order_by(User.is_active_employee.desc(), User.name.asc())

    page = request.args.get("page", 1, type=int)
    pagination = query.paginate(
        page=page, per_page=current_app.config["EMPLOYEES_PER_PAGE"], error_out=False
    )
    employees = pagination.items

    # Lead counts per employee (only among those visible on this page)
    lead_counts = {}
    for emp in employees:
        lead_counts[emp.id] = Lead.query.filter_by(assigned_to_id=emp.id).count()

    return render_template(
        "employees_list.html", employees=employees, roles=ALL_ROLES,
        lead_counts=lead_counts, pagination=pagination,
        filters=dict(role=role_filter, active=active_filter, q=search),
    )


def _team_options_for(user):
    if user.role in (SUPER_ADMIN, ADMIN):
        return Team.query.order_by(Team.name).all()
    if user.team_id:
        return Team.query.filter_by(id=user.team_id).all()
    return []


@employees_bp.route("/new", methods=["GET", "POST"])
@management_required
def new_employee():
    manager_options = visible_employees_query_for(current_user).filter(
        User.is_active_employee.is_(True)
    ).all()
    team_options = _team_options_for(current_user)

    if request.method == "POST":
        form = request.form
        name = form.get("name", "").strip()
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        role = form.get("role")

        errors = []
        if not name:
            errors.append("Name is required.")
        if not is_valid_email(email):
            errors.append("Please enter a valid email address.")
        elif User.query.filter_by(email=email).first():
            errors.append("An account with that email already exists.")
        if not is_strong_enough_password(password):
            errors.append("Password must be at least 8 characters and include a letter and a number.")
        if role in ADMIN_TIER_ROLES and not current_user.is_super_admin():
            errors.append("Only a Super Admin can create Admin/HR Admin/Super Admin accounts.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("employee_form.html", roles=ALL_ROLES,
                                    managers=manager_options, states=INDIAN_STATES,
                                    teams=team_options, form_data=form)

        manager_id = form.get("manager_id", type=int) or None
        team_id = form.get("team_id", type=int) or None
        state_scope = ",".join(form.getlist("state_scope")) or None

        user = User(
            name=name, email=email, phone=form.get("phone", "").strip(),
            role=role, manager_id=manager_id, team_id=team_id, state_scope=state_scope,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f"Account created for {user.name}.", "success")
        return redirect(url_for("employees.list_employees"))

    return render_template("employee_form.html", roles=ALL_ROLES,
                            managers=manager_options, states=INDIAN_STATES,
                            teams=team_options, form_data={})


@employees_bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@management_required
def edit_employee(user_id):
    employee = User.query.get_or_404(user_id)
    if not can_manage_employee(current_user, employee):
        abort(403)

    manager_options = visible_employees_query_for(current_user).filter(
        User.is_active_employee.is_(True), User.id != employee.id
    ).all()
    team_options = _team_options_for(current_user)

    if request.method == "POST":
        form = request.form
        name = form.get("name", "").strip()
        new_role = form.get("role")

        errors = []
        if not name:
            errors.append("Name is required.")
        if new_role in (SUPER_ADMIN, ADMIN) and not current_user.is_super_admin():
            errors.append("Only a Super Admin can grant Admin/Super Admin roles.")
        new_password = form.get("password", "").strip()
        if new_password and not is_strong_enough_password(new_password):
            errors.append("New password must be at least 8 characters and include a letter and a number.")

        if errors:
            for e in errors:
                flash(e, "danger")
            current_states = employee.scoped_states() or []
            return render_template("employee_form.html", employee=employee, roles=ALL_ROLES,
                                    managers=manager_options, states=INDIAN_STATES,
                                    teams=team_options, current_states=current_states)

        employee.name = name
        employee.phone = form.get("phone", "").strip()
        employee.role = new_role
        employee.manager_id = form.get("manager_id", type=int) or None
        employee.team_id = form.get("team_id", type=int) or None
        employee.state_scope = ",".join(form.getlist("state_scope")) or None

        if new_password:
            employee.set_password(new_password)

        db.session.commit()
        flash(f"{employee.name}'s account updated.", "success")
        return redirect(url_for("employees.list_employees"))

    current_states = employee.scoped_states() or []
    return render_template("employee_form.html", employee=employee, roles=ALL_ROLES,
                            managers=manager_options, states=INDIAN_STATES,
                            teams=team_options, current_states=current_states)


@employees_bp.route("/<int:user_id>/resign", methods=["GET", "POST"])
@login_required
def resign_employee(user_id):
    """Deactivate an employee, transfer their open leads, AND re-point any
    direct reports / team-lead role so the hierarchy stays intact (Requirement
    #8: 'hierarchy should remain properly maintained even when employees leave').
    Only Super Admin can do this."""
    if not current_user.is_super_admin():
        abort(403)

    employee = User.query.get_or_404(user_id)
    if employee.id == current_user.id:
        flash("You can't deactivate your own account.", "danger")
        return redirect(url_for("employees.list_employees"))

    assigned_leads = Lead.query.filter_by(assigned_to_id=employee.id).all()
    direct_reports = User.query.filter_by(manager_id=employee.id, is_active_employee=True).all()
    led_teams = Team.query.filter_by(team_lead_id=employee.id).all()

    if request.method == "POST":
        transfer_to_id = request.form.get("transfer_to_id", type=int) or None
        transfer_to = User.query.get(transfer_to_id) if transfer_to_id else None

        # Reports/team-lead reassignment can go to the same person as the lead
        # transfer, or a different one — default to the lead-transfer pick.
        new_manager_id = request.form.get("new_manager_id", type=int) or transfer_to_id
        new_manager = User.query.get(new_manager_id) if new_manager_id else None

        if assigned_leads and transfer_to is None:
            flash("Please choose an employee to transfer the open leads to.", "danger")
            return redirect(url_for("employees.resign_employee", user_id=user_id))

        if transfer_to and not transfer_to.is_active_employee:
            flash("You can't transfer leads to an inactive employee.", "danger")
            return redirect(url_for("employees.resign_employee", user_id=user_id))

        if direct_reports and new_manager is None:
            flash(f"{employee.name} has {len(direct_reports)} direct report(s) — "
                  f"please choose who they should report to instead.", "danger")
            return redirect(url_for("employees.resign_employee", user_id=user_id))

        if new_manager and new_manager.id == employee.id:
            flash("The new manager can't be the employee who's resigning.", "danger")
            return redirect(url_for("employees.resign_employee", user_id=user_id))

        # Deactivate — this also blocks login immediately.
        employee.is_active_employee = False
        employee.resigned_at = datetime.utcnow()

        # Transfer each lead. Call logs / follow-ups already recorded keep the
        # original employee_id forever — only current responsibility (assigned_to)
        # moves, and it's captured in AssignmentHistory for a clean audit trail.
        for lead in assigned_leads:
            history = AssignmentHistory(
                lead_id=lead.id,
                from_employee_id=employee.id,
                to_employee_id=transfer_to.id,
                changed_by_id=current_user.id,
                reason=f"Task transfer: {employee.name} resigned",
            )
            lead.assigned_to_id = transfer_to.id
            lead.updated_at = datetime.utcnow()
            db.session.add(history)

        # Re-point direct reports so nobody is left reporting to a deactivated
        # account — the hierarchy chain stays unbroken.
        for report in direct_reports:
            report.manager_id = new_manager.id if new_manager else None

        # Hand off any team(s) this person led.
        for team in led_teams:
            team.team_lead_id = new_manager.id if new_manager else None

        db.session.commit()

        msg = (f"{employee.name} deactivated. "
               f"{len(assigned_leads)} lead(s) transferred to {transfer_to.name if transfer_to else 'nobody'}.")
        if direct_reports:
            msg += f" {len(direct_reports)} direct report(s) now report to {new_manager.name if new_manager else 'nobody'}."
        if led_teams:
            msg += f" Team lead role on {len(led_teams)} team(s) handed to {new_manager.name if new_manager else 'nobody'}."
        flash(msg, "success")
        return redirect(url_for("employees.list_employees"))

    transfer_options = User.query.filter(
        User.is_active_employee.is_(True), User.id != employee.id
    ).all()
    return render_template(
        "resign_employee.html", employee=employee, assigned_leads=assigned_leads,
        direct_reports=direct_reports, led_teams=led_teams,
        transfer_options=transfer_options,
    )


@employees_bp.route("/<int:user_id>/reactivate", methods=["POST"])
@login_required
def reactivate_employee(user_id):
    if not current_user.is_super_admin():
        abort(403)
    employee = User.query.get_or_404(user_id)
    employee.is_active_employee = True
    employee.resigned_at = None
    employee.failed_login_attempts = 0
    employee.locked_until = None
    db.session.commit()
    flash(f"{employee.name}'s account reactivated.", "success")
    return redirect(url_for("employees.list_employees"))
