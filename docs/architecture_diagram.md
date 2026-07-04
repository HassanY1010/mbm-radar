# MBM Radar - System Architecture

This document describes the flow of information and components relationship inside MBM Radar.

---

## 1. Flow Diagram: Market Scanner to Telegram Notification

```mermaid
graph TD
    Market[US Stock Market] -->|Market Data| Provider[FMP Data Provider REST/WS]
    Provider -->|Quotes & Financials| Scanner[Scanner Manager]
    Scanner -->|1. Prescreen| Shariah[Shariah Activity Screen]
    Shariah -->|2. Check Criteria| Filter[Stock Criteria Filter]
    Filter -->|3. Indicators calculation| TA[Technical Analysis Calculator]
    TA -->|4. Score opportunity| Scoring[Scoring System]
    Scoring -->|5. Check rating > 5.0| Signal[Signal Generator]
    Signal -->|6. Check redis cooldown| Cooldown[Redis Anti-Spam Check]
    Cooldown -->|7. Send Signal| Notifier[Notifier Service]
    Notifier -->|HTML Message| Channel[Private Telegram Channel]
    Notifier -->|Direct Message| Users[Subscribed Users]
```

---

## 2. Core Service Relationships

```mermaid
graph LR
    subgraph Core Engine
        FastAPI[FastAPI Gateway]
        Bot[Telegram Bot Engine]
        ScannerEng[Scanner Engine]
        Scheduler[APScheduler]
    end
    
    subgraph Cache & Database
        Postgres[(Postgres Database)]
        Redis[(Redis Cache)]
    end

    FastAPI --> Postgres
    Bot --> Postgres
    ScannerEng --> Postgres
    ScannerEng --> Redis
    Scheduler --> Postgres
    Scheduler --> Bot
```

---

## 3. Database Schema

The database schema manages user states, preferences, active subscription statuses, generated signals, and logging metadata:
- **users**: Main registry mapping Telegram chat IDs to usernames and configurations.
- **user_preferences**: Technical alerts filtering limits for each user (Max Price, Max Float, Min RVOL, Gap%).
- **plans**: Pricing plans configuration details.
- **subscriptions**: Links users to active plan periods and status.
- **signals**: History of generated alert signals with calculations.
- **stocks**: Cached Shariah screening status for US stock tickers.
- **watchlist**: Subscribed user lists of target tickers.
