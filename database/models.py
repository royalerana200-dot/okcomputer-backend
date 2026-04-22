"""
OKComputer — Database Models
Complete schema for the entire platform
"""
from sqlalchemy import (
    Column, String, Float, Integer, Boolean,
    DateTime, Text, ForeignKey, Enum, JSON, BigInteger
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid
import enum

Base = declarative_base()


def gen_uuid():
    return str(uuid.uuid4())


# ── ENUMS ────────────────────────────────────────────────────
class UserPlan(str, enum.Enum):
    STARTER = "starter"       # $99/mo
    GROWTH = "growth"         # $299/mo
    ENTERPRISE = "enterprise" # $999+/mo


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    TRIAL = "trial"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class TradeStatus(str, enum.Enum):
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    ERROR = "error"


class TradeSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class AssetClass(str, enum.Enum):
    CRYPTO = "crypto"
    STOCK = "stock"
    FOREX = "forex"
    COMMODITY = "commodity"


class AgentStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    EVOLVING = "evolving"


class BotStatus(str, enum.Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


# ── USER ─────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)

    # Plan & billing
    plan = Column(Enum(UserPlan), default=UserPlan.TRIAL)
    status = Column(Enum(UserStatus), default=UserStatus.TRIAL)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    trial_ends_at = Column(DateTime, nullable=True)

    # Settings
    is_superuser = Column(Boolean, default=False)
    paper_trading = Column(Boolean, default=True)  # Always start paper
    risk_tolerance = Column(Float, default=0.02)   # 2% default

    # KYC
    kyc_verified = Column(Boolean, default=False)
    kyc_data = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_login_at = Column(DateTime, nullable=True)

    # Relationships
    bots = relationship("TradingBot", back_populates="user")
    trades = relationship("Trade", back_populates="user")
    portfolio = relationship("Portfolio", back_populates="user", uselist=False)
    api_keys = relationship("ExchangeAPIKey", back_populates="user")


# ── EXCHANGE API KEYS ─────────────────────────────────────────
class ExchangeAPIKey(Base):
    __tablename__ = "exchange_api_keys"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    exchange = Column(String, nullable=False)  # binance, okx, etc
    api_key_encrypted = Column(String, nullable=False)  # AES encrypted
    secret_key_encrypted = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    testnet = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="api_keys")


# ── PORTFOLIO ─────────────────────────────────────────────────
class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)

    # Balances
    total_value_usdt = Column(Float, default=0.0)
    available_usdt = Column(Float, default=0.0)
    in_positions_usdt = Column(Float, default=0.0)

    # Performance
    total_pnl = Column(Float, default=0.0)
    total_pnl_pct = Column(Float, default=0.0)
    daily_pnl = Column(Float, default=0.0)
    daily_pnl_pct = Column(Float, default=0.0)

    # Risk metrics
    max_drawdown = Column(Float, default=0.0)
    current_drawdown = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, default=0.0)
    sortino_ratio = Column(Float, default=0.0)
    win_rate = Column(Float, default=0.0)

    # Constitution A1: Capital Preservation
    peak_value = Column(Float, default=0.0)
    drawdown_alert_triggered = Column(Boolean, default=False)
    emergency_stop_triggered = Column(Boolean, default=False)

    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="portfolio")
    snapshots = relationship("PortfolioSnapshot", back_populates="portfolio")


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(String, primary_key=True, default=gen_uuid)
    portfolio_id = Column(String, ForeignKey("portfolios.id"), nullable=False)
    total_value_usdt = Column(Float, nullable=False)
    pnl_pct = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=func.now())

    portfolio = relationship("Portfolio", back_populates="snapshots")


# ── TRADING BOT ───────────────────────────────────────────────
class TradingBot(Base):
    __tablename__ = "trading_bots"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    # Config
    exchange = Column(String, default="binance")
    asset_class = Column(Enum(AssetClass), default=AssetClass.CRYPTO)
    trading_pairs = Column(JSON, default=list)  # ["BTCUSDT", "ETHUSDT"]
    strategy_name = Column(String, nullable=False)
    strategy_params = Column(JSON, default=dict)

    # Risk config (per-bot Constitution A1 enforcement)
    max_position_size_pct = Column(Float, default=0.02)
    max_daily_loss_pct = Column(Float, default=0.03)
    stop_loss_pct = Column(Float, default=0.02)
    take_profit_pct = Column(Float, default=0.04)

    # Status
    status = Column(Enum(BotStatus), default=BotStatus.PAUSED)
    paper_trading = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)

    # Performance
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    total_pnl = Column(Float, default=0.0)
    total_pnl_pct = Column(Float, default=0.0)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_trade_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="bots")
    trades = relationship("Trade", back_populates="bot")


# ── TRADE ─────────────────────────────────────────────────────
class Trade(Base):
    __tablename__ = "trades"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    bot_id = Column(String, ForeignKey("trading_bots.id"), nullable=True)

    # Trade details
    exchange = Column(String, nullable=False)
    symbol = Column(String, nullable=False)        # BTCUSDT
    asset_class = Column(Enum(AssetClass), default=AssetClass.CRYPTO)
    side = Column(Enum(TradeSide), nullable=False)
    status = Column(Enum(TradeStatus), default=TradeStatus.PENDING)

    # Execution
    quantity = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    stop_loss_price = Column(Float, nullable=True)
    take_profit_price = Column(Float, nullable=True)

    # P&L
    pnl = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    fees = Column(Float, default=0.0)

    # Exchange order IDs
    exchange_order_id = Column(String, nullable=True)

    # Constitution A7: Transparency — full reasoning stored
    agent_reasoning = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    strategy_name = Column(String, nullable=True)

    # Paper trading flag
    is_paper = Column(Boolean, default=True)

    # Timestamps
    signal_at = Column(DateTime, nullable=True)
    opened_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="trades")
    bot = relationship("TradingBot", back_populates="trades")


# ── AGENT SYSTEM ──────────────────────────────────────────────
class AgentLog(Base):
    """Constitution A7: Every agent decision logged with full reasoning"""
    __tablename__ = "agent_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    agent_id = Column(String, nullable=False)       # A0, A1, A2 etc
    agent_name = Column(String, nullable=False)
    division = Column(String, nullable=False)

    # Decision
    action_type = Column(String, nullable=False)    # TRADE, ALERT, IMPROVE, etc
    input_data = Column(JSON, nullable=True)
    reasoning_chain = Column(JSON, nullable=True)   # Chain-of-thought steps
    output_data = Column(JSON, nullable=True)
    decision = Column(Text, nullable=True)

    # Constitution check result
    constitution_check = Column(JSON, nullable=True)
    constitution_passed = Column(Boolean, default=True)
    articles_triggered = Column(JSON, default=list)

    # Confidence
    confidence_score = Column(Float, nullable=True)
    uncertainty_flags = Column(JSON, default=list)

    # Outcome tracking for self-improvement
    predicted_outcome = Column(Text, nullable=True)
    actual_outcome = Column(Text, nullable=True)
    outcome_recorded_at = Column(DateTime, nullable=True)

    timestamp = Column(DateTime, default=func.now())


class AgentMemory(Base):
    """Episodic memory storage per agent"""
    __tablename__ = "agent_memories"

    id = Column(String, primary_key=True, default=gen_uuid)
    agent_id = Column(String, nullable=False, index=True)
    memory_type = Column(String, nullable=False)    # episodic|semantic|procedural

    # Memory content
    situation = Column(Text, nullable=False)        # What happened
    action_taken = Column(Text, nullable=False)     # What we did
    outcome = Column(Text, nullable=True)           # What happened as a result
    lesson = Column(Text, nullable=True)            # What to remember

    # Metadata
    confidence = Column(Float, nullable=True)
    importance_score = Column(Float, default=0.5)   # 0-1, used for retrieval priority
    tags = Column(JSON, default=list)

    created_at = Column(DateTime, default=func.now())
    last_accessed_at = Column(DateTime, nullable=True)
    access_count = Column(Integer, default=0)


class SystemEvolutionCycle(Base):
    """Tracks weekly evolution cycles from The Architect"""
    __tablename__ = "evolution_cycles"

    id = Column(String, primary_key=True, default=gen_uuid)
    cycle_number = Column(Integer, nullable=False)
    week_start = Column(DateTime, nullable=False)
    week_end = Column(DateTime, nullable=True)

    # Collective intelligence
    top_insight = Column(Text, nullable=True)
    cross_division_pattern = Column(Text, nullable=True)
    intelligence_updates = Column(JSON, default=list)
    anomaly_detected = Column(Text, nullable=True)

    # System metrics
    avg_agent_performance = Column(Float, nullable=True)
    system_intelligence_score = Column(Integer, nullable=True)
    net_improvement_pct = Column(Float, nullable=True)

    # State of system report
    sos_report = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=func.now())


# ── SUBSCRIPTION & BILLING ────────────────────────────────────
class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    plan = Column(Enum(UserPlan), nullable=False)
    status = Column(String, nullable=False)          # active|past_due|cancelled
    stripe_subscription_id = Column(String, nullable=True)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String, default="usd")
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())


# ── MARKET DATA CACHE ─────────────────────────────────────────
class MarketDataCache(Base):
    __tablename__ = "market_data_cache"

    id = Column(String, primary_key=True, default=gen_uuid)
    symbol = Column(String, nullable=False, index=True)
    exchange = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)      # 1m, 5m, 1h, 4h, 1d
    data = Column(JSON, nullable=False)             # OHLCV data
    fetched_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, nullable=True)


# ── ALERTS & NOTIFICATIONS ────────────────────────────────────
class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    agent_id = Column(String, nullable=True)

    alert_type = Column(String, nullable=False)    # TRADE|RISK|SYSTEM|CHURN
    severity = Column(String, nullable=False)      # INFO|WARNING|CRITICAL
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)

    is_read = Column(Boolean, default=False)
    is_sent = Column(Boolean, default=False)
    sent_via = Column(JSON, default=list)          # email, push, slack

    created_at = Column(DateTime, default=func.now())
    read_at = Column(DateTime, nullable=True)
