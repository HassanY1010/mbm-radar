import datetime
from typing import List, Optional
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, BigInteger,
    ForeignKey, Text, JSON, Table, UniqueConstraint
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.database.session import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    registered_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    preferences: Mapped["UserPreferences"] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)
    watchlist: Mapped[List["Watchlist"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    subscriptions: Mapped[List["Subscription"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    payments: Mapped[List["Payment"]] = relationship(back_populates="user")
    sessions: Mapped[List["Session"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    api_keys: Mapped[List["ApiKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    channel_memberships: Mapped[List["ChannelMember"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    usage_stats: Mapped[List["UsageStatistics"]] = relationship(back_populates="user")

class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    max_price: Mapped[float] = mapped_column(Float, default=20.0)
    max_float: Mapped[float] = mapped_column(Float, default=20000000.0)
    max_market_cap: Mapped[float] = mapped_column(Float, default=1500000000.0)
    min_rvol: Mapped[float] = mapped_column(Float, default=3.0)
    min_volume: Mapped[int] = mapped_column(Integer, default=100000)
    min_gap_pct: Mapped[float] = mapped_column(Float, default=2.0)
    min_change_pct: Mapped[float] = mapped_column(Float, default=1.0)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=15)
    alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # List of alert types, e.g. ["VWAP_BREAKOUT", "HIGH_OF_DAY"] stored as JSON
    alert_types: Mapped[dict] = mapped_column(JSON, default=lambda: ["VWAP Breakout", "High Of Day", "Momentum", "Volume Spike", "RVOL Spike", "News", "Halt", "Resume"])
    is_shariah_only: Mapped[bool] = mapped_column(Boolean, default=True)
    volume_filter_type: Mapped[str] = mapped_column(String(10), default=">=")
    min_score_threshold: Mapped[float] = mapped_column(Float, default=3.5)

    user: Mapped["User"] = relationship(back_populates="preferences")

class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    duration_days: Mapped[int] = mapped_column(Integer)  # 30, 90, 365
    price: Mapped[float] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    subscriptions: Mapped[List["Subscription"]] = relationship(back_populates="plan")

class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plans.id"))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, expired, canceled
    start_date: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    end_date: Mapped[datetime.datetime] = mapped_column(DateTime)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="subscriptions")
    plan: Mapped["Plan"] = relationship(back_populates="subscriptions")

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))  # completed, pending, failed
    provider: Mapped[str] = mapped_column(String(50))  # stripe, crypto, manual
    transaction_id: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="payments")

class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    exchange: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    price: Mapped[float] = mapped_column(Float)
    ask: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    spread: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float] = mapped_column(Float)
    gap_pct: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(BigInteger)
    rvol: Mapped[float] = mapped_column(Float)
    dollar_volume: Mapped[float] = mapped_column(Float)
    float_size: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_cap: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vwap: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hod: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lod: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    open_price: Mapped[float] = mapped_column(Float)
    prev_close: Mapped[float] = mapped_column(Float)
    atr14: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_volume_30d: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    support: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resistance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target3: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_reward: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    momentum_score: Mapped[float] = mapped_column(Float)
    quality_score: Mapped[float] = mapped_column(Float)
    score_rating: Mapped[str] = mapped_column(String(10))  # A+, A, B, C, Weak
    signal_type: Mapped[str] = mapped_column(String(50))  # e.g., "VWAP Breakout"
    catalyst: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latest_news: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sec_link: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    notifications: Mapped[List["Notification"]] = relationship(back_populates="signal", cascade="all, delete-orphan")

class Stock(Base):
    __tablename__ = "stocks"

    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    sector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    exchange: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_shariah: Mapped[bool] = mapped_column(Boolean, default=True)
    shariah_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    debt_to_assets_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cash_to_assets_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    non_compliant_income_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_updated: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Watchlist(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    added_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="watchlist")
    
    __table_args__ = (UniqueConstraint('user_id', 'ticker', name='_user_ticker_uc'),)

class Settings(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    telegram_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    signal_id: Mapped[int] = mapped_column(Integer, ForeignKey("signals.id", ondelete="CASCADE"))
    sent_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    status: Mapped[str] = mapped_column(String(20), default="sent")  # sent, failed

    signal: Mapped["Signal"] = relationship(back_populates="notifications")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(255))
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class Blacklist(Base):
    __tablename__ = "blacklist"

    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class Whitelist(Base):
    __tablename__ = "whitelist"

    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class ChannelMember(Base):
    __tablename__ = "channel_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    invite_link: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    joined_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    left_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, removed

    user: Mapped["User"] = relationship(back_populates="channel_memberships")

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(back_populates="sessions")

class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="api_keys")

class UsageStatistics(Base):
    __tablename__ = "usage_statistics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    endpoint: Mapped[str] = mapped_column(String(255))
    method: Mapped[str] = mapped_column(String(10))
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="usage_stats")
