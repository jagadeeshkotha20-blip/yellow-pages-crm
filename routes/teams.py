from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from extensions import db
from models import Team, User, Lead, CALLING_ROLES, TEAM_LEAD, SUPER_ADMIN, ADMIN
from permissions import visible_employees_query_for

teams_bp = Blueprint("teams", __name__, url_prefix="/teams")


def _can_manage_teams(user):
    return user.role in (SUPER_ADMIN, ADMIN)


@teams_bp.route("/")
@login_required
def list_teams():
    if current_user.role in (SUPER_ADMIN, ADMIN):
        teams = Team.query.order_by(Team.name).all()
    elif current_user.team_id:
        teams = Team.query.filter_by(id=current_user.team_id).all()
    else:
        teams = []

    member_counts = {t.id: User.query.filter_by(team_id=t.id, is_active_employee=True).count()
                      for t in teams}
    return render_template("teams_list.html", teams=teams, member_counts=member_counts,
                            can_manage=_can_manage_teams(current_user))


@teams_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_team():
    if not _can_manage_teams(current_user):
        abort(403)

    lead_options = User.query.filter(
        User.role.in_([TEAM_LEAD]), User.is_active_employee.is_(True)
    ).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Team name is required.", "danger")
            return render_template("team_form.html", leads=lead_options)
        if Team.query.filter_by(name=name).first():
            flash("A team with that name already exists.", "danger")
            return render_template("team_form.html", leads=lead_options)

        team_lead_id = request.form.get("team_lead_id", type=int) or None
        team = Team(name=name, team_lead_id=team_lead_id)
        db.session.add(team)
        db.session.commit()

        # If a team lead was picked, make sure their manager chain is set to admin
        # scoping stays consistent — but always let the admin adjust manually too.
        flash(f"Team '{team.name}' created.", "success")
        return redirect(url_for("teams.view_team", team_id=team.id))

    return render_template("team_form.html", leads=lead_options)


@teams_bp.route("/<int:team_id>")
@login_required
def view_team(team_id):
    team = Team.query.get_or_404(team_id)
    if current_user.role not in (SUPER_ADMIN, ADMIN) and current_user.team_id != team.id:
        abort(403)

    members = User.query.filter_by(team_id=team.id).order_by(
        User.is_active_employee.desc(), User.name
    ).all()
    lead_counts = {m.id: Lead.query.filter_by(assigned_to_id=m.id).count() for m in members}

    return render_template("team_detail.html", team=team, members=members,
                            lead_counts=lead_counts, can_manage=_can_manage_teams(current_user))


@teams_bp.route("/<int:team_id>/edit", methods=["GET", "POST"])
@login_required
def edit_team(team_id):
    if not _can_manage_teams(current_user):
        abort(403)
    team = Team.query.get_or_404(team_id)
    lead_options = User.query.filter(
        User.role.in_([TEAM_LEAD]), User.is_active_employee.is_(True)
    ).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Team name is required.", "danger")
            return render_template("team_form.html", team=team, leads=lead_options)

        existing = Team.query.filter(Team.name == name, Team.id != team.id).first()
        if existing:
            flash("A team with that name already exists.", "danger")
            return render_template("team_form.html", team=team, leads=lead_options)

        team.name = name
        team.team_lead_id = request.form.get("team_lead_id", type=int) or None
        db.session.commit()
        flash(f"Team '{team.name}' updated.", "success")
        return redirect(url_for("teams.view_team", team_id=team.id))

    return render_template("team_form.html", team=team, leads=lead_options)
