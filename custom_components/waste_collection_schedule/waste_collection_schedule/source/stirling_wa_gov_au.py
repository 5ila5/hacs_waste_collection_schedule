import logging

from waste_collection_schedule.base_source import BaseSource
from waste_collection_schedule.config_params import coords, text_field
from waste_collection_schedule.exceptions import SourceArgumentNotFound
from waste_collection_schedule.retrievers import HttpGetRetriever
from waste_collection_schedule.service.ArcGis import ArcGisGeocodeError, geocode
from waste_collection_schedule.transformers import KeyValueTransformer
from waste_collection_schedule.waste_types import (
    GARDEN_WASTE,
    GENERAL_WASTE,
    ORGANIC,
    RECYCLABLES,
)

_LOGGER = logging.getLogger(__name__)

# Demonstrates: alternative-input PARAMS (address OR lat+lon).
# The framework renders both groups; validation ensures at least one is complete.
_PARAMS_ADDRESS = text_field(
    "address",
    label="Street Address",
)
_PARAMS_COORDS = coords(lat="lat", lon="lon")
# A `ConfigParam` group tagged as mutually-exclusive alternatives would replace
# the two separate params above once the framework supports that widget concept
# (see issue #6561 for discussion).  For now, listing both is a valid prototype.


class Source(BaseSource):
    TITLE = "Stirling"
    DESCRIPTION = "Source for Stirling."
    URL = "https://www.stirling.wa.gov.au"
    COUNTRY = "au"
    CODEOWNERS = ["@markvp"]

    TEST_CASES = {
        "by_address": {"address": "100 Cedric Street, Stirling, WA, Australia"},
        "by_coords": {"lat": -31.9034183, "lon": 115.8320855},
        "by_coords_str": {"lat": "-31.8783052", "lon": "115.8157741"},
    }

    # TODO(arch): once the framework supports mutually-exclusive PARAMS groups,
    # this becomes: PARAMS = [address_or_coords("address", "lat", "lon")]
    PARAMS = [_PARAMS_ADDRESS, _PARAMS_COORDS]

    HOWTO = {
        "en": (
            "Enter your street address including suburb "
            "(e.g. '100 Cedric Street, Stirling, WA, Australia'), "
            "or provide latitude and longitude coordinates."
        ),
    }

    transformer = KeyValueTransformer(
        date_key="date",
        type_key="type",
        type_value_map={
            "red": GENERAL_WASTE,
            "green": ORGANIC,
            "greenverge": GARDEN_WASTE,
            "yellow": RECYCLABLES,
        },
    )

    def __init__(
        self,
        address: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
    ):
        self._address = address
        self._lat = float(lat) if lat is not None else None
        self._lon = float(lon) if lon is not None else None

        if not self._address and (self._lat is None or self._lon is None):
            raise SourceArgumentNotFound(
                "address",
                "Either 'address' or both 'lat' and 'lon' must be provided.",
            )

    @staticmethod
    def _resolve_coordinates(
        address: str | None, lat: float | None, lon: float | None
    ) -> tuple[float, float]:
        if lat is not None and lon is not None:
            return lat, lon
        try:
            location = geocode(address)
        except ArcGisGeocodeError as e:
            raise SourceArgumentNotFound("address", address) from e
        return location["y"], location["x"]

    @staticmethod
    def headers(address, lat, lon):
        lat, lon = Source._resolve_coordinates(address, lat, lon)
        return {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "configid": "7c833520-7b62-4228-8522-fb1a220b32e8",
            "form": "57753bab-f589-44d7-8934-098b6d5c572f",
            "fields": f"{lon},{lat}",
            "apikeylookup": "Bin Day",
            "Origin": Source.URL,
            "Referer": f"{Source.URL}/waste-and-environment/waste-and-recycling/bin-collections",
        }

    retrieve = HttpGetRetriever(
        url="https://www.stirling.wa.gov.au/bincollectioncheck/getresult",
        headers=Source.headers,  # TODO: Fix this does work like this
    )
