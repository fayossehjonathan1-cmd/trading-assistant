from app.indicators import adx, atr, rsi


def _series(n=60, up=True):
    closes = [100.0 + (i if up else -i) * 0.5 for i in range(n)]
    highs = [c + 0.3 for c in closes]
    lows = [c - 0.3 for c in closes]
    return highs, lows, closes


def test_rsi_extremes():
    _, _, up = _series(up=True)
    assert rsi(up) == 100.0
    _, _, down = _series(up=False)
    assert rsi(down) == 0.0


def test_rsi_needs_enough_data():
    assert rsi([1.0, 2.0, 3.0]) is None


def test_atr_positive_and_scaled():
    highs, lows, closes = _series()
    value = atr(highs, lows, closes)
    assert value is not None and 0 < value < 2


def test_adx_high_in_strong_trend():
    highs, lows, closes = _series(n=80, up=True)
    value = adx(highs, lows, closes)
    assert value is not None and value > 25


def test_adx_low_in_flat_market():
    closes = [100.0 + (0.1 if i % 2 else -0.1) for i in range(80)]
    highs = [c + 0.2 for c in closes]
    lows = [c - 0.2 for c in closes]
    value = adx(highs, lows, closes)
    assert value is not None and value < 25
