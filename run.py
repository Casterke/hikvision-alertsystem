"""Main entry: ISAPI event stream + event sampler + web UI."""
import logging
import sys
import threading
import time
from io import StringIO

# Suppress HTTPS verification warnings (NVRs often use self-signed certs)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Reduce Flask request logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)

import lxml.etree as ET
import requests
from requests.auth import HTTPDigestAuth

from src.live_feed import push_event, push_snapshots
from src.config import (
    NVR_CONNECT_TIMEOUT,
    NVR_PASS,
    NVR_RETRY_DELAY,
    NVR_STREAM_READ_TIMEOUT,
    NVR_URL,
    NVR_USR,
)
from src.db import get_enabled_channels_and_events, init_db
from src.event_sampler import sample_event_async
from src.image_process import process_event
from src.web.app import app, run_web

XML_NAMESPACE = "http://www.hikvision.com/ver20/XMLSchema"
DEFAULT_HEADERS = {
    "Content-Type": "application/xml; charset='UTF-8'",
    "Accept": "*/*",
}

# Ensure paths work when run from project root
sys.path.insert(0, ".")

print("Hikvision alert started")
init_db()

# Auto-discover channels/events on first run if empty
_enabled = get_enabled_channels_and_events()
if not _enabled:
    try:
        from src.isapi_client import discover_channels, discover_event_types
        from src.db import upsert_event_types, upsert_channels
        ets = discover_event_types()
        upsert_event_types(ets)
        chs = discover_channels()
        upsert_channels(chs)
        print("Auto-discovered channels and events from NVR")
    except Exception as e:
        print("Auto-discover failed (configure NVR in .env):", e)


def _session():
    s = requests.Session()
    s.auth = HTTPDigestAuth(NVR_USR, NVR_PASS)
    s.headers.update(DEFAULT_HEADERS)
    s.verify = False
    return s


def _on_event_complete(event_id: str, channel_id: str, snapshot_paths: list):
    """Callback when event sampling is done."""
    push_snapshots(event_id, channel_id, snapshot_paths)
    process_event(event_id, channel_id, snapshot_paths, "linedetection")


def _event_loop():
    url = NVR_URL.rstrip("/") + "/ISAPI/Event/notification/alertStream"
    parse_string = ""
    start_event = False
    fail_count = 0

    while True:
        try:
            stream = _session().get(
                url,
                stream=True,
                timeout=(NVR_CONNECT_TIMEOUT, NVR_STREAM_READ_TIMEOUT),
            )
            if stream.status_code != 200:
                print("Can't connect to the stream!")
                raise ValueError("Connection unsuccessful")
            fail_count = 0
            print("Connection successful to:", NVR_URL)

            for line in stream.iter_lines():
                if not line:
                    continue
                str_line = line.decode("utf-8")
                if "<EventNotificationAlert" in str_line:
                    start_event = True
                    parse_string += str_line
                elif "</EventNotificationAlert>" in str_line:
                    parse_string += str_line
                    start_event = False
                    if parse_string:
                        try:
                            parser = ET.XMLParser(recover=True)
                            tree = ET.parse(StringIO(parse_string), parser=parser)
                            ch = tree.find(f"{{{XML_NAMESPACE}}}channelID")
                            if ch is None:
                                ch = tree.find(f"{{{XML_NAMESPACE}}}dynChannelID")
                            if ch is None or not ch.text or ch.text == "0":
                                parse_string = ""
                                continue
                            et = tree.find(f"{{{XML_NAMESPACE}}}eventType")
                            event_type = et.text if et is not None else "linedetection"
                            channel_id = ch.text

                            enabled = get_enabled_channels_and_events()
                            if (channel_id, event_type) in enabled:
                                print("Event triggered:", event_type, "channel:", channel_id)
                                push_event(channel_id, event_type)
                                sample_event_async(channel_id, _on_event_complete)
                        except Exception as e:
                            print("Parse event error:", e)
                    parse_string = ""
                elif start_event:
                    parse_string += str_line

        except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, requests.exceptions.ReadTimeout) as e:
            fail_count += 1
            delay = fail_count * NVR_RETRY_DELAY
            print(f"Stream error (retry in {delay}s):", e)
            time.sleep(delay)


if __name__ == "__main__":
    # Start event loop in background
    t = threading.Thread(target=_event_loop, daemon=True)
    t.start()
    # Run web server in foreground
    run_web(host="0.0.0.0", port=5000)
