"""
OKComputer — Trading Strategies
Validated strategies only. Constitution A9: Never deploy untested strategy.
All strategies return confidence score — Constitution A4 enforced.
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from loguru import logger
from dataclasses import dataclass
from enum import Enum


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class StrategyResult:
    signal: Signal
    confidence: float        # 0-100
    reasoning: str
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    risk_reward_ratio: float
    strategy_name: str
    indicators: Dict


class BaseStrategy:
    """All strategies must implement generate_signal()"""

    strategy_name: str = "base"
    min_candles: int = 50     # Minimum candles required

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> StrategyResult:
        raise NotImplementedError

    def _validate_df(self, df: pd.DataFrame) -> bool:
        return len(df) >= self.min_candles and "close" in df.columns

    def _calculate_stop_loss(self, price: float, side: str, atr: float, multiplier: float = 2.0) -> float:
        """ATR-based stop loss"""
        if side == "BUY":
            return price - (atr * multiplier)
        return price + (atr * multiplier)

    def _calculate_take_profit(self, price: float, stop_loss: float, side: str, rr_ratio: float = 2.0) -> float:
        """Risk-reward based take profit"""
        risk = abs(price - stop_loss)
        if side == "BUY":
            return price + (risk * rr_ratio)
        return price - (risk * rr_ratio)


# ── STRATEGY 1: RSI Mean Reversion ───────────────────────────
class RSIMeanReversion(BaseStrategy):
    """
    Buy oversold conditions, sell overbought.
    Best in ranging markets (low ATR).
    Constitution A4: Only acts when RSI extremes are confirmed.
    """
    strategy_name = "rsi_mean_reversion"
    min_candles = 30

    def __init__(
        self,
        rsi_oversold: float = 30,
        rsi_overbought: float = 70,
        atr_multiplier: float = 2.0,
        rr_ratio: float = 2.0,
    ):
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.atr_multiplier = atr_multiplier
        self.rr_ratio = rr_ratio

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> StrategyResult:
        if not self._validate_df(df):
            return self._hold("Insufficient data")

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        current_price = float(latest["close"])
        rsi = float(latest.get("rsi", 50))
        atr = float(latest.get("atr", current_price * 0.02))
        volume_ratio = float(latest.get("volume_ratio", 1.0))
        bb_lower = float(latest.get("bb_lower", current_price * 0.97))
        bb_upper = float(latest.get("bb_upper", current_price * 1.03))

        # Constitution A4: Risk of mean reversion fails above 2.5 ATR
        atr_pct = atr / current_price * 100
        if atr_pct > 2.5:
            return self._hold(
                f"High volatility: ATR {atr_pct:.2f}% > 2.5%. "
                f"Mean reversion unreliable. (Constitution A4)",
                confidence=25
            )

        # BUY signal: oversold RSI + price near lower BB + volume confirmation
        if rsi < self.rsi_oversold and current_price <= bb_lower * 1.01:
            confidence = self._calculate_buy_confidence(rsi, volume_ratio, atr_pct)

            if confidence < 70:
                return self._hold(f"Buy conditions weak: {confidence:.1f}% confidence", confidence)

            stop_loss = self._calculate_stop_loss(current_price, "BUY", atr, self.atr_multiplier)
            take_profit = self._calculate_take_profit(current_price, stop_loss, "BUY", self.rr_ratio)

            return StrategyResult(
                signal=Signal.BUY,
                confidence=confidence,
                reasoning=(
                    f"RSI {rsi:.1f} oversold (< {self.rsi_oversold}). "
                    f"Price at lower Bollinger Band. "
                    f"Volume ratio {volume_ratio:.2f}x. "
                    f"Low volatility ({atr_pct:.2f}% ATR) supports mean reversion."
                ),
                entry_price=current_price,
                stop_loss_price=round(stop_loss, 4),
                take_profit_price=round(take_profit, 4),
                risk_reward_ratio=self.rr_ratio,
                strategy_name=self.strategy_name,
                indicators={"rsi": rsi, "atr_pct": atr_pct, "volume_ratio": volume_ratio},
            )

        # SELL signal: overbought RSI + price near upper BB
        elif rsi > self.rsi_overbought and current_price >= bb_upper * 0.99:
            confidence = self._calculate_sell_confidence(rsi, volume_ratio, atr_pct)

            if confidence < 70:
                return self._hold(f"Sell conditions weak: {confidence:.1f}% confidence", confidence)

            stop_loss = self._calculate_stop_loss(current_price, "SELL", atr, self.atr_multiplier)
            take_profit = self._calculate_take_profit(current_price, stop_loss, "SELL", self.rr_ratio)

            return StrategyResult(
                signal=Signal.SELL,
                confidence=confidence,
                reasoning=(
                    f"RSI {rsi:.1f} overbought (> {self.rsi_overbought}). "
                    f"Price at upper Bollinger Band. "
                    f"Volume ratio {volume_ratio:.2f}x. Mean reversion expected."
                ),
                entry_price=current_price,
                stop_loss_price=round(stop_loss, 4),
                take_profit_price=round(take_profit, 4),
                risk_reward_ratio=self.rr_ratio,
                strategy_name=self.strategy_name,
                indicators={"rsi": rsi, "atr_pct": atr_pct, "volume_ratio": volume_ratio},
            )

        return self._hold(
            f"No clear signal. RSI: {rsi:.1f} (need <{self.rsi_oversold} or >{self.rsi_overbought})"
        )

    def _calculate_buy_confidence(self, rsi, volume_ratio, atr_pct) -> float:
        confidence = 50.0
        # RSI depth bonus
        confidence += max(0, (self.rsi_oversold - rsi)) * 1.5
        # Volume confirmation
        if volume_ratio > 1.5: confidence += 10
        elif volume_ratio > 1.0: confidence += 5
        # Low volatility bonus
        if atr_pct < 1.0: confidence += 8
        elif atr_pct < 1.5: confidence += 4
        return min(95, confidence)

    def _calculate_sell_confidence(self, rsi, volume_ratio, atr_pct) -> float:
        confidence = 50.0
        confidence += max(0, (rsi - self.rsi_overbought)) * 1.5
        if volume_ratio > 1.5: confidence += 10
        elif volume_ratio > 1.0: confidence += 5
        if atr_pct < 1.0: confidence += 8
        elif atr_pct < 1.5: confidence += 4
        return min(95, confidence)

    def _hold(self, reason: str, confidence: float = 45.0) -> StrategyResult:
        return StrategyResult(
            signal=Signal.HOLD, confidence=confidence, reasoning=reason,
            entry_price=0, stop_loss_price=0, take_profit_price=0,
            risk_reward_ratio=0, strategy_name=self.strategy_name, indicators={}
        )


# ── STRATEGY 2: EMA Trend Following ──────────────────────────
class EMATrendFollowing(BaseStrategy):
    """
    Follows the trend using EMA crossovers.
    Best in trending markets (high ATR).
    """
    strategy_name = "ema_trend_following"
    min_candles = 55

    def __init__(self, fast=9, slow=21, trend=50, rr_ratio=3.0):
        self.fast = fast
        self.slow = slow
        self.trend = trend
        self.rr_ratio = rr_ratio

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> StrategyResult:
        if not self._validate_df(df):
            return self._hold("Insufficient data")

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        current_price = float(latest["close"])
        ema_fast = float(latest.get(f"ema_{self.fast}", current_price))
        ema_slow = float(latest.get(f"ema_{self.slow}", current_price))
        ema_trend = float(latest.get(f"ema_{self.trend}", current_price))
        prev_ema_fast = float(prev.get(f"ema_{self.fast}", current_price))
        prev_ema_slow = float(prev.get(f"ema_{self.slow}", current_price))
        atr = float(latest.get("atr", current_price * 0.02))
        rsi = float(latest.get("rsi", 50))
        volume_ratio = float(latest.get("volume_ratio", 1.0))

        # Detect crossover
        golden_cross = prev_ema_fast <= prev_ema_slow and ema_fast > ema_slow
        death_cross = prev_ema_fast >= prev_ema_slow and ema_fast < ema_slow

        # BUY: Golden cross + price above trend EMA + not overbought
        if golden_cross and current_price > ema_trend and rsi < 75:
            confidence = 65
            if volume_ratio > 1.3: confidence += 12
            if rsi < 65: confidence += 8
            confidence = min(92, confidence)

            stop_loss = self._calculate_stop_loss(current_price, "BUY", atr, 1.5)
            take_profit = self._calculate_take_profit(current_price, stop_loss, "BUY", self.rr_ratio)

            return StrategyResult(
                signal=Signal.BUY,
                confidence=confidence,
                reasoning=(
                    f"Golden Cross: EMA{self.fast} crossed above EMA{self.slow}. "
                    f"Price above EMA{self.trend} trend. RSI {rsi:.1f} not overbought. "
                    f"Volume {volume_ratio:.2f}x confirms breakout."
                ),
                entry_price=current_price,
                stop_loss_price=round(stop_loss, 4),
                take_profit_price=round(take_profit, 4),
                risk_reward_ratio=self.rr_ratio,
                strategy_name=self.strategy_name,
                indicators={"ema_fast": ema_fast, "ema_slow": ema_slow, "rsi": rsi},
            )

        # SELL: Death cross + price below trend EMA
        elif death_cross and current_price < ema_trend and rsi > 25:
            confidence = 65
            if volume_ratio > 1.3: confidence += 12
            if rsi > 35: confidence += 8
            confidence = min(92, confidence)

            stop_loss = self._calculate_stop_loss(current_price, "SELL", atr, 1.5)
            take_profit = self._calculate_take_profit(current_price, stop_loss, "SELL", self.rr_ratio)

            return StrategyResult(
                signal=Signal.SELL,
                confidence=confidence,
                reasoning=(
                    f"Death Cross: EMA{self.fast} crossed below EMA{self.slow}. "
                    f"Price below EMA{self.trend} trend. Bearish momentum confirmed."
                ),
                entry_price=current_price,
                stop_loss_price=round(stop_loss, 4),
                take_profit_price=round(take_profit, 4),
                risk_reward_ratio=self.rr_ratio,
                strategy_name=self.strategy_name,
                indicators={"ema_fast": ema_fast, "ema_slow": ema_slow, "rsi": rsi},
            )

        return self._hold(f"No EMA crossover. Fast: {ema_fast:.2f}, Slow: {ema_slow:.2f}")

    def _hold(self, reason: str, confidence: float = 40.0) -> StrategyResult:
        return StrategyResult(
            signal=Signal.HOLD, confidence=confidence, reasoning=reason,
            entry_price=0, stop_loss_price=0, take_profit_price=0,
            risk_reward_ratio=0, strategy_name=self.strategy_name, indicators={}
        )


# ── STRATEGY REGISTRY ─────────────────────────────────────────
STRATEGIES = {
    "rsi_mean_reversion": RSIMeanReversion,
    "ema_trend_following": EMATrendFollowing,
}


def get_strategy(name: str, params: Dict = None) -> BaseStrategy:
    """Factory function to get a strategy by name"""
    cls = STRATEGIES.get(name)
    if not cls:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGIES.keys())}")
    return cls(**(params or {}))
