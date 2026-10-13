"""Turn collector markup into plain text: tags dropped, entities decoded, whitespace collapsed."""
import html
import re

_BLOCK = re.compile(r"<\s*(br|/p|/div|/li|/h\d)\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"[ \t\r\f\v]+")
_LINES = re.compile(r"\n\s*\n+")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = _BLOCK.sub("\n", value)
    text = _TAG.sub("", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = _SPACE.sub(" ", text)
    return _LINES.sub("\n", text).strip()
