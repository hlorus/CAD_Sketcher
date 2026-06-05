import json


def _normalize_entry(tag, param, guid):
    return {
        "t": (tag or "").strip(),
        "p": "" if param is None else str(param).strip(),
        "g": "" if guid is None else str(guid).strip(),
    }


def tpg_decode(raw_value):
    """Decode a structured TPG payload into `(entries, "")`.

    Canonical payload:
      {"v": 1, "entries": [{"t": "IfcWall", "p": "", "g": "..."}]}
    """
    text = (raw_value or "").strip()
    if not text:
        return [], ""

    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
        except Exception:
            return [], ""

        if isinstance(obj, dict) and isinstance(obj.get("entries"), list):
            entries = []
            for item in obj["entries"]:
                if not isinstance(item, dict):
                    continue
                entry = _normalize_entry(
                    item.get("t") or item.get("tag"),
                    item.get("p") or item.get("param") or "",
                    item.get("g") or item.get("guid") or "",
                )
                if entry["t"]:
                    entries.append(entry)
            return entries, ""

    return [], ""


def tpg_encode(entries):
    normalized = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        normalized_entry = _normalize_entry(
            entry.get("t") or entry.get("tag"),
            entry.get("p") or entry.get("param") or "",
            entry.get("g") or entry.get("guid") or "",
        )
        if normalized_entry["t"]:
            normalized.append(normalized_entry)

    if not normalized:
        return ""

    return json.dumps({"v": 1, "entries": normalized}, separators=(",", ":"))


def tpg_entry_get(raw_value, tag):
    tag = (tag or "").strip()
    if not tag:
        return None

    entries, _unused = tpg_decode(raw_value)
    for entry in entries:
        if entry["t"] == tag:
            return entry
    return None


def tpg_entry_upsert(raw_value, tag, param=None, guid=None):
    tag = (tag or "").strip()
    if not tag:
        return (raw_value or "").strip()

    entries, _unused = tpg_decode(raw_value)
    for entry in entries:
        if entry["t"] != tag:
            continue
        if param is not None:
            entry["p"] = "" if param is None else str(param).strip()
        if guid is not None:
            entry["g"] = "" if guid is None else str(guid).strip()
        return tpg_encode(entries)

    entries.append(_normalize_entry(tag, param or "", guid or ""))
    return tpg_encode(entries)


def tpg_entry_remove(raw_value, tag):
    tag = (tag or "").strip()
    if not tag:
        return (raw_value or "").strip()

    entries, _unused = tpg_decode(raw_value)
    filtered = [entry for entry in entries if entry["t"] != tag]
    return tpg_encode(filtered)


def tpg_param_decode(raw_value):
    text = (raw_value or "").strip()
    if not text:
        return {}

    try:
        value = json.loads(text)
    except Exception:
        return {}

    return value if isinstance(value, dict) else {}


def tpg_param_encode(data):
    if not isinstance(data, dict) or not data:
        return ""
    return json.dumps(data, separators=(",", ":"), sort_keys=True)


def tpg_to_map(raw_value):
    entries, _unused = tpg_decode(raw_value)
    result = {}
    for entry in entries:
        tag = entry["t"]
        if tag not in result:
            result[tag] = entry["g"]
    return result


def tpg_get_guid(raw_value, tag=None):
    entries, _unused = tpg_decode(raw_value)

    if tag:
        tag = (tag or "").strip()
        for entry in entries:
            if entry["t"] == tag:
                return entry["g"]
        return ""

    for entry in entries:
        if entry["g"]:
            return entry["g"]
    return ""
