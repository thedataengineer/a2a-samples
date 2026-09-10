import platform
import sqlite3
import sys

from typing import Any

from mcp.server.fastmcp import FastMCP


# Initialize FastMCP Server
mcp = FastMCP(
    'Enterprise Operations MCP Server',
    instructions='Provides enterprise database, system diagnostics, and analytical tools.',
)


def _init_sqlite_db() -> sqlite3.Connection:
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            sku TEXT,
            name TEXT,
            category TEXT,
            price REAL,
            stock INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            customer TEXT,
            product_id INTEGER,
            quantity INTEGER,
            total_amount REAL,
            status TEXT
        )
    """)
    # Seed initial data
    products = [
        (1, 'SKU-001', 'Cloud Storage Pro', 'Infrastructure', 120.0, 500),
        (2, 'SKU-002', 'BigQuery Compute Unit', 'Analytics', 250.0, 150),
        (3, 'SKU-003', 'AI Inference Node', 'AI/ML', 450.0, 80),
        (4, 'SKU-004', 'Security Key Vault', 'Security', 75.0, 300),
    ]
    cursor.executemany('INSERT INTO products VALUES (?, ?, ?, ?, ?, ?)', products)

    orders = [
        (101, 'Acme Corp', 2, 4, 1000.0, 'Delivered'),
        (102, 'Global Logistics', 3, 2, 900.0, 'Processing'),
        (103, 'FinTech Solutions', 1, 10, 1200.0, 'Delivered'),
        (104, 'HealthCare Plus', 4, 5, 375.0, 'Pending'),
    ]
    cursor.executemany('INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)', orders)
    conn.commit()
    return conn


_DB_CONN = _init_sqlite_db()


@mcp.tool()
def query_database(sql: str) -> list[dict[str, Any]]:
    """Execute a read-only SQL query against the enterprise SQLite database.

    Args:
        sql: A valid SELECT SQL query. Example: SELECT * FROM products WHERE price > 100
    """
    if not sql.strip().upper().startswith('SELECT'):
        raise ValueError('Only SELECT queries are permitted for safety.')
    cursor = _DB_CONN.cursor()
    cursor.execute(sql)
    columns = [desc[0] for desc in cursor.description] if cursor.description else []
    rows = cursor.fetchall()
    return [dict(zip(columns, row, strict=False)) for row in rows]


@mcp.tool()
def get_system_metrics() -> dict[str, Any]:
    """Retrieve host system information and Python runtime diagnostics."""
    return {
        'platform': platform.platform(),
        'python_version': sys.version.split()[0],
        'architecture': platform.machine(),
        'processor': platform.processor(),
        'system_status': 'HEALTHY',
    }


@mcp.tool()
def calculate_financial_roi(investment: float, annual_gain: float, years: int) -> dict[str, Any]:
    """Calculate Return on Investment (ROI) and Compound Growth over time.

    Args:
        investment: Initial capital investment.
        annual_gain: Expected net return per year.
        years: Time duration in years.
    """
    total_gain = annual_gain * years
    net_profit = total_gain - investment
    roi_percentage = (net_profit / investment) * 100 if investment > 0 else 0.0
    return {
        'initial_investment': investment,
        'duration_years': years,
        'total_gain': total_gain,
        'net_profit': net_profit,
        'roi_percentage': round(roi_percentage, 2),
    }


if __name__ == '__main__':
    # Run in stdio mode by default
    mcp.run(transport='stdio')
