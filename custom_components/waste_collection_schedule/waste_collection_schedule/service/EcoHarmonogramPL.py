import datetime
import json
import logging
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from random import randrange
from typing import TYPE_CHECKING, Any, Literal, TypedDict, get_args

if __name__ == "__main__":
    import sys

    sys.path.append(str(Path(__file__).parent.parent.parent))

from waste_collection_schedule import response_shape
from waste_collection_schedule.exceptions import (
    SourceArgAmbiguousWithSuggestions,
    SourceArgumentNotFound,
    SourceArgumentNotFoundWithSuggestions,
    SourceArgumentRequiredWithSuggestions,
)
from waste_collection_schedule.parsers import Parser
from waste_collection_schedule.retrievers import RetrieverFunc

if TYPE_CHECKING:
    from waste_collection_schedule.base_source import BaseSource

_LOGGER = logging.getLogger(__name__)

API_URL = "https://ecoharmonogram.pl/api/api.php"
JSON_RESPONSE_ATTEMPTS = 2

SUPPORTED_APPS_LITERAL = Literal[
    None,
    "eco-przyszlosc",
    "ogrodzieniec",
    "gdansk",
    "hajnowka",
    "niemce",
    "zgk-info",
    "ilza",
    "swietochlowice",
    "popielow",
    "mierzecice",
    "bialapodlaska",
    "slupsk",
    "trzebownisko",
    "zory",
    "opole",
]

SUPPORTED_APPS = get_args(SUPPORTED_APPS_LITERAL)

SUPPORTED_LANGUAGES_LITERAL = Literal["pl", "en", "uk", "ru"]
SUPPORTED_LANGUAGES = get_args(SUPPORTED_LANGUAGES_LITERAL)

# Apps/deployments Ecoharmonogram.pl runs under a `customApp` value (the
# `app` parameter). One structure (this pipeline) covers all of them, so each
# becomes a Region; the default (no `app`) deployment is listed too, so the
# region count matches the source's supported-apps list exactly (16: the
# generic deployment + 15 named apps).
_APP_LABELS: dict[str, str] = {
    "eco-przyszlosc": "Eco-Przyszłość",
    "ogrodzieniec": "Ogrodzieniec",
    "gdansk": "Gdańsk",
    "hajnowka": "Hajnówka",
    "niemce": "Niemce",
    "zgk-info": "ZGK Info",
    "ilza": "Iłża",
    "swietochlowice": "Świętochłowice",
    "popielow": "Popielów",
    "mierzecice": "Mierzęcice",
    "bialapodlaska": "Biała Podlaska",
    "slupsk": "Słupsk",
    "trzebownisko": "Trzebownisko",
    "zory": "Żory",
    "opole": "Opole",
}

_APP_LOCATIONS: dict[str, list[str]] = {
    "eco-przyszlosc": [
        "Powiat Nowosolski, PL",
        "Powiat Wschowski, PL",
        "Gmina Bojadła, PL",
        "Gmina Kargowa, PL",
        "Gmina Świdnica, PL",
        "Zielona Góra, PL",
    ],
    "ogrodzieniec": ["Gmina Ogrodzieniec, PL"],
    "gdansk": ["Gdańsk, PL"],
    "hajnowka": ["Hajnówka"],
    "niemce": ["Gmina Niemce"],
    "zgk-info": [
        "Gmina Stary Lubotyń, PL",
        "Gmina Wąsewo, PL",
        "Gmina Brok, PL",
        "Gmina Goworowo, PL",
        "Gmina Nur, PL",
        "Gmina Ostrów Mazowiecka, PL",
    ],
    "ilza": ["Gmina Iłża, PL"],
    "swietochlowice": ["Gmina Świętochłowice, PL"],
    "popielow": ["Gmina Popielów, PL"],
    "mierzecice": ["Gmina Mierzęcice, PL"],
    "bialapodlaska": ["Miasto Biała Podlaska, PL"],
    "slupsk": ["Słupsk, PL"],
    "trzebownisko": ["Gmina Trzebownisko, PL"],
    "zory": ["Żory, PL"],
    "opole": ["Opole, PL"],
}


class Town(TypedDict):
    id: str
    communityId: str
    name: str
    district: str
    province: str
    icon: str
    isStrNmrReq: str
    schedulePeriodId: int


class Towns(TypedDict):
    towns: list[Town]


class SchedulePeriod(TypedDict):
    id: str
    startDate: str
    endDate: str
    changeDate: str


class SchedulePeriods(TypedDict):
    schedulePeriods: list[SchedulePeriod]


class Street(TypedDict):
    id: str
    name: str
    region: str
    numbers: str
    numberFrom: str
    numberTo: str
    sides: str
    g1: str
    g2: str
    g3: str
    g4: str
    g5: str
    townName: str
    townDistrict: str
    townProvince: str


class StreetGroup(TypedDict):
    streetName: str
    name: str
    choosedStreetIds: str


class StreetGroups(TypedDict):
    items: list[StreetGroup]
    groupId: str


class StreetResponse(TypedDict):
    streets: list[Street]
    groups: StreetGroups


class Schedule(TypedDict):
    id: str
    month: str
    days: str
    year: str
    scheduleDescriptionId: str


class ScheduleDescription(TypedDict):
    id: str
    month: str
    days: str
    year: str
    scheduleDescriptionId: str
    name: str
    description: str
    typeId: str
    color: str
    notificationType: str
    notificationText: str
    notificationDaysBefore: str
    visInCompl: str
    customTextWhenNoDates: str
    doNotShowDates: str


class Search(TypedDict):
    number: str


class ScheduleResponse(TypedDict):
    schedules: list[Schedule]
    scheduleDescription: list[ScheduleDescription]
    street: Street
    town: Town
    schedulePeriod: SchedulePeriod
    name: str
    id: str
    groupname: str
    search: Search
    footer: str


# --------------------------------------------------------------------------- #
# Pipeline components (BaseSource architecture)
#
#     retrieve = EcoharmonogramRetriever()
#     parse    = EcoharmonogramParser()
#
# Ecoharmonogram.pl resolves a place across a genuine multi-step cascade: a
# town lookup (disambiguated by district, optionally scoped to a "community"),
# then every schedule period in force, then - per period - a street lookup
# that may itself branch through up to five named "groups" (g1..g5, matched
# against the API's own group ids) and an "additional sides matcher" that
# narrows an ambiguous street list, then finally the schedules for the
# resolved street id(s). All of that HTTP + resolution (and every
# SourceArgument* it can raise) lives in EcoharmonogramRetriever, which
# returns the raw ``ScheduleResponse`` payloads it gathered (undecoded).
# EcoharmonogramParser does no I/O: it applies the one purely-content-based
# filter left (the "sides" substring match used to decide which fetched
# response's rows to keep) and decodes the schedule + scheduleDescription
# cross-reference into ``(date, label)`` rows, deduplicated across every
# report.
# --------------------------------------------------------------------------- #


class EcoharmonogramClient:
    """Thin HTTP client for the Ecoharmonogram.pl API (api/api.php).

    Every request goes through the caller-supplied ``session`` (the shared
    ``source.session``), so this class holds no session of its own. Used
    exclusively by :class:`EcoharmonogramRetriever`.
    """

    def __init__(self, session: Any, app: "str | None" = None, language: str = "pl"):
        self._session = session
        self._headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
        }
        self._app = app or None
        self._language = language if language in SUPPORTED_LANGUAGES else "pl"
        self._client_id = hex(randrange(0x1000000000000000, 0xFFFFFFFFFFFFFFFF))[2:]

    def _do_request(
        self, action: str, payload: Mapping[str, "str | int"], url: str = API_URL
    ) -> Any:
        params = dict(payload)
        params["action"] = action
        if self._app:
            params["customApp"] = self._app
        params["funcVersion"] = 3
        params["appVersion"] = 107
        params["systemId"] = 1
        params["clientId"] = self._client_id
        params["lng"] = self._language

        for attempt in range(1, JSON_RESPONSE_ATTEMPTS + 1):
            response = self._session.post(url, headers=self._headers, data=params)
            response.raise_for_status()

            try:
                # Ecoharmonogram prefixes JSON with a UTF-8 BOM and declares it
                # as text/html. curl_cffi's Response.json() parses the raw bytes
                # and rejects that otherwise valid payload, so decode it
                # explicitly before handing it to the standard JSON parser.
                return json.loads(response.content.decode("utf-8-sig"))
            except (UnicodeDecodeError, json.JSONDecodeError) as err:
                if attempt < JSON_RESPONSE_ATTEMPTS:
                    _LOGGER.warning(
                        "Ecoharmonogram returned invalid JSON for %s; retrying once",
                        action,
                    )
                    continue

                content_type = response.headers.get("content-type", "unknown")
                raise ValueError(
                    "Ecoharmonogram returned invalid JSON for "
                    f"{action} after {JSON_RESPONSE_ATTEMPTS} attempts "
                    f"(status {response.status_code}, content type {content_type}, "
                    f"{len(response.content)} bytes)"
                ) from err

        raise AssertionError("unreachable")

    def fetch_schedules(self, sp: SchedulePeriod, street_id: str) -> ScheduleResponse:
        return self._do_request(
            "getSchedules", {"streetId": street_id, "schedulePeriodId": sp["id"]}
        )

    def fetch_streets(
        self,
        sp: SchedulePeriod,
        town: Town,
        street: str,
        house_number: "str | int",
        group_id: "int | str" = "1",
        choosed_street_ids: str = "",
    ) -> StreetResponse:
        payload: dict[str, str | int] = {
            "streetName": str(street),
            "number": str(house_number),
            "townId": town["id"],
            "schedulePeriodId": sp["id"],
            "groupId": group_id,
            "choosedStreetIds": choosed_street_ids,
        }
        return self._do_request("getStreets", payload)

    def fetch_scheduled_periods(self, town: Town) -> SchedulePeriods:
        return self._do_request("getSchedulePeriods", {"townId": town["id"]})

    def fetch_town(self, town_input: str) -> Towns:
        return self._do_request("getTowns", {"townName": town_input})

    def fetch_town_with_community(self, community: str) -> Towns:
        return self._do_request(
            action="getTownsForCommunity", payload={"communityId": community}
        )


_HOUSE_NUMBER_RE = re.compile(r"(\d+)")


def _extract_house_number(value: str) -> "int | None":
    """Return the leading integer from a house-number string, e.g. '317E' -> 317."""
    m = _HOUSE_NUMBER_RE.match(value.strip())
    return int(m.group(1)) if m else None


def _filter_streets_by_house_number(
    streets: "list[Street]", house_number_input: str
) -> "list[Street]":
    """Narrow candidate streets to those matching the configured house number.

    The API returns all streets in a group regardless of the searched house
    number. When multiple streets in the same group carry different
    schedules (e.g. Rzeszów - Krakowska has per-house-number routes), only
    the street(s) that best match the user's house number are kept.

    Matching priority:
    1. Exact match on ``numbers`` field (e.g. "7/B" == "7/B").
    2. Exact match on ``numberFrom`` field.
    3. Range match: ``numberFrom`` <= house_number <= ``numberTo``
       (open upper bound when ``numberTo`` is empty).
    Falls back to the full list when nothing matches.
    """
    if len(streets) <= 1 or not house_number_input:
        return streets

    hn = house_number_input.strip()
    hn_int = _extract_house_number(hn)

    exact = [s for s in streets if s.get("numbers", "").strip() == hn]
    if exact:
        return exact

    exact_from = [s for s in streets if s.get("numberFrom", "").strip() == hn]
    if exact_from:
        return exact_from

    if hn_int is not None:
        range_match = []
        for s in streets:
            from_val = _extract_house_number(s.get("numberFrom", ""))
            to_val = _extract_house_number(s.get("numberTo", ""))
            if from_val is None:
                continue
            if from_val <= hn_int and (to_val is None or hn_int <= to_val):
                range_match.append(s)
        if range_match:
            return range_match

    return streets


class EcoharmonogramRetriever(RetrieverFunc):
    """Resolve a town/street/house number on Ecoharmonogram.pl and gather the
    raw schedule payload(s) for every schedule period in force.

    Field names are the ``source.params`` wire names holding each piece of
    the address. ``g1``..``g5`` are always read under those literal names:
    they are not a naming convention this source chose, they are the group
    ids the API itself returns (``streets["groups"]["groupId"]``).
    """

    def __init__(
        self,
        town: str = "town",
        district: str = "district",
        street: str = "street",
        house_number: str = "house_number",
        additional_sides_matcher: str = "additional_sides_matcher",
        community: str = "community",
        app: str = "app",
        language: str = "language",
    ):
        self.town = town
        self.district = district
        self.street = street
        self.house_number = house_number
        self.additional_sides_matcher = additional_sides_matcher
        self.community = community
        self.app = app
        self.language = language

    def __call__(self, source: "BaseSource") -> dict[str, Any]:
        params = source.params
        town_input = str(params.get(self.town) or "")
        district_input = str(params.get(self.district) or "")
        street_input = str(params.get(self.street) or "")
        house_number_input = str(params.get(self.house_number) or "")
        matcher_input = str(params.get(self.additional_sides_matcher) or "")
        community_input = str(params.get(self.community) or "")
        app = params.get(self.app) or None
        language = params.get(self.language) or "pl"
        groups = {f"g{i}": str(params.get(f"g{i}") or "") for i in range(1, 6)}

        client = EcoharmonogramClient(source.session, app=app, language=language)

        town = self._resolve_town(client, town_input, district_input, community_input)
        schedule_periods = client.fetch_scheduled_periods(town).get(
            "schedulePeriods", []
        )

        reports: list[ScheduleResponse] = []
        for sp in schedule_periods:
            reports.extend(
                self._gather_reports(
                    client,
                    sp,
                    town,
                    street_input,
                    house_number_input,
                    matcher_input,
                    groups,
                )
            )

        return {"reports": reports, "additional_sides_matcher": matcher_input}

    def _resolve_town(
        self,
        client: EcoharmonogramClient,
        town_input: str,
        district_input: str,
        community_input: str,
    ) -> Town:
        if community_input == "":
            town_data = client.fetch_town(town_input)
        else:
            town_data = client.fetch_town_with_community(community_input)

        matching_towns = [
            t
            for t in town_data.get("towns", [])
            if town_input.lower() in t.get("name", "").lower()
        ]
        if not matching_towns:
            raise SourceArgumentNotFoundWithSuggestions(
                self.town,
                town_input,
                {t.get("name") for t in town_data.get("towns", [])},
            )

        matching_towns_district = [
            t
            for t in matching_towns
            if district_input.lower() in t.get("district", "").lower()
        ]
        if not matching_towns_district:
            raise SourceArgumentNotFoundWithSuggestions(
                self.district,
                district_input,
                {t.get("district") for t in matching_towns},
            )

        if len(matching_towns_district) == 1:
            return matching_towns_district[0]

        exact = [
            t
            for t in matching_towns_district
            if town_input.lower() == t.get("name", "").lower()
            and district_input.lower() == t.get("district", "").lower()
        ]
        if not exact:
            matches = [
                f"town: {t.get('name')}, district:{t.get('district')}"
                for t in matching_towns_district
            ]
            raise SourceArgAmbiguousWithSuggestions(self.town, town_input, matches)
        return exact[0]

    def _resolve_streets(
        self,
        client: EcoharmonogramClient,
        sp: SchedulePeriod,
        town: Town,
        street_input: str,
        house_number_input: str,
        matcher_input: str,
        groups: "dict[str, str]",
    ) -> StreetResponse:
        group_id: str = "1"
        choosed_street_ids = ""
        streets: StreetResponse = {
            "streets": [],
            "groups": {"items": [], "groupId": ""},
        }
        for _ in range(6):  # a deployment nests at most a handful of groups
            streets = client.fetch_streets(
                sp,
                town,
                street_input,
                house_number_input,
                group_id,
                choosed_street_ids,
            )
            group_id = streets["groups"]["groupId"]
            if group_id == "":
                break
            if streets["groups"]["items"] and group_id in groups:
                value = groups[group_id]
                if value == "":
                    raise SourceArgumentRequiredWithSuggestions(
                        group_id,
                        value,
                        {g["name"] for g in streets["groups"]["items"]},
                    )
                match = next(
                    (
                        g
                        for g in streets["groups"]["items"]
                        if g["name"].strip().casefold() == value.strip().casefold()
                    ),
                    None,
                )
                if match is None:
                    raise SourceArgumentNotFoundWithSuggestions(
                        group_id,
                        value,
                        {g["name"] for g in streets["groups"]["items"]},
                    )
                choosed_street_ids = match["choosedStreetIds"]
        else:
            raise RuntimeError(
                "Infinite loop detected while fetching Ecoharmonogram street groups"
            )

        if len(streets["streets"]) == 1:
            return streets
        if len(streets["streets"]) == 0:
            raise SourceArgumentNotFound(self.street, street_input)

        narrowed: list[Street] = []
        for st in streets["streets"]:
            if st["sides"] == "":
                narrowed.append(st)
            elif matcher_input != "" and (
                st["sides"].strip().casefold() == matcher_input.strip().casefold()
            ):
                narrowed.append(st)

        if not narrowed:
            sides_suggestions = {st["sides"] for st in streets["streets"]}
            if matcher_input == "":
                raise SourceArgumentRequiredWithSuggestions(
                    self.additional_sides_matcher, matcher_input, sides_suggestions
                )
            raise SourceArgumentNotFoundWithSuggestions(
                self.additional_sides_matcher, matcher_input, sides_suggestions
            )

        return {**streets, "streets": narrowed}

    def _gather_reports(
        self,
        client: EcoharmonogramClient,
        sp: SchedulePeriod,
        town: Town,
        street_input: str,
        house_number_input: str,
        matcher_input: str,
        groups: "dict[str, str]",
    ) -> "list[ScheduleResponse]":
        streets = self._resolve_streets(
            client, sp, town, street_input, house_number_input, matcher_input, groups
        )
        streets_list = _filter_streets_by_house_number(
            streets["streets"], house_number_input
        )

        reports: list[ScheduleResponse] = []
        for street in streets_list:
            for street_id in street["id"].split(","):
                reports.append(client.fetch_schedules(sp, street_id))
            if matcher_input == "":
                # No sides matcher: only the first street's schedule(s) are
                # used, matching the pre-refactor behaviour (avoids mixing in
                # other candidate streets left over in the same group).
                return reports
        return reports


class EcoharmonogramRecord(TypedDict):
    date: datetime.date
    type: str
    color: str | None


class EcoharmonogramParser(Parser["list[EcoharmonogramRecord]"]):
    """Decode the raw ``reports`` gathered by :class:`EcoharmonogramRetriever`
    into dated records, retaining each description's display color.

    Applies the one purely-content-based filter left after the retriever's
    resolution (the "additional sides matcher" SUBSTRING match against each
    fetched schedule response's own ``street.sides`` value - the pre-refactor
    decode-time check, distinct from the EXACT-match street narrowing already
    applied by the retriever before any schedule was even fetched), then
    cross-references each schedule against its ``scheduleDescription`` to
    resolve its name. Deduplicates by (date, name) across every report. Does
    no I/O, so it runs standalone against a cached
    ``{"reports": [...], "additional_sides_matcher": ...}`` fixture.
    """

    def __call__(
        self, raw: "dict[str, Any]", source: "BaseSource | None" = None
    ) -> "list[EcoharmonogramRecord]":
        response_shape.expect(
            isinstance(raw, dict) and "reports" in raw,
            source_name=response_shape.source_name(source),
            detail="Ecoharmonogram response missing 'reports'",
            raw=raw,
        )

        matcher = str(raw.get("additional_sides_matcher") or "").lower()
        entries: list[EcoharmonogramRecord] = []
        seen: set[tuple[datetime.date, str]] = set()

        for schedules_response in raw["reports"]:
            sides = str(schedules_response.get("street", {}).get("sides") or "")
            if matcher not in sides.lower():
                continue

            descriptions = {
                d["id"]: d for d in schedules_response.get("scheduleDescription", [])
            }
            for sch in schedules_response.get("schedules", []):
                description = descriptions.get(sch["scheduleDescriptionId"])
                if description is None:
                    continue
                name = description["name"]
                year, month = sch["year"], sch["month"]
                for day in sch["days"].split(";"):
                    day = day.strip()
                    if not day:
                        continue
                    try:
                        date = datetime.date(int(year), int(month), int(day))
                    except ValueError:
                        _LOGGER.warning(
                            "ecoharmonogram_pl: skipping invalid date %s-%s-%s for %s",
                            year,
                            month,
                            day,
                            name,
                        )
                        continue
                    key = (date, name)
                    if key in seen:
                        continue
                    seen.add(key)
                    entries.append(
                        EcoharmonogramRecord(
                            date=date, type=name, color=description.get("color")
                        )
                    )

        return entries


def _strip_numbers(value: Town) -> Town:
    value["name"] = value["name"].strip("0123456789").strip()
    value["district"] = value["district"].strip("0123456789").strip()
    value["province"] = value["province"].strip("0123456789").strip()
    return value


def _district_is_town(
    district: str, town: str, district_counts: dict[str, int]
) -> bool:
    return (
        district.removeprefix("Miasto").removeprefix("Miasta").strip().casefold()[:-1]
        == town.strip().casefold()[:-1]
        and district_counts.get(district, 0) == 1
    )


def _make_unique(iterable: Iterable[Town]) -> list[Town]:
    my_dict: dict[tuple[str, str, str], Town] = {}
    for item in iterable:
        key = (item["name"], item["district"], item["province"])
        my_dict[key] = item
    return list(my_dict.values())


def build_regions_yaml() -> None:
    import requests
    import yaml

    yaml_file = (
        Path(__file__).parent.parent.parent.parent.parent
        / "doc"
        / "regions"
        / "ecoharmonogram_pl.yaml"
    )

    session = requests.Session()
    client = EcoharmonogramClient(session)
    towns = client.fetch_town("")["towns"]

    PROVINCE_OVERRIDES = {
        "Warmińsko-Mazurksie": "Województwo warmińsko-mazurskie",
        "Warmińsko-mazurskim": "Województwo warmińsko-mazurskie",
    }
    SKIP_PROVINCE_FOR = ["Miasto Opole"]

    towns = _make_unique(
        map(
            _strip_numbers,
            filter(
                lambda t: (
                    t["district"] not in ("Demo szablon", "Testowa")
                    and t["province"] != "Gmina testowa"
                ),
                towns,
            ),
        )
    )

    district_counts: dict[str, int] = {}
    for t in towns:
        district = t["district"]
        district_counts[district] = district_counts.get(district, 0) + 1

    non_gmina = {
        (t["name"], PROVINCE_OVERRIDES.get(t["province"], t["province"]))
        for t in towns
        if _district_is_town(t["district"], t["name"], district_counts)
    }
    gmina = {
        (t["district"], PROVINCE_OVERRIDES.get(t["province"], t["province"]))
        for t in towns
        if not _district_is_town(t["district"], t["name"], district_counts)
    }

    location_quries = []

    for district, province in non_gmina:
        if district in SKIP_PROVINCE_FOR:
            location_quries.append(
                f"{district.removeprefix('Miasto').removeprefix('Miasta').strip()}, PL"
            )
        else:
            location_quries.append(
                f"{district.removeprefix('Miasto').removeprefix('Miasta').strip()}, {province}, PL"
            )
    for district, province in gmina:
        if district in SKIP_PROVINCE_FOR:
            string = f"gmina {district.removeprefix('Gmina').strip()}, PL"
        else:
            string = f"gmina {district.removeprefix('Gmina').strip()}, {province}, PL"
        location_quries.append(string)

    regions: list[dict[str, Any]] = [
        {
            "title": "Ecoharmonogram.pl (generic)",
            "url": "https://ecoharmonogram.pl",
            "locations": location_quries,
        }
    ]

    for app_id, label in _APP_LABELS.items():
        regions.append(
            {
                "title": label,
                "url": "https://ecoharmonogram.pl",
                "app": app_id,
                "locations": _APP_LOCATIONS[app_id],
            }
        )

    with open(yaml_file, "w", encoding="utf-8") as f:
        yaml.dump(regions, f, allow_unicode=True, sort_keys=False)


if __name__ == "__main__":
    build_regions_yaml()
