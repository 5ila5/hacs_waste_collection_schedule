"""Date parsing utilities.

Each parser is a function that takes a string and returns a datetime.date.
Sources select a parser by format or use the auto-detect fallback.
"""

import datetime
import logging
from typing import Protocol

from dateutil import parser as dateutil_parser

_LOGGER = logging.getLogger(__name__)


class DateParser(Protocol):
    def __call__(self, *args: str) -> datetime.date:  #
        ...


class DateParserAuto(DateParser):
    """Auto-detect date format using dateutil.

    Works both as a bound method (``parse_date = date_parsers.auto`` on a
    Source class, called as ``self.parse_date(date_str)``) and as a plain
    callable (passed to a transformer as ``parse_date=date_parsers.auto``).
    The last positional argument is always treated as the date string.
    """

    def __call__(self, *args: str) -> datetime.date:
        date_str = args[-1]
        return dateutil_parser.parse(str(date_str).strip()).date()


class DateParserForFormat(DateParser):
    """Parse date strings in a specific format using datetime.strptime.

    Use via the factory function for_format(fmt) which returns a DateParserForFormat
    instance with the format string "baked in". The last positional argument is always
    treated as the date string.
    """

    def __init__(self, fmt: str):
        self.fmt = fmt

    def __call__(self, *args: str) -> datetime.date:
        date_str = args[-1]
        return datetime.datetime.strptime(str(date_str).strip(), self.fmt).date()
