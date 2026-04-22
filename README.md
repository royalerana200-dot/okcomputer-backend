# OKComputer Backend — Complete Setup Guide
# Built for Termux on Android → Deploy to Railway

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## STEP 1 — TERMUX SETUP (run these first)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

```bash
# Update Termux packages
pkg update && pkg upgrade -y

# Install Python and Git
pkg install python git -y

# Install build tools (needed for some packages)
pkg install python-dev libffi openssl -y

# Verify Python version (need 3.10+)
python --version
```

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## STEP 2 — CLONE AND INSTALL
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

```bash
# Clone your repo
git clone https://github.com/rajin123-droid/algo-trader.git okcomputer
cd okcomputer

# Install all dependencies
pip install -r requirements.txt --break-system-packages

# If a package fails to install, install it separately:
# pip install fastapi uvicorn sqlalchemy anthropic --break-system-packages
```

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## STEP 3 — ENVIRONMENT SETUP
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

```bash
# Copy example env file
cp .env.example .env

# Edit with your keys (use nano or vim)
nano .env

# Required keys to fill in:
# ANTHROPIC_API_KEY — get from console.anthropic.com
# SECRET_KEY — generate: python -c "import secrets; print(secrets.token_hex(32))"
# JWT_SECRET_KEY — generate same way
# DATABASE_URL — Railway provides this automatically
```

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## STEP 4 — LOCAL TEST (Termux)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

```bash
# For local testing without PostgreSQL, use SQLite
# Change DATABASE_URL in .env to:
# DATABASE_URL=sqlite+aiosqlite:///./okcomputer.db
# pip install aiosqlite --break-system-packages

# Create logs directory
mkdir -p logs

# Run the server
python main.py

# You should see:
# ============================================================
#    OKComputer v1.0 — Starting up
# ============================================================
#    Environment: development
#    Paper Trading: True
#    AI Model: claude-sonnet-4-20250514
# ============================================================

# Test it (in another Termux window):
curl http://localhost:8000/
curl http://localhost:8000/health
curl http://localhost:8000/constitution
```

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## STEP 5 — DEPLOY TO RAILWAY
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

```bash
# Install Railway CLI
npm install -g @railway/cli
# OR on Termux:
pkg install nodejs -y && npm install -g @railway/cli

# Login to Railway
railway login

# Initialize project (from your project folder)
railway init

# Add PostgreSQL database
railway add --plugin postgresql

# Add Redis (for background tasks)
railway add --plugin redis

# Set environment variables on Railway
railway variables set ANTHROPIC_API_KEY=your-key
railway variables set SECRET_KEY=your-secret
railway variables set JWT_SECRET_KEY=your-jwt-secret
railway variables set APP_ENV=production
railway variables set PAPER_TRADING_MODE=true
railway variables set DEBUG=false

# Deploy
railway up

# View logs
railway logs

# Get your deployment URL
railway status
```

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## STEP 6 — TEST YOUR LIVE API
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

```bash
BASE_URL="https://your-app.railway.app"

# Health check
curl $BASE_URL/health

# Register first user
curl -X POST $BASE_URL/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@email.com","password":"SecurePass123!","full_name":"Rajin"}'

# Login
curl -X POST $BASE_URL/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=you@email.com&password=SecurePass123!"

# Save the access_token from login response, then:
TOKEN="your-access-token"

# Get agent status
curl $BASE_URL/agents/status -H "Authorization: Bearer $TOKEN"

# Get daily briefing (CEO Agent runs)
curl $BASE_URL/agents/briefing -H "Authorization: Bearer $TOKEN"

# Create a trading bot
curl -X POST $BASE_URL/trading/bots \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"My First Bot","trading_pairs":["BTCUSDT"],"strategy_name":"rsi_mean_reversion"}'

# Get trade signal (no execution)
curl -X POST $BASE_URL/trading/signal \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"bot_id":"BOT_ID_HERE","symbol":"BTCUSDT"}'

# Ask CEO Agent a question
curl -X POST $BASE_URL/agents/orchestrate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input":"Should we increase our BTC position size given current market conditions?"}'
```

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## API ENDPOINTS REFERENCE
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### Authentication
POST   /auth/register          — Create account (30-day trial)
POST   /auth/login             — Get access + refresh tokens
POST   /auth/refresh           — Refresh access token
GET    /auth/me                — Get current user profile

### Trading
POST   /trading/bots           — Create trading bot
GET    /trading/bots           — List all bots
POST   /trading/bots/{id}/start — Start bot
POST   /trading/bots/{id}/pause — Pause bot
GET    /trading/portfolio      — Get portfolio state
POST   /trading/signal         — Get trade signal (no execution)
GET    /trading/trades         — Trade history
GET    /trading/market/{symbol} — Market data + indicators

### Agents
GET    /agents/status          — All 27 agent statuses
POST   /agents/orchestrate     — CEO Agent analysis
GET    /agents/briefing        — Daily operator briefing
GET    /agents/risk            — Risk Guardian status
GET    /agents/logs            — Agent decision logs (A7)
GET    /agents/memory/{id}     — Agent episodic memory
GET    /agents/constitution    — The 7 constitutional articles

### System
GET    /                       — System info
GET    /health                 — Health check (Railway)
GET    /docs                   — Swagger UI (dev only)

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## FILE STRUCTURE
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

```
okcomputer-backend/
├── main.py                    # FastAPI app + routes
├── config.py                  # All configuration
├── requirements.txt           # Python dependencies
├── railway.toml               # Railway deployment config
├── .env.example               # Environment template
├── README.md                  # This file
│
├── database/
│   ├── models.py              # All database models
│   └── connection.py          # Async DB connection
│
├── agents/
│   ├── base.py                # Base agent (memory, constitution, reasoning)
│   ├── ceo_agent.py           # A1: CEO Orchestrator
│   └── risk_guardian.py       # A7: Risk Guardian
│
├── trading/
│   ├── binance_client.py      # Binance + paper trading
│   └── strategies.py          # RSI + EMA strategies
│
├── routers/
│   ├── auth.py                # JWT authentication
│   ├── trading.py             # Bots, trades, portfolio
│   └── agents.py              # Agent system access
│
└── logs/                      # Auto-created
    └── okcomputer.log
```

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## WHAT'S NEXT (Build Order)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Week 1 (Done): Core backend infrastructure ✅
Week 2: Add remaining 25 agents + Stripe payments
Week 3: Frontend dashboard (Next.js)
Week 4: First beta users + feedback loop
Month 2: Scale + marketing agent
```
