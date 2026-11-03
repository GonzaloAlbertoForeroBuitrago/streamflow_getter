"""Tests for geographic NWM reach resolution."""

import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("shapely")

from shapely.geometry import LineString

from streamflow_getter.spatial_resolution import nearest_reaches


@pytest.fixture
def mock_hydrofabric_crs(monkeypatch):
    """Provide valid CONUS CRS metadata for mocked hydrofabric tests."""
    import pyogrio

    monkeypatch.setattr(
        pyogrio,
        "read_info",
        lambda *args, **kwargs: {"crs": "EPSG:4269"},
    )


@pytest.fixture
def reaches():
    return gpd.GeoDataFrame(
        {
            "ID": [101, 102, 103],
        },
        geometry=[
            LineString([(-99.32, 30.06), (-99.32, 30.08)]),
            LineString([(-99.33, 30.06), (-99.33, 30.08)]),
            LineString([(-99.40, 30.06), (-99.40, 30.08)]),
        ],
        crs="EPSG:4326",
    )


def test_nearest_reach(reaches):
    result = nearest_reaches(
        reaches,
        -99.321,
        30.07,
        max_distance_m=2000,
    )

    assert result[0]["feature_id"] == 101


def test_candidates_sorted(reaches):
    result = nearest_reaches(
        reaches,
        -99.321,
        30.07,
        max_distance_m=2000,
    )

    distances = [item["distance_m"] for item in result]

    assert distances == sorted(distances)


def test_distance_limit(reaches):
    result = nearest_reaches(
        reaches,
        -99.321,
        30.07,
        max_distance_m=200,
    )

    assert [item["feature_id"] for item in result] == [101]


def test_no_nearby_reaches(reaches):
    result = nearest_reaches(
        reaches,
        -90.0,
        40.0,
        max_distance_m=500,
    )

    assert result == []


def test_invalid_coordinates(reaches):
    with pytest.raises(ValueError, match="Invalid"):
        nearest_reaches(reaches, -200, 30)


def test_missing_crs(reaches):
    reaches = reaches.set_crs(None, allow_override=True)

    with pytest.raises(ValueError, match="CRS"):
        nearest_reaches(reaches, -99.321, 30.07)


def test_missing_id_column(reaches):
    reaches = reaches.rename(columns={"ID": "other"})

    with pytest.raises(ValueError, match="ID"):
        nearest_reaches(reaches, -99.321, 30.07)


def test_candidate_limit(reaches):
    result = nearest_reaches(
        reaches,
        -99.321,
        30.07,
        max_distance_m=2000,
        limit=1,
    )

    assert len(result) == 1


def test_load_nearby_reaches_missing_file(tmp_path):
    from streamflow_getter.spatial_resolution import load_nearby_reaches

    with pytest.raises(FileNotFoundError, match="not found"):
        load_nearby_reaches(
            tmp_path / "missing.gdb",
            -99.321,
            30.07,
        )


@pytest.mark.usefixtures("mock_hydrofabric_crs")
def test_load_nearby_reaches_invalid_coordinates(tmp_path):
    from streamflow_getter.spatial_resolution import load_nearby_reaches

    path = tmp_path / "hydrofabric.gdb"
    path.mkdir()

    with pytest.raises(ValueError, match="Invalid"):
        load_nearby_reaches(path, -200, 30.07)


@pytest.mark.usefixtures("mock_hydrofabric_crs")
def test_load_nearby_reaches_invalid_radius(tmp_path):
    from streamflow_getter.spatial_resolution import load_nearby_reaches

    path = tmp_path / "hydrofabric.gdb"
    path.mkdir()

    with pytest.raises(ValueError, match="positive"):
        load_nearby_reaches(
            path,
            -99.321,
            30.07,
            max_distance_m=0,
        )


@pytest.mark.usefixtures("mock_hydrofabric_crs")
def test_load_nearby_reaches_geographic_filter(tmp_path, monkeypatch):
    from streamflow_getter.spatial_resolution import load_nearby_reaches

    path = tmp_path / "hydrofabric.gdb"
    path.mkdir()

    calls = []

    def fake_read_dataframe(path_arg, *, layer, bbox, columns):
        calls.append({
            "path": path_arg,
            "layer": layer,
            "bbox": bbox,
            "columns": columns,
        })
        return gpd.GeoDataFrame(
            {"ID": [3586192]},
            geometry=[LineString([(-99.32, 30.06), (-99.32, 30.08)])],
            crs="EPSG:4269",
        )

    # Verify the loader passes a valid bounding box to pyogrio.
    monkeypatch.setattr(
        "pyogrio.read_dataframe",
        fake_read_dataframe,
    )

    result = load_nearby_reaches(
        path,
        -99.321,
        30.07,
        max_distance_m=1000,
    )

    assert len(calls) == 1

    west, south, east, north = calls[0]["bbox"]

    assert west < -99.321 < east
    assert south < 30.07 < north
    assert calls[0]["layer"] == "nwm_reaches_conus"
    assert calls[0]["columns"] == ["ID"]



@pytest.mark.usefixtures("mock_hydrofabric_crs")
def test_geographic_envelope_covers_projected_radius(
    tmp_path, monkeypatch
):
    """The geographic filter must cover the projected search circle."""
    import pyogrio
    from shapely.geometry import Point

    from streamflow_getter.spatial_resolution import load_nearby_reaches

    path = tmp_path / "hydrofabric.gdb"
    path.mkdir()

    captured = {}

    def fake_read_dataframe(path_arg, *, layer, bbox, columns):
        captured["bbox"] = bbox
        return gpd.GeoDataFrame(
            {"ID": []},
            geometry=[],
            crs="EPSG:4269",
        )

    monkeypatch.setattr(
        pyogrio,
        "read_dataframe",
        fake_read_dataframe,
    )

    longitude = -99.3217121935161
    latitude = 30.0699307434853
    radius = 1000

    load_nearby_reaches(
        path,
        longitude,
        latitude,
        max_distance_m=radius,
    )

    center = gpd.GeoSeries(
        [Point(longitude, latitude)],
        crs="EPSG:4326",
    ).to_crs("EPSG:5070").iloc[0]

    # Sample the projected search-circle boundary densely.
    boundary = gpd.GeoSeries(
        [center.buffer(radius, quad_segs=256).boundary],
        crs="EPSG:5070",
    ).to_crs("EPSG:4269").iloc[0]

    west, south, east, north = captured["bbox"]

    minx, miny, maxx, maxy = boundary.bounds

    assert west <= minx
    assert south <= miny
    assert east >= maxx
    assert north >= maxy



@pytest.mark.usefixtures("mock_hydrofabric_crs")
def test_reaches_in_bbox(tmp_path, monkeypatch, reaches):
    import pyogrio

    from streamflow_getter.spatial_resolution import reaches_in_bbox

    path = tmp_path / "hydrofabric.gdb"
    path.mkdir()

    def fake_read_dataframe(path_arg, *, layer, bbox, columns):
        return reaches.to_crs("EPSG:4269")

    monkeypatch.setattr(
        pyogrio,
        "read_dataframe",
        fake_read_dataframe,
    )

    result = reaches_in_bbox(
        path,
        (-99.335, 30.065, -99.315, 30.075),
    )

    assert result == [101, 102]


@pytest.mark.usefixtures("mock_hydrofabric_crs")
def test_reaches_in_bbox_empty(tmp_path, monkeypatch, reaches):
    import pyogrio

    from streamflow_getter.spatial_resolution import reaches_in_bbox

    path = tmp_path / "hydrofabric.gdb"
    path.mkdir()

    monkeypatch.setattr(
        pyogrio,
        "read_dataframe",
        lambda *args, **kwargs: reaches.to_crs("EPSG:4269"),
    )

    result = reaches_in_bbox(
        path,
        (-95.0, 35.0, -94.0, 36.0),
    )

    assert result == []


def test_reaches_in_bbox_invalid(tmp_path):
    from streamflow_getter.spatial_resolution import reaches_in_bbox

    with pytest.raises(ValueError, match="Invalid"):
        reaches_in_bbox(
            tmp_path,
            (-99, 30, -100, 31),
        )



@pytest.mark.usefixtures("mock_hydrofabric_crs")
def test_reaches_in_polygon(tmp_path, monkeypatch, reaches):
    import pyogrio
    from shapely.geometry import box

    from streamflow_getter.spatial_resolution import reaches_in_polygon

    path = tmp_path / "hydrofabric.gdb"
    path.mkdir()

    monkeypatch.setattr(
        pyogrio,
        "read_dataframe",
        lambda *args, **kwargs: reaches.to_crs("EPSG:4269"),
    )

    polygon = box(-99.335, 30.065, -99.315, 30.075)

    result = reaches_in_polygon(path, polygon)

    assert result == [101, 102]


@pytest.mark.usefixtures("mock_hydrofabric_crs")
def test_reaches_in_polygon_empty(tmp_path, monkeypatch, reaches):
    import pyogrio
    from shapely.geometry import box

    from streamflow_getter.spatial_resolution import reaches_in_polygon

    path = tmp_path / "hydrofabric.gdb"
    path.mkdir()

    monkeypatch.setattr(
        pyogrio,
        "read_dataframe",
        lambda *args, **kwargs: reaches.to_crs("EPSG:4269"),
    )

    polygon = box(-95, 35, -94, 36)

    assert reaches_in_polygon(path, polygon) == []


def test_reaches_in_polygon_invalid(tmp_path):
    from shapely.geometry import Polygon

    from streamflow_getter.spatial_resolution import reaches_in_polygon

    invalid = Polygon([
        (0, 0),
        (1, 1),
        (1, 0),
        (0, 1),
        (0, 0),
    ])

    with pytest.raises(ValueError, match="valid"):
        reaches_in_polygon(tmp_path, invalid)


@pytest.mark.usefixtures("mock_hydrofabric_crs")
def test_reaches_in_polygon_multipolygon(
    tmp_path, monkeypatch, reaches
):
    import pyogrio
    from shapely.geometry import MultiPolygon, box

    from streamflow_getter.spatial_resolution import reaches_in_polygon

    path = tmp_path / "hydrofabric.gdb"
    path.mkdir()

    monkeypatch.setattr(
        pyogrio,
        "read_dataframe",
        lambda *args, **kwargs: reaches.to_crs("EPSG:4269"),
    )

    polygon = MultiPolygon([
        box(-99.325, 30.065, -99.315, 30.075),
        box(-99.405, 30.065, -99.395, 30.075),
    ])

    result = reaches_in_polygon(path, polygon)

    assert result == [101, 103]


def test_nearest_reaches_rejects_fractional_feature_id(reaches):
    invalid = reaches.copy()
    invalid["ID"] = [101.5, 102.0, 103.0]

    with pytest.raises(ValueError, match="integer"):
        nearest_reaches(
            invalid,
            -99.321,
            30.07,
            max_distance_m=2000,
        )



def test_hydrofabric_crs_valid(monkeypatch):
    import pyogrio

    from streamflow_getter.spatial_resolution import (
        validate_hydrofabric_crs,
    )

    monkeypatch.setattr(
        pyogrio,
        "read_info",
        lambda *args, **kwargs: {"crs": "EPSG:4269"},
    )

    validate_hydrofabric_crs("dummy.gdb")


def test_hydrofabric_crs_invalid(monkeypatch):
    import pyogrio

    from streamflow_getter.spatial_resolution import (
        validate_hydrofabric_crs,
    )

    monkeypatch.setattr(
        pyogrio,
        "read_info",
        lambda *args, **kwargs: {"crs": "EPSG:3857"},
    )

    with pytest.raises(ValueError, match="Unexpected hydrofabric CRS"):
        validate_hydrofabric_crs("dummy.gdb")


@pytest.mark.parametrize("selector", ["point", "bbox", "polygon"])
def test_loader_rejects_incompatible_crs(tmp_path, monkeypatch, selector):
    """Each geographic loader must enforce the hydrofabric CRS check."""
    import pyogrio
    from shapely.geometry import box

    from streamflow_getter.spatial_resolution import (
        load_nearby_reaches,
        reaches_in_bbox,
        reaches_in_polygon,
    )

    path = tmp_path / "hydrofabric.gdb"
    path.mkdir()

    monkeypatch.setattr(
        pyogrio,
        "read_info",
        lambda *args, **kwargs: {"crs": "EPSG:3857"},
    )

    def unexpected_read(*args, **kwargs):
        pytest.fail("Geometry read occurred before CRS validation")

    monkeypatch.setattr(pyogrio, "read_dataframe", unexpected_read)

    with pytest.raises(ValueError, match="Unexpected hydrofabric CRS"):
        if selector == "point":
            load_nearby_reaches(path, -99.321, 30.07)
        elif selector == "bbox":
            reaches_in_bbox(path, (-99.335, 30.065, -99.315, 30.075))
        else:
            reaches_in_polygon(
                path,
                box(-99.335, 30.065, -99.315, 30.075),
            )
