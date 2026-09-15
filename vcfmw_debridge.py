# -*- coding: utf-8 -*-
#
# vcfmw_debridge.py - WeeChat script
#
# Rewrites messages from the ccmpbot bridge bot in #vcfmw so they appear
# to come directly from the bridged user, hiding the bot's own nick.

import re
import weechat

SCRIPT_NAME = "vcfmw_debridge"
SCRIPT_AUTHOR = "zdykstra"
SCRIPT_VERSION = "1.0.2"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Rewrite ccmpbot bridge messages in #vcfmw/#shadytel-vcfmw to appear from the bridged user"

BOT_NICK = "ccmpbot"
TARGET_CHANNELS = ("#vcfmw", "#shadytel-vcfmw")

# Matches: <Nick> rest of message
BRIDGE_RE = re.compile(r"^<([^>]+)>\s?(.*)$")

# Strips non-ASCII characters (e.g. emoji) from bridged display names
NICK_FILTER_RE = re.compile(r"[^\x20-\x7E]+")


def print_cb(data, modifier, modifier_data, string):
    # modifier_data is "buffer_pointer;tags"
    parts = modifier_data.split(";", 1)
    if len(parts) < 2:
        return string
    buffer_pointer, tags = parts[0], parts[1]

    if ("nick_" + BOT_NICK) not in tags.split(","):
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
    weechat.hook_modifier("weechat_print", "print_cb", "")
