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
