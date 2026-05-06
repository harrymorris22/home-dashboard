"""HomeAssistantCoverSource — position inversion + multi-entity averaging."""
from app.sensors.homeassistant import HomeAssistantCoverSource


class FakeHAClient:
    def __init__(self, states: dict[str, dict]) -> None:
        self.states = states

    def get_state(self, entity_id: str):
        return self.states.get(entity_id)


def _state(pos: int | None, status: str = "open"):
    attrs = {}
    if pos is not None:
        attrs["current_position"] = pos
    return {"state": status, "attributes": attrs}


def test_single_entity_inverts_position():
    """HA position 100 (open) → our blind_pct 0 (up)."""
    client = FakeHAClient({"cover.bedroom": _state(100)})
    source = HomeAssistantCoverSource(client, {"bedroom": ["cover.bedroom"]})
    assert source.latest().blind_pct == {"bedroom": 0}


def test_single_entity_closed_inverts():
    """HA position 0 (closed) → our blind_pct 100 (down)."""
    client = FakeHAClient({"cover.bedroom": _state(0)})
    source = HomeAssistantCoverSource(client, {"bedroom": ["cover.bedroom"]})
    assert source.latest().blind_pct == {"bedroom": 100}


def test_multi_entity_averages_positions():
    """Two bedroom blinds at HA 100 + 50 → average 75 → our 25."""
    client = FakeHAClient({
        "cover.left_bedroom": _state(100),  # open → 0
        "cover.right_bedroom": _state(50),  # half → 50
    })
    source = HomeAssistantCoverSource(client, {
        "bedroom": ["cover.left_bedroom", "cover.right_bedroom"],
    })
    # (0 + 50) // 2 = 25
    assert source.latest().blind_pct == {"bedroom": 25}


def test_missing_entity_skipped():
    client = FakeHAClient({"cover.left": _state(80)})
    source = HomeAssistantCoverSource(client, {
        "bedroom": ["cover.left", "cover.right"],
    })
    # Only left contributes; 100 - 80 = 20.
    assert source.latest().blind_pct == {"bedroom": 20}


def test_no_entity_states_yields_empty_group():
    client = FakeHAClient({})
    source = HomeAssistantCoverSource(client, {"bedroom": ["cover.left"]})
    assert source.latest().blind_pct == {}


def test_string_state_fallback():
    """Cover with no current_position attribute → derive from state string."""
    client = FakeHAClient({
        "cover.foo": {"state": "closed", "attributes": {}},
    })
    source = HomeAssistantCoverSource(client, {"office": ["cover.foo"]})
    assert source.latest().blind_pct == {"office": 100}


def test_unavailable_state_skipped():
    client = FakeHAClient({
        "cover.foo": {"state": "unavailable", "attributes": {}},
    })
    source = HomeAssistantCoverSource(client, {"office": ["cover.foo"]})
    assert source.latest().blind_pct == {}


def test_position_out_of_range_clamped():
    client = FakeHAClient({"cover.foo": _state(150)})
    source = HomeAssistantCoverSource(client, {"office": ["cover.foo"]})
    # 150 clamps to 100, then inverts to 0.
    assert source.latest().blind_pct == {"office": 0}


def test_returns_no_windows():
    """Cover source only deals in blinds — windows always empty."""
    client = FakeHAClient({"cover.foo": _state(50)})
    source = HomeAssistantCoverSource(client, {"office": ["cover.foo"]})
    assert source.latest().window_open == {}
