"""Flask entrypoint for the outbound sales automation web app."""

from __future__ import annotations

import os

from flask import Flask
from flask_login import LoginManager

from auth import auth_bp, load_user
from config import FLASK_SECRET_KEY
from routes.actions import actions_bp
from routes.main import main_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = FLASK_SECRET_KEY

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def _user_loader(user_id):
        return load_user(user_id)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(actions_bp)

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
