"""مجمّع اتّصالات القاعدة وعلما الويب وحده (W-20261027-026): مطفأٌ افتراضاً ويُفعَّل بعلمٍ صريح."""

from tests.test_production_runtime_settings import _load_production_settings, _values


def test_the_pool_is_off_by_default():
    result = _load_production_settings()

    assert result.returncode == 0, result.stderr
    assert "pool" not in _values(result)["DB_OPTIONS"]
    assert _values(result)["CONN_MAX_AGE"] == "0"


def test_the_pool_is_enabled_by_flag_and_keeps_conn_max_age_zero():
    result = _load_production_settings(
        DB_POOL_ENABLED="true", DB_POOL_MIN_SIZE="3", DB_POOL_MAX_SIZE="12"
    )

    assert result.returncode == 0, result.stderr
    assert "'pool': {'min_size': 3, 'max_size': 12}" in _values(result)["DB_OPTIONS"]
    assert _values(result)["CONN_MAX_AGE"] == "0"


def test_the_pool_defaults_are_two_and_ten():
    result = _load_production_settings(DB_POOL_ENABLED="true")

    assert result.returncode == 0, result.stderr
    assert "'pool': {'min_size': 2, 'max_size': 10}" in _values(result)["DB_OPTIONS"]


def test_an_inverted_pool_size_is_refused_at_startup():
    result = _load_production_settings(
        DB_POOL_ENABLED="true", DB_POOL_MIN_SIZE="9", DB_POOL_MAX_SIZE="3"
    )

    assert result.returncode != 0
    assert "DB_POOL_MIN_SIZE" in result.stderr


def test_the_pool_and_the_statement_timeout_coexist():
    result = _load_production_settings(DB_POOL_ENABLED="true", DB_STATEMENT_TIMEOUT_MS="5000")

    options = _values(result)["DB_OPTIONS"]
    assert result.returncode == 0, result.stderr
    assert "'pool'" in options and "statement_timeout=5000" in options
