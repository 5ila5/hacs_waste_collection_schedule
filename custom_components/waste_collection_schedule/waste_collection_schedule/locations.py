from collections.abc import Collection
from dataclasses import dataclass
from typing import TypeAlias, TypedDict, TypeGuard


class LocationID(TypedDict):
    """A TypedDict for location IDs."""

    id: str


class LocationQuery(TypedDict):
    """A TypedDict for locations."""

    query: str | dict[str, str] | list[str | dict[str, str]]


Location: TypeAlias = LocationID | LocationQuery
Locations: TypeAlias = Collection[Location]


def is_location_id(data: Location) -> TypeGuard[LocationID]:
    return "id" in data  # type: ignore[typeddict-item]


def is_location_query(data: Location) -> TypeGuard[LocationQuery]:
    return "query" in data  # type: ignore[typeddict-item]


@dataclass(frozen=True)
class LocationDataClass:
    """A dataclass for locations."""

    id: str | None = None
    query: str | dict[str, str] | list[str | dict[str, str]] | None = None

    def to_json(self) -> Location:
        """Convert the dataclass to a JSON-serializable dictionary."""
        if self.id is not None:
            return {"id": self.id}
        if self.query is not None:
            return {"query": self.query}
        raise ValueError("Either 'id' or 'query' must be provided.")

    @classmethod
    def from_location(cls, data: Location) -> "LocationDataClass":
        """Create a dataclass from a JSON-serializable dictionary."""
        if is_location_id(data):
            return cls(id=data["id"])
        if is_location_query(data):
            return cls(query=data["query"])
        raise ValueError("Either 'id' or 'query' must be provided.")

    def to_hashable(
        self,
    ) -> tuple[str | tuple[str | tuple[str | tuple[str, ...], ...], ...], ...]:
        """Convert the dataclass to a hashable tuple."""
        if self.id is not None:
            return ("id", self.id)
        if self.query is not None:
            if isinstance(self.query, str):
                return ("query", self.query)
            if isinstance(self.query, dict):
                return ("query", tuple(sorted(self.query.items())))
            if isinstance(self.query, list):
                return (
                    "query",
                    tuple(
                        sorted(
                            (
                                item
                                if isinstance(item, str)
                                else tuple(sorted(item.items()))
                            )
                            for item in self.query
                        )
                    ),
                )
        raise ValueError("Either 'id' or 'query' must be provided.")

    def __hash__(self) -> int:
        """Make the dataclass hashable."""
        return hash(self.to_hashable())

    def __eq__(self, other: object) -> bool:
        """Check equality of two dataclasses."""
        if not isinstance(other, LocationDataClass):
            return NotImplemented
        return self.to_hashable() == other.to_hashable()

    def __lt__(self, other: object) -> bool:
        """Check if one dataclass is less than another."""
        if not isinstance(other, LocationDataClass):
            return NotImplemented
        return self.to_hashable() < other.to_hashable()


@dataclass(frozen=True)
class LocationsDataClass:
    locations: tuple[LocationDataClass, ...]

    @classmethod
    def from_locations(cls, locations: Locations) -> "LocationsDataClass":
        """Create a LocationsDataClass from a collection of Location."""
        return cls(
            locations=tuple(
                sorted(LocationDataClass.from_location(loc) for loc in locations)
            )
        )
