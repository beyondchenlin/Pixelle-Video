import math
from enum import Enum
from types import MappingProxyType

import pytest

from pixelle_video.utils.json_safety import to_json_compatible


class _Mode(Enum):
    ENABLED = "enabled"


def test_to_json_compatible_detaches_frozen_json_containers():
    source = MappingProxyType(
        {
            "mode": _Mode.ENABLED,
            "items": (MappingProxyType({"ok": True}),),
        }
    )

    assert to_json_compatible(source) == {
        "mode": "enabled",
        "items": [{"ok": True}],
    }


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_to_json_compatible_rejects_non_finite_floats(value):
    with pytest.raises(ValueError, match="non-finite"):
        to_json_compatible({"score": value}, field_name="snapshot")


def test_to_json_compatible_rejects_unsupported_objects():
    with pytest.raises(TypeError, match="object"):
        to_json_compatible({"unsafe": object()}, field_name="snapshot")
