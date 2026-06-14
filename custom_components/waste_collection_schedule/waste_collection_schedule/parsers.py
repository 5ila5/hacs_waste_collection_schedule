"""Standard response parsers for waste collection sources.

Each parser is a function (or factory) that integrates with the
retrieve → parse → transform pipeline in BaseSource.

Simple parsers (assign directly):

    parse = parsers.json    # response.json() — list or dict of records
    parse = parsers.ics     # list of (date, summary) tuples

Factory parsers (call to configure, then assign):

    parse = parsers.html("tr", skip=1)  # list of <tr> elements, header skipped
"""

import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    List,
    Protocol,
    Tuple,
    TypeAlias,
)

from bs4 import BeautifulSoup, Tag
from waste_collection_schedule.service.ICS import (
    IcsEvent,
)

if TYPE_CHECKING:
    import requests
    from curl_cffi import requests as _cffi_requests

    # type alias Response = requests.Response | _cffi_requests.Response

    Response: TypeAlias = requests.Response | _cffi_requests.Response
else:
    Response = object


class Parser[T](Protocol):
    def __call__(self, request: Response) -> T:  #
        ...


class JsonParser(Parser[Any]):
    """Parse response as JSON, optionally drilling into a nested key path.

    With no arguments, returns the top-level parsed value::

        parse = parsers.json()          # response.json()

    With one or more keys, walks the parsed value before returning::

        parse = parsers.json("collections")          # response.json()["collections"]
        parse = parsers.json("data", "items")        # response.json()["data"]["items"]

    If the response is already a list at the top level, omit keys entirely.
    """

    def __init__(self, *keys):
        self.keys = keys

    def __call__(self, response: Response):
        data = response.json()
        for key in self.keys:
            data = data[key]
        return data


class TextParser(Parser[str]):
    """Return response as plain text."""

    def __call__(self, response: Response) -> str:
        return response.text


class HtmlParser(Parser[list[Tag]]):
    """Parse response as HTML and select elements by CSS selector.

    Use with HtmlTransformer. The returned list of elements is passed
    individually to the transformer.

    Args:
        selector: CSS selector string passed to BeautifulSoup.select().
        skip:     Number of leading elements to drop (default 0).
    """

    def __init__(self, selector: str, skip: int = 0):
        self.selector = selector
        self.skip = skip

    def __call__(self, response: Response) -> list[Tag]:
        print(f"request to {response.url}")
        print(f"{response}, {response.text[:200]}")  # DEBUG
        soup = BeautifulSoup(response.text, "html.parser")
        print(soup.select(self.selector)[self.skip :])
        return soup.select(self.selector)[self.skip :]


class IcsParser(Parser[list[Tuple[datetime.date, str]]]):
    """Parse response as an iCalendar feed.

    Returns a list of (date, summary) tuples for all events in the next year.
    Use this with the default http_get retriever::

        parse = parsers.ics

        def classify(self, record) -> Collection | None:
            date, summary = record
            return Collection(date=date, waste_type=self._classify_type(summary))
    """

    def __call__(self, response: Response) -> list[Tuple[datetime.date, str]]:
        from waste_collection_schedule.service.ICS import ICS

        return ICS().convert(response.text)


class IcsEventsParser(Parser[List[IcsEvent]]):
    """Parse response as an iCalendar feed, exposing full event fields.

    Like :func:`ics`, but returns ``IcsEvent(date, title, location,
    description)`` records instead of bare ``(date, summary)`` tuples. Use this
    with ``classify()`` when the source must inspect the ICS ``LOCATION`` or
    ``DESCRIPTION`` fields — for example to filter events by collection route::

        parse = parsers.ics_events

        def classify(self, record) -> Collection | None:
            # record.title / record.location / record.description available
            return Collection(date=record.date, waste_type=...)
    """

    def __call__(self, response: Response) -> list:
        from waste_collection_schedule.service.ICS import ICS

        return ICS().convert_events(response.text)
