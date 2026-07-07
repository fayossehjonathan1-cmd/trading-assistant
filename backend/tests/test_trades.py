from app.trades import check_trade

SIGNAL_BUY = {
    "direction": "achat", "entree": 100.0, "sl": 98.0,
    "tp1": 102.0, "tp2": 104.0, "invalidation": 97.5, "regime": "tendance",
}
SIGNAL_SELL = {
    "direction": "vente", "entree": 100.0, "sl": 102.0,
    "tp1": 98.0, "tp2": 96.0, "invalidation": 102.5, "regime": "range",
}


def _trade(statut="en_cours", be=False):
    return {"id": 1, "signal_id": 1, "statut": statut, "be_recommande": be}


def test_buy_hits_tp1():
    statut, fields = check_trade(_trade(), SIGNAL_BUY, prix=102.2, regime="tendance")
    assert statut == "tp1_touche"
    assert "closed_at" not in fields


def test_buy_hits_tp2_and_closes():
    statut, fields = check_trade(_trade("tp1_touche"), SIGNAL_BUY, prix=104.5, regime="tendance")
    assert statut == "tp2_touche"
    assert "closed_at" in fields


def test_buy_hits_sl_and_closes():
    statut, fields = check_trade(_trade(), SIGNAL_BUY, prix=97.9, regime="tendance")
    assert statut == "sl_touche"
    assert "closed_at" in fields


def test_sl_takes_priority_over_invalidation():
    # 97.9 < invalidation(97.5)? non — mais < sl(98) oui: SL prioritaire
    statut, _ = check_trade(_trade(), SIGNAL_BUY, prix=97.9, regime="tendance")
    assert statut == "sl_touche"


def test_invalidation_between_sl_and_entry_impossible_for_buy_uses_regime():
    # invalidation structurelle en dessous du SL n'est atteinte qu'après le SL pour un achat;
    # on vérifie donc l'invalidation par changement de régime radical
    statut, fields = check_trade(_trade(), SIGNAL_BUY, prix=100.5, regime="volatile")
    assert statut == "invalide"
    assert "closed_at" in fields


def test_break_even_recommended_at_1r():
    # risque = 2.0 ; prix 102.0 => +1R exactement mais tp1=102 -> tp1 prioritaire.
    # On teste le BE avec un prix juste sous TP1 et un TP1 plus éloigné.
    signal = {**SIGNAL_BUY, "tp1": 103.0}
    statut, fields = check_trade(_trade(), signal, prix=102.1, regime="tendance")
    assert statut == "be_recommande"
    assert fields["be_recommande"] is True
    assert fields["pnl_estime"] >= 1.0


def test_sell_direction_mirrors_logic():
    statut, _ = check_trade(_trade(), SIGNAL_SELL, prix=97.8, regime="range")
    assert statut == "tp1_touche"
    statut, fields = check_trade(_trade(), SIGNAL_SELL, prix=102.1, regime="range")
    assert statut == "sl_touche"
    assert "closed_at" in fields


def test_no_transition_when_price_in_range():
    statut, fields = check_trade(_trade(), SIGNAL_BUY, prix=100.4, regime="tendance")
    assert statut is None
    assert fields["prix_actuel"] == 100.4
