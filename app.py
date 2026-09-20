import os
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template
from flask_login import current_user

from config import get_config, assert_production_ready
from extensions import db, login_manager, csrf, migrate


def create_app(config_class=None):
    app = Flask(__name__)
    config_class = config_class or get_config()
    app.config.from_object(config_class)
    assert_production_ready(app.config)

    os.makedirs(os.path.join(app.root_path, "instance"), exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    _configure_logging(app)

    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.leads import leads_bp
    from routes.employees import employees_bp
    from routes.bulk_upload import bulk_bp
    from routes.teams import teams_bp
    from routes.reports import reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(leads_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(bulk_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(reports_bp)

    @app.context_processor
    def inject_globals():
        from models import ROLE_LABELS
        return dict(ROLE_LABELS=ROLE_LABELS)

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403,
                                message="You don't have permission to view this page."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404,
                                message="That page doesn't exist."), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template("error.html", code=413,
                                message="That file is too large (25 MB max)."), 413

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("Unhandled server error")
        return render_template("error.html", code=500,
                                message="Something went wrong on our end. It's been logged."), 500

    # NOTE: table creation is intentionally NOT done here. Doing it as a side
    # effect of create_app() used to collide with `flask db upgrade`/`migrate`
    # (Flask's CLI also calls create_app() just to load the app, which was
    # racing Alembic to create the same tables). Schema setup now always goes
    # through one explicit path: `python seed.py` for a first-time local setup
    # (it calls db.create_all() itself, safely — see seed.py), or
    # `flask db upgrade` for production, which seed.py also works fine after.

    return app


def _configure_logging(app):
    log_dir = os.path.join(app.root_path, "logs")
    os.makedirs(log_dir, exist_ok=True)
    handler = RotatingFileHandler(
        os.path.join(log_dir, "crm.log"), maxBytes=1_000_000, backupCount=5
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    ))
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)


if __name__ == "__main__":
    app = create_app()
    debug_mode = app.config.get("FLASK_ENV") != "production"
    app.run(debug=debug_mode, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
