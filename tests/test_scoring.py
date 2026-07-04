import pytest
from app.signals.scoring_system import ScoringSystem

def test_scoring_system_ratings():
    # A+ Signal
    # RVOL = 12.0, Gap = 16%, Price > VWAP, Has news, at/above resistance, healthy RSI
    m_score, q_score, rating = ScoringSystem.evaluate(
        price=10.5,
        rvol=12.0,
        gap_pct=16.0,
        change_pct=18.0,
        has_news=True,
        vwap=10.0,
        resistance=10.2,
        support=9.5,
        rsi=65.0
    )
    assert rating == "A+"
    assert q_score >= 9.0

    # A Signal
    # RVOL = 6.0, Gap = 9%, Price > VWAP, Has news, near resistance, healthy RSI
    m_score, q_score, rating = ScoringSystem.evaluate(
        price=10.1,
        rvol=6.0,
        gap_pct=9.0,
        change_pct=10.0,
        has_news=True,
        vwap=9.8,
        resistance=10.2,
        support=9.5,
        rsi=60.0
    )
    assert rating in ["A", "A+"]

    # Weak Signal
    # RVOL = 1.1, Gap = 0.5%, Price < VWAP, No news, far below resistance, overbought RSI
    m_score, q_score, rating = ScoringSystem.evaluate(
        price=9.5,
        rvol=1.1,
        gap_pct=0.5,
        change_pct=0.5,
        has_news=False,
        vwap=10.0,
        resistance=12.0,
        support=9.0,
        rsi=85.0
    )
    assert rating == "Weak"
    assert q_score < 5.0
