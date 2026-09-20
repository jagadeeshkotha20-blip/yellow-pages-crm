from functools import wraps
from flask import abort
from flask_login import current_user

from models import (
    User, Lead, SUPER_ADMIN, ADMIN, HR_ADMIN, TEAM_LEAD, MANAGEMENT_ROLES,
)


def role_required(*roles):
    """Restrict a view to the given roles (Super Admin always allowed)."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role == SUPER_ADMIN or current_user.role in roles:
                return view_func(*args, **kwargs)
            abort(403)
        return wrapped
    return decorator


def management_required(view_func):
    """Restrict a view to any management-tier role."""
    return role_required(*MANAGEMENT_ROLES)(view_func)


def visible_user_ids_for(user):
    """Which user IDs `user` is allowed to see leads/activity for."""
    if user.role in (SUPER_ADMIN, ADMIN, HR_ADMIN):
        return None  # None == everyone
    if user.role == TEAM_LEAD:
        return user.all_subordinate_ids(include_self=True)
    # Individual contributors (employee/telecaller/bde) only see themselves
    return {user.id}


def leads_query_for_user(user):
    """Base Lead query scoped to what this user is allowed to see."""
    query = Lead.query
    visible_ids = visible_user_ids_for(user)
    if visible_ids is not None:
        query = query.filter(Lead.assigned_to_id.in_(visible_ids))

    states = user.scoped_states()
    if states:
        query = query.filter(Lead.state.in_(states))
    return query


def can_view_lead(user, lead):
    if user.role in (SUPER_ADMIN, ADMIN, HR_ADMIN):
        return True
    if lead.assigned_to_id is None:
        # Unassigned leads are visible to anyone who could potentially claim them
        return True
    visible_ids = visible_user_ids_for(user)
    if visible_ids is None:
        return True
    return lead.assigned_to_id in visible_ids


def can_work_lead(user, lead):
    """Can this user add call logs / follow-ups / change status on this lead right now?"""
    if user.role in (SUPER_ADMIN, ADMIN, HR_ADMIN):
        return True
    if lead.assigned_to_id == user.id:
        return True
    if lead.assigned_to_id is not None:
        assignee = User.query.get(lead.assigned_to_id)
        if assignee and user.is_manager_of(assignee):
            return True
    return False


def can_manage_employee(manager, employee):
    """Can `manager` edit/deactivate/reassign-for `employee`?"""
    if manager.role == SUPER_ADMIN:
        return True
    # Nobody below Super Admin may touch an admin-tier account (Admin, HR
    # Admin, or another Super Admin) — not view its edit form, not reset its
    # password, not change anything. Only the role field being blocked isn't
    # enough on its own, since every other field on that account is reachable
    # through the same edit form.
    if employee.role in (SUPER_ADMIN, ADMIN, HR_ADMIN):
        return False
    if manager.role in (ADMIN, HR_ADMIN):
        return True
    if manager.role == TEAM_LEAD:
        return employee.id in manager.all_subordinate_ids(include_self=False)
    return False


def visible_employees_query_for(user):
    from models import User as UserModel
    if user.role in (SUPER_ADMIN, ADMIN, HR_ADMIN):
        return UserModel.query
    if user.role == TEAM_LEAD:
        ids = user.all_subordinate_ids(include_self=True)
        return UserModel.query.filter(UserModel.id.in_(ids))
    return UserModel.query.filter(UserModel.id == user.id)
