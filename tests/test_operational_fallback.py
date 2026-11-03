
"""Offline tests for Kerchunk-first operational NWM fallback."""

import pytest

from streamflow_getter import operational_nwm
from streamflow_getter.operational_nwm import (
    ForecastConfig,
    fetch_operational_forecast,
)


@pytest.fixture
def config():
    return ForecastConfig()


@pytest.fixture
def expected_result():
    return {
        "method": "kerchunk",
        "streamflow_m3s": {3586192: 0.41},
    }


def test_kerchunk_success_no_fallback(
    monkeypatch, config, expected_result
):
    def native_should_not_run(*args):
        raise AssertionError("Native fallback was not expected")

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        lambda *args: expected_result,
    )

    monkeypatch.setattr(
        operational_nwm,
        "read_native_forecast",
        native_should_not_run,
    )

    result = fetch_operational_forecast(
        config, 1, [3586192]
    )

    assert result["method"] == "kerchunk"


def test_access_failure_uses_native(
    monkeypatch, config, expected_result
):
    def fail_kerchunk(*args):
        raise OSError("Reference unavailable")

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        fail_kerchunk,
    )

    monkeypatch.setattr(
        operational_nwm,
        "read_native_forecast",
        lambda *args: {
            **expected_result,
            "method": "native_remote",
        },
    )

    result = fetch_operational_forecast(
        config, 1, [3586192]
    )

    assert result["method"] == "native_remote"
    assert "OSError" in result["fallback_reason"]


@pytest.mark.parametrize(
    "message",
    [
        "Incorrect forecast valid time",
        "Missing reaches",
        "Non-finite streamflow values found",
        "Incorrect Kerchunk source identity",
    ],
)
def test_integrity_error_never_falls_back(
    monkeypatch, config, message
):
    def fail_kerchunk(*args):
        raise ValueError(message)

    def native_should_not_run(*args):
        raise AssertionError("Native fallback must not run")

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        fail_kerchunk,
    )

    monkeypatch.setattr(
        operational_nwm,
        "read_native_forecast",
        native_should_not_run,
    )

    with pytest.raises(ValueError, match=message):
        fetch_operational_forecast(
            config, 1, [3586192]
        )


def test_both_access_methods_fail(monkeypatch, config):
    def fail_kerchunk(*args):
        raise OSError("Kerchunk unavailable")

    def fail_native(*args):
        raise OSError("Native unavailable")

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        fail_kerchunk,
    )

    monkeypatch.setattr(
        operational_nwm,
        "read_native_forecast",
        fail_native,
    )

    with pytest.raises(RuntimeError, match="Both Kerchunk"):
        fetch_operational_forecast(
            config, 1, [3586192]
        )



@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("Request timed out"),
        ConnectionError("Connection interrupted"),
        FileNotFoundError("Kerchunk reference missing"),
    ],
)
def test_recoverable_access_errors_use_native(
    monkeypatch, config, error
):
    """Known access failures should trigger native retrieval."""
    def fail_kerchunk(*args):
        raise error

    def native_success(*args):
        return {
            "method": "native_remote",
            "streamflow_m3s": {3586192: 0.41},
        }

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        fail_kerchunk,
    )

    monkeypatch.setattr(
        operational_nwm,
        "read_native_forecast",
        native_success,
    )

    result = fetch_operational_forecast(
        config, 1, [3586192]
    )

    assert result["method"] == "native_remote"
    assert type(error).__name__ in result["fallback_reason"]


def test_permission_error_does_not_fallback(monkeypatch, config):
    """Authorization errors must not silently switch sources."""
    def fail_kerchunk(*args):
        raise PermissionError("Access denied")

    def native_should_not_run(*args):
        raise AssertionError("Native fallback must not run")

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        fail_kerchunk,
    )

    monkeypatch.setattr(
        operational_nwm,
        "read_native_forecast",
        native_should_not_run,
    )

    with pytest.raises(PermissionError, match="Access denied"):
        fetch_operational_forecast(
            config, 1, [3586192]
        )



def test_coordinator_passes_cache_directory(
    monkeypatch, config, tmp_path
):
    """The coordinator forwards the selected cache directory."""
    captured = {}

    def fake_kerchunk(config_arg, hour, reaches, *, cache_dir):
        captured["cache_dir"] = cache_dir
        return {
            "method": "kerchunk",
            "streamflow_m3s": {3586192: 0.41},
        }

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        fake_kerchunk,
    )

    result = fetch_operational_forecast(
        config,
        1,
        [3586192],
        cache_dir=tmp_path,
    )

    assert result["method"] == "kerchunk"
    assert captured["cache_dir"] == tmp_path


def test_cached_access_failure_does_not_fallback(
    monkeypatch, config, tmp_path
):
    """Cached access errors must not silently trigger native retrieval."""
    def fail_kerchunk(*args, **kwargs):
        raise OSError("Cached retrieval failed")

    def native_should_not_run(*args):
        raise AssertionError("Native fallback must not run")

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        fail_kerchunk,
    )

    monkeypatch.setattr(
        operational_nwm,
        "read_native_forecast",
        native_should_not_run,
    )

    with pytest.raises(OSError, match="Cached retrieval failed"):
        fetch_operational_forecast(
            config,
            1,
            [3586192],
            cache_dir=tmp_path,
        )
