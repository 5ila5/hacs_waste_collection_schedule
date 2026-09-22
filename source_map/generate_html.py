import json
from pathlib import Path

import folium

THIS_DIR = Path(__file__).parent
GEOJSON_FILE = THIS_DIR / "source-map.geojson"
OUTPUT_FILE = THIS_DIR / "map.html"


def main():
    with open(GEOJSON_FILE) as f:
        data = json.load(f)

    # Group properties by unique geometry
    grouped_features = {}

    for feature in data["features"]:
        # Create a canonical key for the geometry
        geom_key = json.dumps(feature["geometry"], sort_keys=True)

        if geom_key not in grouped_features:
            grouped_features[geom_key] = {
                "type": "Feature",
                "geometry": feature["geometry"],
                "properties": {"records": []},
            }

        grouped_features[geom_key]["properties"]["records"].append(
            feature["properties"]
        )

    # Reconstruct GeoJSON with merged tooltips and popups
    consolidated_features = []
    for feat in grouped_features.values():
        records = feat["properties"]["records"]
        count = len(records)

        # 1. Construct combined tooltip text
        names = [str(r.get("name", "Item")) for r in records]
        feat["properties"]["combined_tooltip"] = f"{count} items here: " + ", ".join(
            names
        )

        # 2. Construct combined HTML popup for all records
        popup_html = "<div style='font-family: sans-serif; width: 220px; max-height: 250px; overflow-y: auto;'>"
        popup_html += (
            f"<b>{count} Records for this Region</b><hr style='margin: 6px 0;'>"
        )

        for idx, rec in enumerate(records, 1):
            popup_html += "<div style='margin-bottom: 8px; font-size: 12px;'>"
            popup_html += f"<b>Entry #{idx}</b><br>"
            for key, val in rec.items():
                popup_html += f"&bull; <b>{key}:</b> {val}<br>"
            popup_html += "</div>"

        popup_html += "</div>"
        feat["properties"]["combined_popup"] = popup_html
        consolidated_features.append(feat)

    consolidated_geojson = {
        "type": "FeatureCollection",
        "features": consolidated_features,
    }

    # Initialize map with standard OpenStreetMap tiles
    m = folium.Map(tiles="OpenStreetMap")

    geo_layer = folium.GeoJson(
        consolidated_geojson,
        tooltip=folium.GeoJsonTooltip(fields=["combined_tooltip"], labels=False),
        popup=folium.GeoJsonPopup(fields=["combined_popup"], labels=False),
    ).add_to(m)

    m.fit_bounds(geo_layer.get_bounds())
    m.save(OUTPUT_FILE)


if __name__ == "__main__":
    main()
