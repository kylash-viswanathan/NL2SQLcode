-- Wealth & portfolio management sample schema (Turso / libSQL, SQLite dialect)

CREATE TABLE IF NOT EXISTS clients (
    client_id       INTEGER PRIMARY KEY,
    full_name       TEXT NOT NULL,
    ssn             TEXT NOT NULL,
    date_of_birth   TEXT NOT NULL,
    email           TEXT NOT NULL,
    phone           TEXT NOT NULL,
    address         TEXT NOT NULL,
    account_number  TEXT NOT NULL,
    risk_profile    TEXT NOT NULL,
    onboarded_date  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id    INTEGER PRIMARY KEY,
    client_id       INTEGER NOT NULL REFERENCES clients(client_id),
    portfolio_name  TEXT NOT NULL,
    base_currency   TEXT NOT NULL,
    created_date    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    ticker          TEXT PRIMARY KEY,
    asset_name      TEXT NOT NULL,
    asset_class     TEXT NOT NULL,
    sector          TEXT,
    currency        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS holdings (
    holding_id      INTEGER PRIMARY KEY,
    portfolio_id    INTEGER NOT NULL REFERENCES portfolios(portfolio_id),
    ticker          TEXT NOT NULL REFERENCES assets(ticker),
    quantity        REAL NOT NULL,
    cost_basis      REAL NOT NULL,
    as_of_date      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    trade_id        INTEGER PRIMARY KEY,
    portfolio_id    INTEGER NOT NULL REFERENCES portfolios(portfolio_id),
    ticker          TEXT NOT NULL REFERENCES assets(ticker),
    side            TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity        REAL NOT NULL,
    price           REAL NOT NULL,
    trade_date      TEXT NOT NULL
);
