"""Creates the schema and loads sample data into the Turso database.

Usage:
    python data/seed.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingestion.db import get_client  # noqa: E402

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

CLIENTS = [
    (1, "Alice Nakamura", "123-45-6789", "1978-03-14", "alice.nakamura@example.com", "212-555-0101", "12 Elm St, New York, NY", "ACC-100234", "moderate", "2019-01-15"),
    (2, "Brian O'Connell", "234-56-7890", "1965-11-02", "brian.oconnell@example.com", "312-555-0110", "88 Oak Ave, Chicago, IL", "ACC-100311", "conservative", "2016-06-01"),
    (3, "Carmen Diaz", "345-67-8901", "1990-07-22", "carmen.diaz@example.com", "415-555-0123", "45 Bay St, San Francisco, CA", "ACC-100455", "aggressive", "2021-09-10"),
    (4, "David Kim", "456-78-9012", "1982-01-30", "david.kim@example.com", "206-555-0199", "7 Pine Rd, Seattle, WA", "ACC-100522", "moderate", "2018-03-22"),
    (5, "Elena Petrova", "567-89-0123", "1975-05-18", "elena.petrova@example.com", "617-555-0142", "3 Charles St, Boston, MA", "ACC-100630", "conservative", "2015-11-05"),
    (6, "Farid Hassan", "678-90-1234", "1988-09-09", "farid.hassan@example.com", "713-555-0177", "21 Main St, Houston, TX", "ACC-100788", "aggressive", "2022-02-14"),
]

PORTFOLIOS = [
    (1, 1, "Alice Growth Portfolio", "USD", "2019-01-20"),
    (2, 1, "Alice Retirement Portfolio", "USD", "2020-04-01"),
    (3, 2, "Brian Conservative Income", "USD", "2016-06-05"),
    (4, 3, "Carmen Aggressive Growth", "USD", "2021-09-15"),
    (5, 4, "David Balanced Portfolio", "USD", "2018-03-25"),
    (6, 5, "Elena Income Portfolio", "USD", "2015-11-10"),
    (7, 6, "Farid Growth Portfolio", "USD", "2022-02-20"),
]

ASSETS = [
    ("AAPL", "Apple Inc.", "Equity", "Technology", "USD"),
    ("MSFT", "Microsoft Corp.", "Equity", "Technology", "USD"),
    ("GOOGL", "Alphabet Inc.", "Equity", "Technology", "USD"),
    ("JNJ", "Johnson & Johnson", "Equity", "Healthcare", "USD"),
    ("JPM", "JPMorgan Chase & Co.", "Equity", "Financials", "USD"),
    ("XOM", "Exxon Mobil Corp.", "Equity", "Energy", "USD"),
    ("BND", "Vanguard Total Bond Market ETF", "Bond", "Fixed Income", "USD"),
    ("VTI", "Vanguard Total Stock Market ETF", "Equity", "Diversified", "USD"),
    ("GLD", "SPDR Gold Shares", "Commodity", "Materials", "USD"),
    ("TSLA", "Tesla Inc.", "Equity", "Consumer Discretionary", "USD"),
]

HOLDINGS = [
    (1, 1, "AAPL", 150, 120.50, "2026-09-01"),
    (2, 1, "VTI", 80, 190.00, "2026-09-01"),
    (3, 2, "BND", 300, 78.20, "2026-09-01"),
    (4, 2, "MSFT", 60, 250.00, "2026-09-01"),
    (5, 3, "JNJ", 200, 150.00, "2026-09-01"),
    (6, 3, "BND", 500, 77.00, "2026-09-01"),
    (7, 4, "TSLA", 100, 210.00, "2026-09-01"),
    (8, 4, "GOOGL", 40, 130.00, "2026-09-01"),
    (9, 5, "JPM", 120, 140.00, "2026-09-01"),
    (10, 5, "VTI", 90, 185.00, "2026-09-01"),
    (11, 6, "BND", 400, 79.00, "2026-09-01"),
    (12, 6, "JNJ", 100, 148.00, "2026-09-01"),
    (13, 7, "TSLA", 60, 220.00, "2026-09-01"),
    (14, 7, "XOM", 150, 105.00, "2026-09-01"),
    (15, 7, "GLD", 50, 190.00, "2026-09-01"),
]

TRADES = [
    (1, 1, "AAPL", "BUY", 50, 118.00, "2026-06-01"),
    (2, 1, "AAPL", "BUY", 100, 121.50, "2026-07-15"),
    (3, 2, "BND", "BUY", 300, 78.20, "2026-05-10"),
    (4, 4, "TSLA", "BUY", 100, 210.00, "2026-08-01"),
    (5, 5, "JPM", "BUY", 120, 140.00, "2026-04-20"),
    (6, 7, "GLD", "BUY", 50, 190.00, "2026-08-20"),
    (7, 4, "GOOGL", "SELL", 10, 135.00, "2026-08-25"),
    (8, 3, "JNJ", "BUY", 200, 150.00, "2026-03-05"),
]


def _executemany(client, table: str, columns: list[str], rows: list[tuple]) -> None:
    placeholders = ", ".join(["?"] * len(columns))
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    for row in rows:
        client.execute(sql, row)


def main() -> None:
    client = get_client()
    try:
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        for statement in schema_sql.split(";"):
            statement = statement.strip()
            if statement:
                client.execute(statement)

        _executemany(
            client, "clients",
            ["client_id", "full_name", "ssn", "date_of_birth", "email", "phone", "address", "account_number", "risk_profile", "onboarded_date"],
            CLIENTS,
        )
        _executemany(
            client, "portfolios",
            ["portfolio_id", "client_id", "portfolio_name", "base_currency", "created_date"],
            PORTFOLIOS,
        )
        _executemany(
            client, "assets",
            ["ticker", "asset_name", "asset_class", "sector", "currency"],
            ASSETS,
        )
        _executemany(
            client, "holdings",
            ["holding_id", "portfolio_id", "ticker", "quantity", "cost_basis", "as_of_date"],
            HOLDINGS,
        )
        _executemany(
            client, "trades",
            ["trade_id", "portfolio_id", "ticker", "side", "quantity", "price", "trade_date"],
            TRADES,
        )
        print("Schema created and sample data loaded.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
