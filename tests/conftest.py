import pytest

from semantic_layer.definitions import build_default_catalog


@pytest.fixture()
def catalog():
    return build_default_catalog()
