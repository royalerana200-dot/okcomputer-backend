"""
OKComputer — Trading Router
Bot management, trade execution, portfolio monitoring
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from loguru import logger

from database.connection import get_db
from database.models import (
    User, TradingBot, Trade, Portfolio, PortfolioSnapshot,
    BotStatus, TradeSide, AssetClass, TradeStatus
)
from routers.auth import get_current_user
from agents.risk_guardian import RiskGuardian
from trading.binance_client import BinanceClient
from trading.strategies import get_strategy, Signal

router = APIRouter(prefix="/trading", tags=["trading"])


# ── SCHEMAS ───────────────────────────────────────────────────
class CreateBotRequest(BaseModel):
    name: str
    exchange: str = "binance"
    asset_class: str = "crypto"
    trading_pairs: List[str] = ["BTCUSDT", "ETHUSDT"]
    strategy_name: str = "rsi_mean_reversion"
    strategy_params: Dict = {}
    max_position_size_pct: float = 0.02
    max_daily_loss_pct: float = 0.03
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.04


class BotResponse(BaseModel):
    id: str
    name: str
    exchange: str
    trading_pairs: List[str]
    strategy_name: str
    status: str
    paper_trading: bool
    total_trades: int
    winning_trades: int
    total_pnl: float
    total_pnl_pct: float
    created_at: datetime


class PortfolioResponse(BaseModel):
    total_value_usdt: float
    available_usdt: float
    in_positions_usdt: float
    total_pnl: float
    total_pnl_pct: float
    daily_pnl: float
    daily_pnl_pct: float
    max_drawdown: float
    current_drawdown: float
    win_rate: float
    sharpe_ratio: float
    emergency_stop_triggered: bool


class TradeSignalRequest(BaseModel):
    bot_id: str
    symbol: str
    strategy_override: Optional[str] = None


# ── BOT MANAGEMENT ────────────────────────────────────────────
@router.post("/bots", response_model=BotResponse, status_code=201)
async def create_bot(
    request: CreateBotRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new trading bot — starts in PAUSED paper trading mode"""

    # Validate strategy exists
    try:
        get_strategy(request.strategy_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    bot = TradingBot(
        user_id=current_user.id,
        name=request.name,
        exchange=request.exchange,
        asset_class=request.asset_class,
        trading_pairs=request.trading_pairs,
        strategy_name=request.strategy_name,
        strategy_params=request.strategy_params,
        max_position_size_pct=min(request.max_position_size_pct, 0.05),  # Cap at 5%
        max_daily_loss_pct=min(request.max_daily_loss_pct, 0.05),
        stop_loss_pct=request.stop_loss_pct,
        take_profit_pct=request.take_profit_pct,
        status=BotStatus.PAUSED,
        paper_trading=current_user.paper_trading,  # Inherit user setting
    )
    db.add(bot)
    await db.commit()
    await db.refresh(bot)

    logger.info(f"Bot created: {bot.name} for user {current_user.email}")

    return BotResponse(
        id=bot.id, name=bot.name, exchange=bot.exchange,
        trading_pairs=bot.trading_pairs, strategy_name=bot.strategy_name,
        status=bot.status, paper_trading=bot.paper_trading,
        total_trades=bot.total_trades, winning_trades=bot.winning_trades,
        total_pnl=bot.total_pnl, total_pnl_pct=bot.total_pnl_pct,
        created_at=bot.created_at,
    )


@router.get("/bots", response_model=List[BotResponse])
async def list_bots(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all bots for current user"""
    result = await db.execute(
        select(TradingBot)
        .where(TradingBot.user_id == current_user.id)
        .where(TradingBot.is_active == True)
        .order_by(desc(TradingBot.created_at))
    )
    bots = result.scalars().all()

    return [
        BotResponse(
            id=b.id, name=b.name, exchange=b.exchange,
            trading_pairs=b.trading_pairs, strategy_name=b.strategy_name,
            status=b.status, paper_trading=b.paper_trading,
            total_trades=b.total_trades, winning_trades=b.winning_trades,
            total_pnl=b.total_pnl, total_pnl_pct=b.total_pnl_pct,
            created_at=b.created_at,
        )
        for b in bots
    ]


@router.post("/bots/{bot_id}/start")
async def start_bot(
    bot_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Start a trading bot"""
    result = await db.execute(
        select(TradingBot)
        .where(TradingBot.id == bot_id)
        .where(TradingBot.user_id == current_user.id)
    )
    bot = result.scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    bot.status = BotStatus.RUNNING
    await db.commit()

    # Start background trading loop
    background_tasks.add_task(run_bot_loop, bot_id, current_user.id)

    logger.info(f"Bot started: {bot.name} | Paper: {bot.paper_trading}")
    return {"message": f"Bot '{bot.name}' started", "paper_trading": bot.paper_trading}


@router.post("/bots/{bot_id}/pause")
async def pause_bot(
    bot_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Pause a trading bot"""
    result = await db.execute(
        select(TradingBot)
        .where(TradingBot.id == bot_id)
        .where(TradingBot.user_id == current_user.id)
    )
    bot = result.scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    bot.status = BotStatus.PAUSED
    await db.commit()
    return {"message": f"Bot '{bot.name}' paused"}


# ── PORTFOLIO ─────────────────────────────────────────────────
@router.get("/portfolio", response_model=PortfolioResponse)
async def get_portfolio(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current portfolio state"""
    result = await db.execute(
        select(Portfolio).where(Portfolio.user_id == current_user.id)
    )
    portfolio = result.scalar_one_or_none()

    if not portfolio:
        # Create default portfolio
        portfolio = Portfolio(user_id=current_user.id, total_value_usdt=10000.0)
        db.add(portfolio)
        await db.commit()

    return PortfolioResponse(
        total_value_usdt=portfolio.total_value_usdt,
        available_usdt=portfolio.available_usdt,
        in_positions_usdt=portfolio.in_positions_usdt,
        total_pnl=portfolio.total_pnl,
        total_pnl_pct=portfolio.total_pnl_pct,
        daily_pnl=portfolio.daily_pnl,
        daily_pnl_pct=portfolio.daily_pnl_pct,
        max_drawdown=portfolio.max_drawdown,
        current_drawdown=portfolio.current_drawdown,
        win_rate=portfolio.win_rate,
        sharpe_ratio=portfolio.sharpe_ratio,
        emergency_stop_triggered=portfolio.emergency_stop_triggered,
    )


# ── TRADE SIGNAL ─────────────────────────────────────────────
@router.post("/signal")
async def get_trade_signal(
    request: TradeSignalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a trade signal for a symbol.
    Goes through: Strategy → Risk Guardian → Constitution Check
    Does NOT execute — returns signal for review.
    """
    # Get bot
    result = await db.execute(
        select(TradingBot)
        .where(TradingBot.id == request.bot_id)
        .where(TradingBot.user_id == current_user.id)
    )
    bot = result.scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Get market data
    exchange_client = BinanceClient()
    df = await exchange_client.get_klines(request.symbol, interval="1h", limit=100)

    if df.empty:
        raise HTTPException(status_code=503, detail="Unable to fetch market data")

    # Generate signal
    strategy = get_strategy(
        request.strategy_override or bot.strategy_name,
        bot.strategy_params
    )
    signal_result = strategy.generate_signal(df, request.symbol)

    current_price = float(df.iloc[-1]["close"])

    return {
        "symbol": request.symbol,
        "signal": signal_result.signal,
        "confidence": signal_result.confidence,
        "reasoning": signal_result.reasoning,
        "entry_price": current_price,
        "stop_loss_price": signal_result.stop_loss_price,
        "take_profit_price": signal_result.take_profit_price,
        "risk_reward_ratio": signal_result.risk_reward_ratio,
        "strategy_name": signal_result.strategy_name,
        "indicators": signal_result.indicators,
        "constitution_a4_check": signal_result.confidence >= 70,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── TRADE HISTORY ─────────────────────────────────────────────
@router.get("/trades")
async def get_trades(
    limit: int = 50,
    symbol: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get trade history"""
    query = (
        select(Trade)
        .where(Trade.user_id == current_user.id)
        .order_by(desc(Trade.created_at))
        .limit(min(limit, 200))
    )
    if symbol:
        query = query.where(Trade.symbol == symbol)

    result = await db.execute(query)
    trades = result.scalars().all()

    return {
        "trades": [
            {
                "id": t.id,
                "symbol": t.symbol,
                "side": t.side,
                "status": t.status,
                "quantity": t.quantity,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl": t.pnl,
                "pnl_pct": t.pnl_pct,
                "confidence_score": t.confidence_score,
                "strategy_name": t.strategy_name,
                "is_paper": t.is_paper,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in trades
        ],
        "total": len(trades),
    }


# ── MARKET DATA ───────────────────────────────────────────────
@router.get("/market/{symbol}")
async def get_market_data(
    symbol: str,
    interval: str = "1h",
    limit: int = 100,
    current_user: User = Depends(get_current_user),
):
    """Get OHLCV market data with technical indicators"""
    client = BinanceClient()
    df = await client.get_klines(symbol.upper(), interval=interval, limit=min(limit, 500))

    if df.empty:
        raise HTTPException(status_code=503, detail="Unable to fetch market data")

    # Return last N candles as JSON
    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "candles": df[["open_time", "open", "high", "low", "close", "volume",
                        "rsi", "ema_9", "ema_21", "macd", "atr"]].tail(limit).to_dict("records"),
        "current_price": float(df.iloc[-1]["close"]),
        "fetched_at": datetime.utcnow().isoformat(),
    }


# ── BACKGROUND BOT LOOP ───────────────────────────────────────
async def run_bot_loop(bot_id: str, user_id: str):
    """
    Background task: runs the bot trading loop.
    Checks signals every 5 minutes.
    All trades go through Risk Guardian first.
    """
    import asyncio
    from database.connection import AsyncSessionLocal

    logger.info(f"Bot loop started: {bot_id}")

    while True:
        try:
            async with AsyncSessionLocal() as db:
                # Check bot is still running
                result = await db.execute(select(TradingBot).where(TradingBot.id == bot_id))
                bot = result.scalar_one_or_none()

                if not bot or bot.status != BotStatus.RUNNING:
                    logger.info(f"Bot {bot_id} stopped or not found. Exiting loop.")
                    break

                # Get portfolio
                port_result = await db.execute(
                    select(Portfolio).where(Portfolio.user_id == user_id)
                )
                portfolio = port_result.scalar_one_or_none()

                if not portfolio:
                    await asyncio.sleep(300)
                    continue

                # Initialize clients
                exchange_client = BinanceClient()
                risk_guardian = RiskGuardian(db_session=db)

                # Check each trading pair
                for symbol in bot.trading_pairs:
                    df = await exchange_client.get_klines(symbol)
                    if df.empty:
                        continue

                    strategy = get_strategy(bot.strategy_name, bot.strategy_params)
                    signal = strategy.generate_signal(df, symbol)

                    if signal.signal == Signal.HOLD:
                        continue

                    # Calculate position size
                    current_price = signal.entry_price or float(df.iloc[-1]["close"])
                    quantity = risk_guardian.calculate_position_size(
                        portfolio_value=portfolio.total_value_usdt,
                        risk_pct=bot.max_position_size_pct,
                        entry_price=current_price,
                        stop_loss_price=signal.stop_loss_price,
                    )

                    if quantity <= 0:
                        continue

                    # Risk Guardian approval
                    approved, reason, risk_analysis = await risk_guardian.approve_trade(
                        symbol=symbol,
                        side=signal.signal.value,
                        quantity=quantity,
                        price=current_price,
                        portfolio_value=portfolio.total_value_usdt,
                        daily_pnl=portfolio.daily_pnl,
                        current_drawdown=portfolio.current_drawdown,
                        confidence=signal.confidence,
                        strategy_name=bot.strategy_name,
                        user_id=user_id,
                    )

                    if not approved:
                        logger.info(f"[Bot {bot_id}] Trade rejected: {reason}")
                        continue

                    # Execute trade
                    order = await exchange_client.place_order_with_stops(
                        symbol=symbol,
                        side=signal.signal.value,
                        quantity=quantity,
                        stop_loss_price=signal.stop_loss_price,
                        take_profit_price=signal.take_profit_price,
                        risk_approved=True,
                        reasoning=signal.reasoning,
                    )

                    if order["success"]:
                        # Record trade in DB
                        trade = Trade(
                            user_id=user_id,
                            bot_id=bot_id,
                            exchange=bot.exchange,
                            symbol=symbol,
                            side=TradeSide(signal.signal.value.lower()),
                            status=TradeStatus.OPEN,
                            quantity=quantity,
                            entry_price=current_price,
                            stop_loss_price=signal.stop_loss_price,
                            take_profit_price=signal.take_profit_price,
                            agent_reasoning=signal.reasoning,
                            confidence_score=signal.confidence,
                            strategy_name=bot.strategy_name,
                            is_paper=bot.paper_trading,
                            signal_at=datetime.utcnow(),
                            opened_at=datetime.utcnow(),
                            exchange_order_id=order.get("order_id"),
                        )
                        db.add(trade)

                        # Update bot stats
                        bot.total_trades += 1
                        bot.last_trade_at = datetime.utcnow()
                        await db.commit()

                        logger.info(
                            f"[Bot {bot_id}] Trade recorded: {signal.signal.value} "
                            f"{quantity:.6f} {symbol} @ {current_price}"
                        )

        except Exception as e:
            logger.error(f"Bot loop error [{bot_id}]: {e}")

        # Wait 5 minutes before next check
        await asyncio.sleep(300)
