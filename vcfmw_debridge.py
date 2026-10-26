# -*- coding: utf-8 -*-
#
# vcfmw_debridge.py - WeeChat script
#
# Rewrites messages from the ccmpbot bridge bot in #vcfmw so they appear
# to come directly from the bridged user, hiding the bot's own nick.

import json
import re
import weechat

SCRIPT_NAME = "vcfmw_debridge"
SCRIPT_AUTHOR = "zdykstra"
SCRIPT_VERSION = "1.1.0"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Rewrite ccmpbot bridge messages in #vcfmw/#shadytel-vcfmw to appear from the bridged user"

BOT_NICK = "ccmpbot"
TARGET_CHANNELS = ("#vcfmw", "#shadytel-vcfmw")

# Matches the bot's nick tag, allowing IRC fallback suffixes (e.g. ccmpbot`, ccmpbot_)
BOT_NICK_TAG_RE = re.compile(r"^nick_" + re.escape(BOT_NICK) + r"[`_^|\-\[\]{}\\0-9]*$", re.IGNORECASE)

# Matches: <Nick> rest of message
BRIDGE_RE = re.compile(r"^<([^>]+)>\s?(.*)$")

# Strips non-ASCII characters (e.g. emoji) from bridged display names
NICK_FILTER_RE = re.compile(r"[^\x20-\x7E]+")

# Matches the bot's long-message form: <preview>... https://paste.gg/p/<user>/<id>
PASTE_RE = re.compile(r"^(.*)\.\.\. https://paste\.gg/p/[^/\s]+/([0-9a-f]{32})$")
PASTE_API = "https://api.paste.gg/v1/pastes/%s?full=true"
PASTE_TIMEOUT_MS = 10 * 1000

# Marks lines we print ourselves so print_cb leaves them alone
PASTE_TAG = "vcfmw_debridge_paste"

# Rejects control characters other than tab and newline
PASTE_TEXT_RE = re.compile(r"^[^\x00-\x08\x0b-\x1f\x7f]*$")

OPTIONS = {
    "max_lines": ("10", "maximum lines in a paste.gg paste to inline as messages"),
    "max_chars": ("1500", "maximum characters in a paste.gg paste to inline as messages"),
}

# Paste fetches in flight, keyed by the string passed as callback data
pending_pastes = {}
pending_seq = 0


def get_int_option(name):
    try:
        return int(weechat.config_get_plugin(name))
    except ValueError:
        return int(OPTIONS[name][0])


def normalize_ws(text):
    return " ".join(text.split())


def extract_paste_lines(body, preview):
    try:
        files = json.loads(body)["result"]["files"]
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(files, list) or len(files) != 1:
        return None
    content = files[0].get("content") or {}
    if content.get("format") != "text":
        return None

    text = (content.get("value") or "").rstrip("\n")
    if not text or not PASTE_TEXT_RE.match(text):
        return None
    lines = text.split("\n")
    if len(lines) > get_int_option("max_lines") or len(text) > get_int_option("max_chars"):
        return None

    # The paste must be the full version of the previewed message
    if not normalize_ws(text).startswith(normalize_ws(preview)):
        return None
    return lines


def paste_fetch_cb(data, command, return_code, out, err):
    ctx = pending_pastes.get(data)
    if ctx is None:
        return weechat.WEECHAT_RC_OK
    ctx["out"] += out
    if return_code == weechat.WEECHAT_HOOK_PROCESS_RUNNING:
        return weechat.WEECHAT_RC_OK
    del pending_pastes[data]

    lines = None
    if return_code == 0:
        lines = extract_paste_lines(ctx["out"], ctx["preview"])
    if lines is None:
        lines = [ctx["fallback"]]
    for line in lines:
        weechat.prnt_date_tags(ctx["buffer"], 0, ctx["tags"], ctx["prefix"] + "\t" + line)
    return weechat.WEECHAT_RC_OK


def start_paste_fetch(paste_id, preview, buffer_pointer, prefix, nick, tags, fallback):
    global pending_seq
    pending_seq += 1
    key = str(pending_seq)

    new_tags = [t for t in tags.split(",") if t and not BOT_NICK_TAG_RE.match(t)]
    new_tags += ["nick_" + nick, PASTE_TAG]
    pending_pastes[key] = {
        "buffer": buffer_pointer,
        "prefix": prefix,
        "tags": ",".join(new_tags),
        "preview": preview,
        "fallback": fallback,
        "out": "",
    }
    weechat.hook_process_hashtable("url:" + PASTE_API % paste_id, {},
                                   PASTE_TIMEOUT_MS, "paste_fetch_cb", key)


def print_cb(data, modifier, modifier_data, string):
    # modifier_data is "buffer_pointer;tags"
    parts = modifier_data.split(";", 1)
    if len(parts) < 2:
        return string
    buffer_pointer, tags = parts[0], parts[1]

    tag_list = tags.split(",")
    if PASTE_TAG in tag_list:
        return string
    if not any(BOT_NICK_TAG_RE.match(t) for t in tag_list):
        return string

    buffer_full_name = weechat.buffer_get_string(buffer_pointer, "full_name")
    if not buffer_full_name.endswith(TARGET_CHANNELS):
        return string

    if "\t" not in string:
        return string
    prefix, message = string.split("\t", 1)

    match = BRIDGE_RE.match(message)
    if not match:
        return string

    real_nick, real_message = match.groups()
    filtered_nick = NICK_FILTER_RE.sub("", real_nick).strip() or real_nick
    new_prefix = weechat.info_get("nick_color", filtered_nick) + filtered_nick + weechat.color("reset")

    # Hide the truncated preview; the full paste is printed once fetched
    paste_match = PASTE_RE.match(real_message.strip())
    if paste_match:
        preview, paste_id = paste_match.groups()
        start_paste_fetch(paste_id, preview, buffer_pointer, new_prefix,
                          filtered_nick, tags, real_message)
        return ""

    return new_prefix + "\t" + real_message


if __name__ == "__main__":
    weechat.register(
        SCRIPT_NAME,
        SCRIPT_AUTHOR,
        SCRIPT_VERSION,
        SCRIPT_LICENSE,
        SCRIPT_DESC,
        "",
        "",
    )
    for option, (default, desc) in OPTIONS.items():
        if not weechat.config_is_set_plugin(option):
            weechat.config_set_plugin(option, default)
        weechat.config_set_desc_plugin(option, desc)
    weechat.hook_modifier("weechat_print", "print_cb", "")
