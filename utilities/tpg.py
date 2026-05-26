import json


def _normalize_entry(tag, param, guid):
    return {
        "t": (tag or "").strip(),
        "p": "" if param is None else str(param).strip(),
        "g": "" if guid is None else str(guid).strip(),
    }


def tpg_decode(raw_value):
    """Decode a GUID metadata payload into `(entries, legacy_single)`.

    Canonical payload:
      {"v": 1, "entries": [{"t": "IfcWall", "p": "", "g": "..."}]}

    Legacy payloads still accepted:
    - Plain GUID string
    - JSON map: {"IfcWall": "...", "IfcSlab": "..."}
    - Delimited map: IfcWall=...;IfcSlab=... (also supports ':' and '|')
    """
    text = (raw_value or "").strip()
    if not text:
        return [], ""

    # JSON-based payloads
    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                entries = []
                if isinstance(obj.get("entries"), list):
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
                    if entries:
                        return entries, ""

                # Legacy JSON map: {tag: guid}
                for key, value in obj.items():
                    if key in {"v", "entries"}:
                        continue
                    entry = _normalize_entry(key, "", value)
                    if entry["t"]:
                        entries.append(entry)
                if entries:
                    return entries, ""
        except Exception:
            pass

    # Delimited legacy map: tag=value;tag2=value2 or tag:value
    parsed = []
    for part in text.replace("|", ";").split(";"):
        token = part.strip()
        if not token:
            continue
        if "=" in token:
            key, value = token.split("=", 1)
        elif ":" in token:
            key, value = token.split(":", 1)
        else:
            continue
        entry = _normalize_entry(key, "", value)
        if entry["t"]:
            parsed.append(entry)
    if parsed:
        return parsed, ""

    # Plain legacy single GUID
    return [], text


def tpg_to_map(raw_value):
    entries, _legacy_single = tpg_decode(raw_value)
    result = {}
    for entry in entries:
        tag = entry["t"]
        if tag not in result:
            result[tag] = entry["g"]
    return result


def tpg_get_guid(raw_value, tag=None):
    entries, legacy_single = tpg_decode(raw_value)

    if tag:
        tag = (tag or "").strip()
        for entry in entries:
            if entry["t"] == tag:
                return entry["g"]
        return legacy_single

    for entry in entries:
        if entry["g"]:
            return entry["g"]
    return legacy_single
