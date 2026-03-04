"""Hikvision ISAPI client for autodiscovering channels and event types."""
import time
import xml.etree.ElementTree as ET
from io import StringIO
from typing import List, Optional

import requests
from requests.auth import HTTPDigestAuth

from src.config import (
    NVR_CHANNELS,
    NVR_CONNECT_TIMEOUT,
    NVR_PASS,
    NVR_READ_TIMEOUT,
    NVR_RETRIES,
    NVR_RETRY_DELAY,
    NVR_URL,
    NVR_USR,
)

XML_NAMESPACE = "http://www.hikvision.com/ver20/XMLSchema"
DEFAULT_HEADERS = {
    "Content-Type": "application/xml; charset='UTF-8'",
    "Accept": "*/*",
}


def _session():
    s = requests.Session()
    s.auth = HTTPDigestAuth(NVR_USR, NVR_PASS)
    s.headers.update(DEFAULT_HEADERS)
    s.verify = False
    return s


def _get(path: str) -> Optional[str]:
    """GET XML from NVR, return text or None. Retries with backoff."""
    url = NVR_URL.rstrip("/") + path
    timeout = (NVR_CONNECT_TIMEOUT, NVR_READ_TIMEOUT)
    for attempt in range(NVR_RETRIES):
        try:
            r = _session().get(url, timeout=timeout)
            if r.status_code == 200:
                return r.text
        except Exception as e:
            if attempt < NVR_RETRIES - 1:
                delay = NVR_RETRY_DELAY * (attempt + 1)
                print(f"ISAPI GET retry {attempt + 1}/{NVR_RETRIES} in {delay}s: {e}")
                time.sleep(delay)
            else:
                print("ISAPI GET error:", e)
    return None


def discover_channels() -> List[dict]:
    """
    Discover available streaming channels.
    Tries /ISAPI/Streaming/channels and /ISAPI/ContentMgmt/InputProxy/channels.
    """
    channels = []
    # Try streaming channels first (common for NVR)
    xml = _get("/ISAPI/Streaming/channels")
    if xml:
        channels = _parse_streaming_channels(xml)
    if not channels:
        xml = _get("/ISAPI/ContentMgmt/InputProxy/channels")
        if xml:
            channels = _parse_input_proxy_channels(xml)
    # Fallback: if no discovery works, assume channels 1 to NVR_CHANNELS
    if not channels:
        for i in range(1, NVR_CHANNELS + 1):
            channels.append({"hik_id": str(i), "name": f"Channel {i}", "enabled": True})
    return channels


def _parse_streaming_channels(xml: str) -> List[dict]:
    """Parse Streaming/channels response."""
    result = []
    try:
        root = ET.fromstring(xml)
        ns = {"t": XML_NAMESPACE}
        for ch in root.findall(".//t:StreamingChannel", namespaces=ns) or root.findall(".//StreamingChannel"):
            id_elem = ch.find("t:id", ns) or ch.find("id")
            name_elem = ch.find("t:channelName", ns) or ch.find("channelName")
            ena = ch.find("t:enabled", ns) or ch.find("enabled")
            if id_elem is not None and id_elem.text:
                # Channel ID format: 101 = main stream ch1, 102 = sub ch1
                ch_id = id_elem.text
                if len(ch_id) >= 2:
                    base_id = ch_id[: len(ch_id) - 2] or ch_id[0]
                else:
                    base_id = ch_id
                result.append({
                    "hik_id": base_id,
                    "name": (name_elem.text if name_elem is not None else "") or f"Channel {base_id}",
                    "enabled": (ena.text or "true").lower() == "true",
                })
    except ET.ParseError as e:
        print("Parse streaming channels error:", e)
    return result


def _parse_input_proxy_channels(xml: str) -> List[dict]:
    """Parse ContentMgmt/InputProxy/channels response."""
    result = []
    try:
        root = ET.fromstring(xml)
        ns = {"t": XML_NAMESPACE}
        for ch in root.findall(".//t:InputProxyChannel", ns) or root.findall(".//InputProxyChannel"):
            id_elem = ch.find("t:id", ns) or ch.find("id", ns)
            name_elem = ch.find("t:name", ns) or ch.find("name", ns)
            if id_elem is not None and id_elem.text:
                result.append({
                    "hik_id": id_elem.text,
                    "name": (name_elem.text if name_elem is not None else "") or f"Channel {id_elem.text}",
                    "enabled": True,
                })
    except ET.ParseError as e:
        print("Parse input proxy channels error:", e)
    return result


def discover_event_types() -> List[str]:
    """
    Discover available event types from triggers or triggersCap.
    """
    event_types = set()
    # triggers
    xml = _get("/ISAPI/Event/triggers")
    if xml:
        event_types.update(_parse_event_triggers(xml))
    xml = _get("/ISAPI/Event/triggersCap")
    if xml:
        event_types.update(_parse_event_triggers_cap(xml))
    if not event_types:
        event_types = {"linedetection", "motion", "videoloss", "tamperdetection"}
    return sorted(event_types)


def _parse_event_triggers(xml: str) -> set:
    result = set()
    try:
        root = ET.fromstring(xml)
        ns = {"t": XML_NAMESPACE}
        for elem in root.findall(".//t:eventType", ns) or root.findall(".//eventType"):
            if elem.text:
                result.add(elem.text.strip())
    except ET.ParseError:
        pass
    return result


def _parse_event_triggers_cap(xml: str) -> set:
    result = set()
    try:
        root = ET.fromstring(xml)
        ns = {"t": XML_NAMESPACE}
        for elem in root.findall(".//t:eventType", ns) or root.findall(".//eventType"):
            if elem.text:
                result.add(elem.text.strip())
    except ET.ParseError:
        pass
    return result


def download_snapshot(channel_id: str) -> Optional[bytes]:
    """Download a snapshot image for the given channel.
    URL format: /ISAPI/Streaming/channels/{id}/picture e.g. 301 for channel 3.
    """
    # Channel format: 301 = channel 3 main, 101 = channel 1 main (channel*100+1)
    if channel_id.isdigit():
        n = int(channel_id)
        stream_id = str(n * 100 + 1) if n < 100 else channel_id
    else:
        stream_id = f"{channel_id}01"
    url = (
        NVR_URL.rstrip("/")
        + f"/ISAPI/Streaming/channels/{stream_id}/picture?"
        "videoResolutionWidth=640&videoResolutionHeight=480"
    )
    timeout = (NVR_CONNECT_TIMEOUT, NVR_READ_TIMEOUT)
    for attempt in range(NVR_RETRIES):
        try:
            r = _session().get(url, timeout=timeout)
            if r.status_code == 200:
                return r.content
        except Exception as e:
            if attempt < NVR_RETRIES - 1:
                delay = NVR_RETRY_DELAY * (attempt + 1)
                print(f"Snapshot retry {attempt + 1}/{NVR_RETRIES} in {delay}s: {e}")
                time.sleep(delay)
            else:
                print("Snapshot download error:", e)
    return None
