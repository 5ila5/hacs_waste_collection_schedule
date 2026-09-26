"""Read source-map.geojson and prints warnings for any region smaller than the threshold"""

from pathlib import Path

import geopandas as gpd
import pandas as pd

THRESHOLD_AREA_KM2 = 0.3  # km², regions smaller than this will be printed as warning
geo_json_file = Path(__file__).parent / "source-map.geojson"
source_locations_file = (
    Path(__file__).parent.parent
    / "custom_components"
    / "waste_collection_schedule"
    / "source_locations.json"
)


def main():
    # gdf = gpd.read_file(geo_json_file)

    # 2. Convert WKT polygon string column into active geometry series with EPSG:4326 (WGS84)
    df = pd.read_json(source_locations_file)
    gdf = gpd.GeoDataFrame(
        df, geometry=gpd.GeoSeries.from_wkt(df["polygon"]), crs="EPSG:4326"
    )

    # Optional: drop the redundant WKT text column
    gdf = gdf.drop(columns=["polygon"])

    # 3. Calculate geodesic surface area by reprojecting to an Equal Area projection (EPSG:6933)
    gdf["area_m2"] = gdf.to_crs(epsg=6933).area
    gdf["area_km2"] = gdf["area_m2"] / 1_000_000

    gdf_projected = gdf.to_crs(epsg=6933)
    gdf["area_m2"] = gdf_projected.area
    gdf["area_km2"] = gdf["area_m2"] / 1_000_000

    rows = []

    for index, row in gdf.iterrows():
        rows.append((row["title"], row["area_km2"], row["locations"]))
        if row["area_km2"] < THRESHOLD_AREA_KM2:
            print(
                f"WARNING: Region '{row['title']}' has an area of {row['area_km2']:.2f} km², which is smaller than the threshold of {THRESHOLD_AREA_KM2} km². With location query {row['locations']}"
            )
    print("\n" * 3)
    print("biggest 10 regions:")
    for name, area, query in sorted(rows, key=lambda x: x[1], reverse=True)[:10]:
        print(f"{name}: {area:.2f} km², {query}")
    print("\n")

    print("smallest 10 regions:")
    for name, area, query in sorted(rows, key=lambda x: x[1])[:10]:
        print(f"{name}: {area:.2f} km², {query}")


if __name__ == "__main__":
    main()
