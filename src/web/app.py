"""Flask web application."""
import json

from flask import Flask, Response, redirect, render_template_string, request, send_from_directory, url_for

from src.config import DATA_DIR
from src.live_feed import get_feed
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
<nav><a href="/">Dashboard</a> <a href="/live">Live</a> <a href="/channels">Channels</a> <a href="/events">Events</a> 
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


@app.route("/live")
@app.login_required
def live():
    return render_template_string(LIVE_HTML)


@app.route("/live/updates")
@app.login_required
def live_updates():
    return Response(json.dumps(get_feed()), mimetype="application/json")


@app.route("/events/snapshot/<event_id>/<path:filename>")
@app.login_required
def event_snapshot(event_id, filename):
    """Serve event snapshot image."""
    events_dir = DATA_DIR / "events" / event_id
    path = events_dir / filename
    if path.exists():
        return send_from_directory(str(events_dir), filename, mimetype="image/jpeg")
    return "", 404


LIVE_HTML = """
<!DOCTYPE html>
<html><head><title>Live</title>
<style>body{font-family:sans-serif;margin:2em;} nav a{margin-right:1em;}
#events{max-height:200px;overflow-y:auto;border:1px solid #ccc;padding:8px;font-family:monospace;font-size:12px;}
#snapshots{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;}
.snap-img{max-width:320px;max-height:180px;object-fit:contain;border:1px solid #ccc;}
.snap-group{display:inline-block;margin:8px;}</style></head>
<body>
<nav><a href="/">Dashboard</a> <a href="/live">Live</a> <a href="/channels">Channels</a> <a href="/events">Events</a> 
<a href="/objects">Objects</a> <a href="/faces">Faces</a> <a href="/settings">Settings</a>
<a href="/logout">Logout</a></nav>
<h1>Live Feed</h1>
<p>Auto-refreshes every 2s</p>
<h2>Recent Events</h2>
<div id="events"><em>Loading...</em></div>
<h2>Latest Snapshots</h2>
<div id="snapshots"><em>Loading...</em></div>
<script>
function refresh(){
  fetch('/live/updates').then(r=>r.json()).then(data=>{
    var ev = document.getElementById('events');
    ev.innerHTML = data.events.length ? data.events.slice().reverse().map(e =>
      e.time + ' | Ch ' + e.channel_id + ' | ' + e.event_type
    ).join('\\n') : 'No events yet';
    ev.style.whiteSpace = 'pre-wrap';
    var snap = document.getElementById('snapshots');
    if (!data.snapshots.length) { snap.innerHTML = 'No snapshots yet'; return; }
    var html = '';
    data.snapshots.slice().reverse().forEach(s=>{
      html += '<div class="snap-group"><div>' + s.time + ' | Ch ' + s.channel_id + '</div>';
      s.files.forEach(f=>{
        html += '<img class="snap-img" src="/events/snapshot/' + s.event_id + '/' + f + '" alt="">';
      });
      html += '</div>';
    });
    snap.innerHTML = html;
  }).catch(()=>{});
}
refresh();
setInterval(refresh, 2000);
</script>
</body></html>
"""


CHANNELS_HTML = """
<!DOCTYPE html>
<html><head><title>Channels</title>
<style>body{font-family:sans-serif;margin:2em;} table{border-collapse:collapse;}
td,th{border:1px solid #ccc;padding:6px;} nav a{margin-right:1em;}
.channel-img{max-width:320px;max-height:180px;object-fit:contain;border:1px solid #ccc;}</style></head>
<body>
<nav><a href="/">Dashboard</a> <a href="/live">Live</a> <a href="/channels">Channels</a> <a href="/events">Events</a> 
<a href="/objects">Objects</a> <a href="/faces">Faces</a> <a href="/settings">Settings</a>
<a href="/logout">Logout</a></nav>
<h1>Channels</h1>
<form method="post" action="/channels/refresh" style="display:inline"><button>Refresh from NVR</button></form>
<form method="post" action="/channels/refresh-images" style="display:inline"><button>Update images</button></form>
<table><tr><th>Preview</th><th>ID</th><th>Name</th><th>Enabled</th></tr>
{% for c in channels %}
<tr>
<td><img class="channel-img" src="/channels/screenshot/{{ c.hik_id }}" alt="Ch {{ c.hik_id }}" onerror="this.style.display='none'"></td>
<td>{{ c.hik_id }}</td><td>{{ c.name }}</td>
<td><form method="post" action="/channels/{{ c.id }}/toggle" style="display:inline">
<button>{{ 'Disable' if c.enabled else 'Enable' }}</button></form></td>
</tr>
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
    from src.isapi_client import download_snapshot
    upsert_event_types(ets)
    upsert_channels(chs)
    # Download screenshots for each channel
    channels_dir = DATA_DIR / "channels"
    channels_dir.mkdir(exist_ok=True)
    for ch in chs:
        hik_id = ch["hik_id"]
        content = download_snapshot(hik_id)
        if content:
            (channels_dir / f"{hik_id}.jpg").write_bytes(content)
    return redirect(url_for("channels"))


@app.route("/channels/refresh-images", methods=["POST"])
@app.login_required
def channels_refresh_images():
    """Update screenshots only (no channel discovery)."""
    from src.isapi_client import download_snapshot
    channels_dir = DATA_DIR / "channels"
    channels_dir.mkdir(exist_ok=True)
    with _conn() as conn:
        cur = conn.execute("SELECT hik_id FROM channels ORDER BY hik_id")
        for row in cur.fetchall():
            hik_id = row["hik_id"]
            content = download_snapshot(hik_id)
            if content:
                (channels_dir / f"{hik_id}.jpg").write_bytes(content)
    return redirect(url_for("channels"))


@app.route("/channels/screenshot/<hik_id>")
@app.login_required
def channel_screenshot(hik_id):
    """Serve channel screenshot image."""
    channels_dir = DATA_DIR / "channels"
    path = channels_dir / f"{hik_id}.jpg"
    if path.exists():
        return send_from_directory(str(channels_dir), f"{hik_id}.jpg", mimetype="image/jpeg")
    return "", 404


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
<nav><a href="/">Dashboard</a> <a href="/live">Live</a> <a href="/channels">Channels</a> <a href="/events">Events</a> 
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
<nav><a href="/">Dashboard</a> <a href="/live">Live</a> <a href="/channels">Channels</a> <a href="/events">Events</a> 
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
<nav><a href="/">Dashboard</a> <a href="/live">Live</a> <a href="/channels">Channels</a> <a href="/events">Events</a> 
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
<nav><a href="/">Dashboard</a> <a href="/live">Live</a> <a href="/channels">Channels</a> <a href="/events">Events</a> 
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
