from collections.abc import Iterable, Mapping
from typing import Any, Protocol


class Preprocessor[ParserType, TransformerType](Protocol):
    """Pre-process a record before parsing and transforming it.

    Use with ``preprocessor = preprocessors.some_preprocessor`` when iterating over records.
    """

    def __call__(self, record: ParserType) -> Iterable[TransformerType]:
        """Pre-process a record before parsing and transforming it."""
        ...


class IdentityPreprocessor[T](Preprocessor[Iterable[T], T]):
    """Default preprocessor that returns the input as is."""

    def __call__(self, record):
        return record


class IdentityIterablePreprocessor[T](Preprocessor[T, T]):
    """Preprocessor that wraps a non-iterable record in a single-item iterable."""

    def __call__(self, record):
        if isinstance(record, Iterable):
            return record
        else:
            return [record]


class JsonPreprocessor(Preprocessor[Any, Mapping[str, Any]]):
    """Pre-process JSON records that are either a dict or a list of dicts."""

    def __call__(self, record: Any) -> Iterable[Mapping[str, Any]]:
        if isinstance(record, Mapping):
            yield record
        elif isinstance(record, Iterable):
            for entry in record:
                if not isinstance(entry, Mapping):
                    continue
                yield entry
        else:
            return


class KeyValuePreprocessor(Preprocessor[Any, Iterable[Mapping[str, str]]]):
    """Pre-process records into key value form.

    of the form [[{name: ..., value: ...}], [{name: ..., value: ...}]]
    into an iterable of dicts with the name as key and value as value.
    """

    def __call__(self, record: Any) -> Iterable[Iterable[Mapping[str, str]]]:
        if not isinstance(record, Iterable):
            return
        for entry in record:
            if not isinstance(entry, Iterable):
                continue
            yield filter(lambda item: isinstance(item, Mapping), list(entry))
