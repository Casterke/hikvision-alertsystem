"""Flask web application."""
from flask import Flask, redirect, render_template_string, request, url_for

from src.config import DATA_DIR
from src.db import (
    _conn,
    get_enabled_object_classes,
    init_db,
    COCO_CLASSES,
)
from src.isapi_client import discover_channels, discover_event_types
from src.web.auth import init_auth

app = Flask(__name__)
app.secret_key = "change-me-in-production"
init_db()
init_auth(app)


INDEX_HTML = """
<!DOCTYPE html>
<html><head><title>Hikvision Alerts</title>
<style>body{font-family:sans-serif;margin:2em;} nav a{margin-right:1em;}</style></head>
<body>
<nav><a href="/">Dashboard</a> <a href="/channels">Channels</a> <a href="/events">Events</a> 
<a href="/objects">Objects</a> <a href="/faces">Faces</a> <a href="/settings">Settings</a>
<a href="/logout">Logout</a></nav>
<h1>Dashboard</h1>
<p>Hikvision Alert System. Configure channels, events, and objects above.</p>
</body></html>
"""


@app.route("/")
@app.login_required
def index():
    return render_template_string(INDEX_HTML)


CHANNELS_HTML = """
<!DOCTYPE html>
<html><head><title>Channels</title>
<style>body{font-family:sans-serif;margin:2em;} table{border-collapse:collapse;}
td,th{border:1px solid #ccc;padding:6px;} nav a{margin-right:1em;}</style></head>
<body>
<nav><a href="/">Dashboard</a> <a href="/channels">Channels</a> <a href="/events">Events</a> 
<a href="/objects">Objects</a> <a href="/faces">Faces</a> <a href="/settings">Settings</a>
<a href="/logout">Logout</a></nav>
<h1>Channels</h1>
<form method="post" action="/channels/refresh"><button>Refresh from NVR</button></form>
<table><tr><th>ID</th><th>Name</th><th>Enabled</th></tr>
{% for c in channels %}
<tr><td>{{ c.hik_id }}</td><td>{{ c.name }}</td>
<td><form method="post" action="/channels/{{ c.id }}/toggle" style="display:inline">
<button>{{ 'Disable' if c.enabled else 'Enable' }}</button></form></td></tr>
{% endfor %}
</table>
</body></html>
"""


@app.route("/channels", methods=["GET"])
@app.login_required
def channels():
    with _conn() as conn:
        cur = conn.execute("SELECT id, hik_id, name, enabled FROM channels ORDER BY hik_id")
        channels = [dict(r) for r in cur.fetchall()]
    return render_template_string(CHANNELS_HTML, channels=channels)


@app.route("/channels/refresh", methods=["POST"])
@app.login_required
def channels_refresh():
    chs = discover_channels()
    ets = discover_event_types()
    from src.db import upsert_event_types, upsert_channels
    upsert_event_types(ets)
    upsert_channels(chs)
    return redirect(url_for("channels"))


@app.route("/channels/<int:cid>/toggle", methods=["POST"])
@app.login_required
def channel_toggle(cid):
    with _conn() as conn:
        cur = conn.execute("SELECT enabled FROM channels WHERE id=?", (cid,))
        r = cur.fetchone()
        if r:
            new = 0 if r["enabled"] else 1
            conn.execute("UPDATE channels SET enabled=? WHERE id=?", (new, cid))
    return redirect(url_for("channels"))


EVENTS_HTML = """
<!DOCTYPE html>
<html><head><title>Events</title>
<style>body{font-family:sans-serif;margin:2em;} table{border-collapse:collapse;}
td,th{border:1px solid #ccc;padding:6px;} nav a{margin-right:1em;}</style></head>
<body>
<nav><a href="/">Dashboard</a> <a href="/channels">Channels</a> <a href="/events">Events</a> 
<a href="/objects">Objects</a> <a href="/faces">Faces</a> <a href="/settings">Settings</a>
<a href="/logout">Logout</a></nav>
<h1>Event Types</h1>
<table><tr><th>Name</th><th>Enabled</th></tr>
{% for e in events %}
<tr><td>{{ e.name }}</td>
<td><form method="post" action="/events/{{ e.id }}/toggle" style="display:inline">
<button>{{ 'Disable' if e.enabled else 'Enable' }}</button></form></td></tr>
{% endfor %}
</table>
</body></html>
"""


@app.route("/events", methods=["GET"])
@app.login_required
def events():
    with _conn() as conn:
        cur = conn.execute("SELECT id, name, enabled FROM event_types ORDER BY name")
        events = [dict(r) for r in cur.fetchall()]
    return render_template_string(EVENTS_HTML, events=events)


@app.route("/events/<int:eid>/toggle", methods=["POST"])
@app.login_required
def event_toggle(eid):
    with _conn() as conn:
        cur = conn.execute("SELECT enabled FROM event_types WHERE id=?", (eid,))
        r = cur.fetchone()
        if r:
            new = 0 if r["enabled"] else 1
            conn.execute("UPDATE event_types SET enabled=? WHERE id=?", (new, eid))
            # Ensure channel_events exists for all channels when enabling
            if new:
                for row in conn.execute("SELECT id FROM channels WHERE enabled=1"):
                    conn.execute(
                        "INSERT OR IGNORE INTO channel_events (channel_id, event_type_id, enabled) VALUES (?, ?, 1)",
                        (row["id"], eid)
                    )
    return redirect(url_for("events"))


OBJECTS_HTML = """
<!DOCTYPE html>
<html><head><title>Objects</title>
<style>body{font-family:sans-serif;margin:2em;} label{display:block;margin:4px 0;}
nav a{margin-right:1em;}</style></head>
<body>
<nav><a href="/">Dashboard</a> <a href="/channels">Channels</a> <a href="/events">Events</a> 
<a href="/objects">Objects</a> <a href="/faces">Faces</a> <a href="/settings">Settings</a>
<a href="/logout">Logout</a></nav>
<h1>Object Classes (YOLO)</h1>
<form method="post">
{% for c in classes %}
<label><input type="checkbox" name="obj" value="{{ c.name }}" {{ 'checked' if c.enabled else '' }}>
{{ c.name }}</label>
{% endfor %}
<button type="submit">Save</button>
</form>
</body></html>
"""


@app.route("/objects", methods=["GET", "POST"])
@app.login_required
def objects():
    if request.method == "POST":
        enabled = set(request.form.getlist("obj"))
        with _conn() as conn:
            for name in COCO_CLASSES:
                conn.execute(
                    "UPDATE object_classes SET enabled=? WHERE name=?",
                    (1 if name in enabled else 0, name)
                )
        return redirect(url_for("objects"))
    with _conn() as conn:
        cur = conn.execute("SELECT id, name, enabled FROM object_classes ORDER BY id")
        classes = [dict(r) for r in cur.fetchall()]
    return render_template_string(OBJECTS_HTML, classes=classes)


FACES_HTML = """
<!DOCTYPE html>
<html><head><title>Known Faces</title>
<style>body{font-family:sans-serif;margin:2em;} table{border-collapse:collapse;}
td,th{border:1px solid #ccc;padding:6px;} nav a{margin-right:1em;}</style></head>
<body>
<nav><a href="/">Dashboard</a> <a href="/channels">Channels</a> <a href="/events">Events</a> 
<a href="/objects">Objects</a> <a href="/faces">Faces</a> <a href="/settings">Settings</a>
<a href="/logout">Logout</a></nav>
<h1>Face Recognition Library</h1>
<form method="post" enctype="multipart/form-data" action="/faces/add">
  <input type="text" name="name" placeholder="Name" required>
  <input type="file" name="photo" accept="image/*" required>
  <button type="submit">Add Face</button>
</form>
<table><tr><th>Name</th><th>Actions</th></tr>
{% for f in faces %}
<tr><td>{{ f.name }}</td>
<td><form method="post" action="/faces/{{ f.id }}/delete" style="display:inline">
<button>Delete</button></form></td></tr>
{% endfor %}
</table>
</body></html>
"""


@app.route("/faces", methods=["GET"])
@app.login_required
def faces():
    with _conn() as conn:
        cur = conn.execute("SELECT id, name FROM known_faces ORDER BY name")
        faces_list = [dict(r) for r in cur.fetchall()]
    return render_template_string(FACES_HTML, faces=faces_list)


@app.route("/faces/add", methods=["POST"])
@app.login_required
def faces_add():
    name = request.form.get("name", "").strip()
    f = request.files.get("photo")
    if name and f and f.filename:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
            f.save(tf.name)
            from src.face_rec import add_known_face
            if add_known_face(name, tf.name):
                import os
                os.unlink(tf.name)
    return redirect(url_for("faces"))


@app.route("/faces/<int:fid>/delete", methods=["POST"])
@app.login_required
def faces_delete(fid):
    with _conn() as conn:
        conn.execute("DELETE FROM known_faces WHERE id=?", (fid,))
    return redirect(url_for("faces"))


SETTINGS_HTML = """
<!DOCTYPE html>
<html><head><title>Settings</title>
<style>body{font-family:sans-serif;margin:2em;} nav a{margin-right:1em;}</style></head>
<body>
<nav><a href="/">Dashboard</a> <a href="/channels">Channels</a> <a href="/events">Events</a> 
<a href="/objects">Objects</a> <a href="/faces">Faces</a> <a href="/settings">Settings</a>
<a href="/logout">Logout</a></nav>
<h1>Settings</h1>
<p>NVR URL, credentials, and notification settings are in .env</p>
</body></html>
"""


@app.route("/settings", methods=["GET"])
@app.login_required
def settings():
    return render_template_string(SETTINGS_HTML)


def run_web(host="0.0.0.0", port=5000):
    app.run(host=host, port=port, debug=False)
