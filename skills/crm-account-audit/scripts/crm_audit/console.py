import io
import sys
from typing import TextIO


def safe_output(*streams: TextIO) -> None:
    """Print unencodable characters as escapes instead of crashing (e.g. cp1252 consoles)."""
    for stream in streams or (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")
