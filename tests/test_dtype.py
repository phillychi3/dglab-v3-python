import pytest

from dglabv3.dtype import (
    ChannelStrength,
    Channel,
    StrengthType,
    StrengthMode,
    MessageType,
)


def test_channel_strength_initialization():
    cs = ChannelStrength()
    assert cs.A == 0
    assert cs.B == 0


def test_channel_strength_set_valid_values():
    cs = ChannelStrength()
    cs.A = 100
    cs.B = 150
    assert cs.A == 100
    assert cs.B == 150


def test_channel_strength_set_invalid_values():
    cs = ChannelStrength()
    with pytest.raises(ValueError, match="stronger A cannot be greater than 200"):
        cs.A = 201
    with pytest.raises(ValueError, match="stronger A cannot be less than 0"):
        cs.A = -1
    with pytest.raises(ValueError, match="stronger B cannot be greater than 200"):
        cs.B = 201
    with pytest.raises(ValueError, match="stronger B cannot be less than 0"):
        cs.B = -1


def test_channel_enum():
    assert Channel.A == 1
    assert Channel.B == 2
    assert Channel.BOTH == 3


def test_strength_type_enum():
    assert StrengthType.DECREASE == 1
    assert StrengthType.INCREASE == 2
    assert StrengthType.ZERO == 3
    assert StrengthType.SPECIFIC == 4


def test_strength_mode_enum():
    assert StrengthMode.DECREASE == 0
    assert StrengthMode.INCREASE == 1
    assert StrengthMode.SPECIFIC == 2


def test_message_type_enum():
    assert MessageType.SET_CHANNEL == "set channel"
    assert MessageType.HEARTBEAT == "heartbeat"
    assert MessageType.BIND == "bind"
    assert MessageType.CLIENT_MSG == "clientMsg"
    assert MessageType.MSG == "msg"
