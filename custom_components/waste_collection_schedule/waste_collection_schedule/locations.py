from collections.abc import Collection, Sequence
from typing import TypedDict, TypeGuard

type LocationQueryType = str | dict[str, str] | list[str | dict[str, str]]


class LocationID(TypedDict):
    """A TypedDict for location IDs."""

    id: str


class LocationQuery(TypedDict):
    """A TypedDict for locations."""

    query: LocationQueryType


type Location = LocationID | LocationQuery
type Locations = Collection[Location]


def is_location_id(data: Location) -> TypeGuard[LocationID]:
    return "id" in data  # type: ignore[typeddict-item]


def is_location_query(data: Location) -> TypeGuard[LocationQuery]:
    return "query" in data  # type: ignore[typeddict-item]


def locations_queries(*queries: str) -> Sequence[LocationQuery]:
    """Create a list of location queries from strings."""
    return [{"query": list(queries)}]


def locations_ids(*ids: str) -> Sequence[LocationID]:
    """Create a list of location IDs from strings."""
    return [{"id": id} for id in ids]
