"""Simple auth: user/password from .env or auto-generated."""
import secrets
from functools import wraps

from flask import Flask, redirect, request, session, url_for

from src.config import WEB_PASSWORD, WEB_USER

_secrets_file = None


def _get_secrets_path():
    from pathlib import Path
    from src.config import DATA_DIR
    return Path(DATA_DIR) / ".web_secrets"


def _load_credentials():
    """Return (user, password). Generate and save if not set."""
    global _secrets_file
    if WEB_USER and WEB_PASSWORD:
        return (WEB_USER, WEB_PASSWORD)
    path = _get_secrets_path()
    _secrets_file = path
    if path.exists():
        text = path.read_text().strip()
        parts = text.split(":", 1)
        if len(parts) == 2:
            return (parts[0], parts[1])
    user = secrets.token_hex(8)
    passwd = secrets.token_hex(16)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{user}:{passwd}")
    print("=" * 50)
    print("Generated web credentials (first run):")
    print(f"  User: {user}")
    print(f"  Pass: {passwd}")
    print("=" * 50)
    return (user, passwd)


def init_auth(app: Flask):
    user, passwd = _load_credentials()

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            u = request.form.get("username", "")
            p = request.form.get("password", "")
            if u == user and p == passwd:
                session["logged_in"] = True
                return redirect(url_for("index"))
        return """
        <form method="post">
            <input name="username" placeholder="User" required><br>
            <input name="password" type="password" placeholder="Password" required><br>
            <button type="submit">Login</button>
        </form>
        """

    @app.route("/logout")
    def logout():
        session.pop("logged_in", None)
        return redirect(url_for("login"))

    def login_required(f):
        @wraps(f)
        def inner(*a, **k):
            if not session.get("logged_in"):
                return redirect(url_for("login"))
            return f(*a, **k)
        return inner

    app.login_required = login_required
