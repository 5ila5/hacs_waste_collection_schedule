from collections.abc import Collection
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
