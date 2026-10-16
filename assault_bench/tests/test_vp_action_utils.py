from assault_bench.vp_action_utils import parse_action_target_hex


def test_parse_action_target_hex_supports_canonical_colon_format() -> None:
    assert parse_action_target_hex("MOVE:US_1:0:5") == (0, 5)
    assert parse_action_target_hex("ATTACK:US_1:GE_1:2:3") == (2, 3)


def test_parse_action_target_hex_supports_compact_and_structured_formats() -> None:
    assert parse_action_target_hex("MOVE:US_1:0,5") == (0, 5)
    assert parse_action_target_hex("MOVE:US_1:(0,5)") == (0, 5)
    assert parse_action_target_hex("foo target=7,9 bar") == (7, 9)
    assert parse_action_target_hex("foo target=(7,9) bar") == (7, 9)
