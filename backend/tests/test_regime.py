from app.regime import detect_regime


def test_trend_when_adx_high():
    assert detect_regime(adx=30, atr=1.0, atr_moyen=1.0) == "tendance"


def test_range_when_adx_low():
    assert detect_regime(adx=15, atr=1.0, atr_moyen=1.0) == "range"


def test_transition_between_thresholds():
    assert detect_regime(adx=22, atr=1.0, atr_moyen=1.0) == "transition"


def test_volatile_overrides_adx():
    assert detect_regime(adx=30, atr=2.0, atr_moyen=1.0) == "volatile"


def test_handles_missing_values():
    assert detect_regime(adx=None, atr=None, atr_moyen=None) == "transition"
