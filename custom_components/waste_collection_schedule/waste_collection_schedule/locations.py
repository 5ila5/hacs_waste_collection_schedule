from collections.abc import Collection, Sequence
from typing import TypedDict, TypeGuard, overload

type LocationQueryType = str | dict[str, str] | Sequence[str | dict[str, str]]


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


def are_location_queries(data: Locations) -> TypeGuard[Collection[LocationQuery]]:
    return all("query" in loc for loc in data)  # type: ignore[typeddict-item]


@overload
def locations_queries(
    *,
    amenity: str | Sequence[str | None] | None = None,
    street: str | Sequence[str | None] | None = None,
    city: str | Sequence[str | None] | None = None,
    county: str | Sequence[str | None] | None = None,
    state: str | Sequence[str | None] | None = None,
    country: str | Sequence[str | None] | None = None,
    postalcode: str | Sequence[str | None] | None = None,
) -> Sequence[LocationQuery]: ...


@overload
def locations_queries(*queries: str | dict[str, str]) -> Sequence[LocationQuery]: ...


def locations_queries(
    *queries: str | dict[str, str], **kwargs: str | Sequence[str | None] | None
) -> Sequence[LocationQuery]:
    """Create a list of location queries from strings."""
    if queries:
        return [{"query": list(queries)}]
    if kwargs:
        argument_count = max(  # this allows to pass multiple cities but just a single country, for example
            1 if isinstance(v, str) else len(v)
            for v in kwargs.values()
            if v is not None
        )

        structured_queries_dict = {
            k: ([v for _ in range(argument_count)] if isinstance(v, str) else v)
            for k, v in kwargs.items()
            if v is not None
        }
        try:
            structured_queries: list[dict[str, str]] = [
                dict(zip(structured_queries_dict, values, strict=True))
                for values in zip(*structured_queries_dict.values(), strict=True)
            ]
        except ValueError as e:
            raise ValueError(
                "All query parameters must have the same number of values."
            ) from e
        return [
            LocationQuery(
                query=structured_queries[0]
                if len(structured_queries) == 1
                else structured_queries
            )
        ]
    raise ValueError("Either queries or kwargs must be provided.")


def locations_ids(*ids: str) -> Sequence[LocationID]:
    """Create a list of location IDs from strings."""
    return [{"id": id} for id in ids]
