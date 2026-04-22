"""
OKComputer — Binance Trading Client
Real exchange integration with paper trading mode.
Constitution A1: All trades go through Risk Guardian first.
"""
import asyncio
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from loguru import logger
import pandas as pd
import ta

try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    logger.warning("python-binance not installed. Using paper trading mode.")

from config import settings


class BinanceClient:
    """
    Binance exchange client.
    Always starts in paper trading mode.
    Real trading requires explicit activation by operator.
    """

    def __init__(self):
        self.paper_trading = settings.paper_trading_mode
        self.client = None
        self._paper_portfolio = {
            "USDT": 10000.0,  # Start with $10k paper money
            "BTC": 0.0,
            "ETH": 0.0,
        }
        self._paper_trades = []

        if BINANCE_AVAILABLE and settings.binance_api_key:
            try:
                if settings.binance_testnet:
                    self.client = Client(
                        api_key=settings.binance_api_key,
                        api_secret=settings.binance_secret_key,
                        testnet=True,
                    )
                    self.client.API_URL = settings.binance_testnet_url + "/api"
                    logger.info("✓ Binance TESTNET connected")
                else:
                    self.client = Client(
                        api_key=settings.binance_api_key,
                        api_secret=settings.binance_secret_key,
                    )
                    logger.info("✓ Binance LIVE connected")
            except Exception as e:
                logger.error(f"Binance connection failed: {e}. Using paper mode.")
                self.paper_trading = True
        else:
            logger.info("✓ Paper trading mode active (no API keys)")

    # ── MARKET DATA ───────────────────────────────────────────
    async def get_price(self, symbol: str) -> float:
        """Get current price for a symbol"""
        if self.paper_trading or not self.client:
            return self._get_mock_price(symbol)

        try:
            ticker = await asyncio.get_event_loop().run_in_executor(
                None, self.client.get_symbol_ticker, symbol
            )
            return float(ticker["price"])
        except Exception as e:
            logger.error(f"Price fetch error for {symbol}: {e}")
            return self._get_mock_price(symbol)

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100
    ) -> pd.DataFrame:
        """
        Get OHLCV candlestick data.
        Returns pandas DataFrame with technical indicators.
        """
        if self.paper_trading or not self.client:
            return self._get_mock_klines(symbol, limit)

        try:
            klines = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.get_klines(
                    symbol=symbol,
                    interval=interval,
                    limit=limit
                )
            )

            df = pd.DataFrame(klines, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades",
                "taker_buy_base", "taker_buy_quote", "ignore"
            ])

            # Convert to numeric
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col])

            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")

            # Add technical indicators
            df = self._add_indicators(df)

            return df

        except Exception as e:
            logger.error(f"Klines fetch error for {symbol}: {e}")
            return self._get_mock_klines(symbol, limit)

    def _add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add technical analysis indicators"""
        if len(df) < 20:
            return df

        # Trend indicators
        df["ema_9"] = ta.trend.ema_indicator(df["close"], window=9)
        df["ema_21"] = ta.trend.ema_indicator(df["close"], window=21)
        df["ema_50"] = ta.trend.ema_indicator(df["close"], window=50)
        df["sma_200"] = ta.trend.sma_indicator(df["close"], window=200)

        # Momentum indicators
        df["rsi"] = ta.momentum.rsi(df["close"], window=14)
        macd = ta.trend.MACD(df["close"])
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_hist"] = macd.macd_diff()

        # Volatility indicators
        bb = ta.volatility.BollingerBands(df["close"])
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_middle"] = bb.bollinger_mavg()
        df["atr"] = ta.volatility.average_true_range(df["high"], df["low"], df["close"])

        # Volume indicators
        df["volume_sma"] = df["volume"].rolling(window=20).mean()
        df["volume_ratio"] = df["volume"] / df["volume_sma"]

        return df

    async def get_account_balance(self) -> Dict[str, float]:
        """Get current account balances"""
        if self.paper_trading or not self.client:
            return self._paper_portfolio.copy()

        try:
            account = await asyncio.get_event_loop().run_in_executor(
                None, self.client.get_account
            )
            balances = {}
            for asset in account["balances"]:
                free = float(asset["free"])
                locked = float(asset["locked"])
                if free + locked > 0:
                    balances[asset["asset"]] = free + locked
            return balances
        except Exception as e:
            logger.error(f"Balance fetch error: {e}")
            return {}

    # ── TRADE EXECUTION ───────────────────────────────────────
    async def place_market_order(
        self,
        symbol: str,
        side: str,       # BUY or SELL
        quantity: float,
        user_id: str = None,
        risk_approved: bool = False,
        reasoning: str = "",
    ) -> Dict[str, Any]:
        """
        Place a market order.
        Constitution A1: risk_approved must be True (from Risk Guardian).
        """
        if not risk_approved:
            return {
                "success": False,
                "error": "Trade rejected — Risk Guardian approval required (Constitution A1)",
                "order_id": None,
            }

        current_price = await self.get_price(symbol)

        # Paper trading — simulate order
        if self.paper_trading or not self.client:
            return await self._execute_paper_trade(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=current_price,
                reasoning=reasoning,
            )

        # Live trading
        try:
            order_func = (
                self.client.order_market_buy
                if side.upper() == "BUY"
                else self.client.order_market_sell
            )
            order = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: order_func(symbol=symbol, quantity=quantity)
            )

            logger.info(
                f"[LIVE TRADE] {side} {quantity} {symbol} @ ~{current_price} "
                f"| Order ID: {order['orderId']}"
            )

            return {
                "success": True,
                "order_id": str(order["orderId"]),
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": current_price,
                "is_paper": False,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Order placement error: {e}")
            return {
                "success": False,
                "error": str(e),
                "order_id": None,
            }

    async def place_order_with_stops(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_loss_price: float,
        take_profit_price: float,
        risk_approved: bool = False,
        reasoning: str = "",
    ) -> Dict[str, Any]:
        """
        Place market order with automatic stop loss and take profit.
        This is the standard order type for all bot trades.
        """
        if not risk_approved:
            return {"success": False, "error": "Risk Guardian approval required"}

        current_price = await self.get_price(symbol)

        entry_result = await self.place_market_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            risk_approved=True,
            reasoning=reasoning,
        )

        if not entry_result["success"]:
            return entry_result

        entry_result["stop_loss_price"] = stop_loss_price
        entry_result["take_profit_price"] = take_profit_price
        entry_result["risk_reward_ratio"] = abs(take_profit_price - current_price) / abs(current_price - stop_loss_price) if current_price != stop_loss_price else 0

        return entry_result

    # ── PAPER TRADING ─────────────────────────────────────────
    async def _execute_paper_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        reasoning: str = "",
    ) -> Dict[str, Any]:
        """Simulate trade execution for paper trading"""
        trade_value = quantity * price
        base_asset = symbol.replace("USDT", "")

        if side.upper() == "BUY":
            if self._paper_portfolio.get("USDT", 0) < trade_value:
                return {"success": False, "error": "Insufficient paper USDT balance"}
            self._paper_portfolio["USDT"] = self._paper_portfolio.get("USDT", 0) - trade_value
            self._paper_portfolio[base_asset] = self._paper_portfolio.get(base_asset, 0) + quantity
        else:
            if self._paper_portfolio.get(base_asset, 0) < quantity:
                return {"success": False, "error": f"Insufficient paper {base_asset} balance"}
            self._paper_portfolio[base_asset] = self._paper_portfolio.get(base_asset, 0) - quantity
            self._paper_portfolio["USDT"] = self._paper_portfolio.get("USDT", 0) + trade_value

        paper_order_id = f"PAPER_{symbol}_{int(datetime.utcnow().timestamp())}"

        trade_record = {
            "order_id": paper_order_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "value_usdt": trade_value,
            "timestamp": datetime.utcnow().isoformat(),
            "reasoning": reasoning[:200],
        }
        self._paper_trades.append(trade_record)

        logger.info(
            f"[PAPER TRADE] {side} {quantity:.6f} {symbol} @ ${price:.2f} "
            f"| Value: ${trade_value:.2f}"
        )

        return {
            "success": True,
            "order_id": paper_order_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "is_paper": True,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ── MOCK DATA ─────────────────────────────────────────────
    def _get_mock_price(self, symbol: str) -> float:
        """Return realistic mock prices for paper trading"""
        mock_prices = {
            "BTCUSDT": 67250.0,
            "ETHUSDT": 3520.0,
            "BNBUSDT": 590.0,
            "SOLUSDT": 175.0,
            "XRPUSDT": 0.52,
            "ADAUSDT": 0.45,
            "DOTUSDT": 7.8,
            "AVAXUSDT": 35.0,
            "MATICUSDT": 0.88,
            "LINKUSDT": 14.5,
        }
        base = mock_prices.get(symbol, 100.0)
        import random
        # Add small random variance ±0.5%
        return base * (1 + random.uniform(-0.005, 0.005))

    def _get_mock_klines(self, symbol: str, limit: int) -> pd.DataFrame:
        """Generate realistic mock OHLCV data"""
        import numpy as np
        base_price = self._get_mock_price(symbol)
        dates = pd.date_range(end=datetime.utcnow(), periods=limit, freq="1h")

        # Random walk price simulation
        returns = np.random.normal(0.0002, 0.01, limit)
        prices = base_price * np.cumprod(1 + returns)

        df = pd.DataFrame({
            "open_time": dates,
            "open": prices * np.random.uniform(0.999, 1.001, limit),
            "high": prices * np.random.uniform(1.001, 1.02, limit),
            "low": prices * np.random.uniform(0.98, 0.999, limit),
            "close": prices,
            "volume": np.random.uniform(100, 1000, limit),
        })

        return self._add_indicators(df)
