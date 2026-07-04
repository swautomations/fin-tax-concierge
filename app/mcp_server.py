from mcp.server.fastmcp import FastMCP
import datetime

mcp = FastMCP("Financial Tax Concierge Server")

# Mock portfolio data
MOCK_PORTFOLIOS = {
    "user_1": {
        "holdings": [
            {"symbol": "HDFC_BANK", "quantity": 100, "average_buy_price": 1500.0, "buy_date": "2024-05-10"},
            {"symbol": "RELIANCE", "quantity": 50, "average_buy_price": 2200.0, "buy_date": "2023-03-15"},
            {"symbol": "PHYSICAL_GOLD", "quantity": 10, "average_buy_price": 45000.0, "buy_date": "2022-04-10"},
            {"symbol": "HDFC_DEBT_FUND", "quantity": 1000, "average_buy_price": 100.0, "buy_date": "2023-05-01"}
        ],
        "transactions": [
            {"symbol": "HDFC_BANK", "type": "BUY", "quantity": 100, "price": 1500.0, "date": "2024-05-10"},
            {"symbol": "RELIANCE", "type": "BUY", "quantity": 50, "price": 2200.0, "date": "2023-03-15"},
            {"symbol": "PHYSICAL_GOLD", "type": "BUY", "quantity": 10, "price": 45000.0, "date": "2022-04-10"},
            {"symbol": "HDFC_DEBT_FUND", "type": "BUY", "quantity": 1000, "price": 100.0, "date": "2023-05-01"},
            {"symbol": "HDFC_BANK", "type": "SELL", "quantity": 50, "price": 1750.0, "date": "2024-11-20"},
            {"symbol": "RELIANCE", "type": "SELL", "quantity": 50, "price": 2600.0, "date": "2025-02-10"}
        ]
    }
}

# Mock market data
MOCK_MARKET_DATA = {
    "HDFC_BANK": {"price": 1780.0, "asset_type": "LISTED_EQUITY"},
    "RELIANCE": {"price": 2550.0, "asset_type": "LISTED_EQUITY"},
    "PHYSICAL_GOLD": {"price": 72000.0, "asset_type": "GOLD"},
    "HDFC_DEBT_FUND": {"price": 120.0, "asset_type": "DEBT_FUND"}
}

@mcp.tool()
def fetch_portfolio(user_id: str) -> dict:
    """Fetch the user's transaction history and current portfolio holdings.
    
    Args:
        user_id: The ID of the user (e.g. 'user_1').
    """
    return MOCK_PORTFOLIOS.get(user_id, {"holdings": [], "transactions": []})

@mcp.tool()
def market_data_lookup(symbol: str) -> dict:
    """Lookup the current market price and asset type category for a given symbol.
    
    Args:
        symbol: The financial symbol (e.g. 'HDFC_BANK', 'PHYSICAL_GOLD').
    """
    return MOCK_MARKET_DATA.get(symbol, {"price": 0.0, "asset_type": "UNKNOWN"})

@mcp.tool()
def tax_calculator(transactions: list[dict]) -> dict:
    """Calculate STCG and LTCG for the given transactions deterministically.
    
    Args:
        transactions: List of transaction dictionaries, where each dict has:
          - symbol (str)
          - asset_type (str) e.g. 'LISTED_EQUITY', 'GOLD', 'DEBT_FUND'
          - quantity (int)
          - buy_price (float)
          - buy_date (str, 'YYYY-MM-DD')
          - sell_price (float)
          - sell_date (str, 'YYYY-MM-DD')
    """
    results = []
    total_stcg = 0.0
    total_ltcg = 0.0
    total_stcg_tax = 0.0
    total_ltcg_tax = 0.0
    
    for tx in transactions:
        symbol = tx.get("symbol", "UNKNOWN")
        asset_type = tx.get("asset_type", "LISTED_EQUITY")
        quantity = tx.get("quantity", 0)
        buy_price = tx.get("buy_price", 0.0)
        buy_date_str = tx.get("buy_date", "")
        sell_price = tx.get("sell_price", 0.0)
        sell_date_str = tx.get("sell_date", "")
        
        try:
            buy_date = datetime.datetime.strptime(buy_date_str, "%Y-%m-%d")
            sell_date = datetime.datetime.strptime(sell_date_str, "%Y-%m-%d")
        except ValueError:
            results.append({"symbol": symbol, "error": f"Invalid date format for {buy_date_str} or {sell_date_str}. Use YYYY-MM-DD."})
            continue
            
        holding_days = (sell_date - buy_date).days
        holding_months = holding_days / 30.44  # average days in a month
        
        # Calculate capital gains
        purchase_cost = buy_price * quantity
        sale_value = sell_price * quantity
        gains = sale_value - purchase_cost
        
        # Determine classification and tax rate based on holding period
        is_long_term = False
        tax_rate = 0.0
        details = ""
        
        if asset_type in ("LISTED_EQUITY", "LISTED_SECURITY"):
            # Threshold is 12 months (1 year)
            if holding_months > 12:
                is_long_term = True
                tax_rate = 0.125  # 12.5% LTCG post July 2024
                details = "LTCG (Held > 12 months, taxed at 12.5% post-July 23, 2024)"
            else:
                is_long_term = False
                tax_rate = 0.20  # 20% STCG post July 2024
                details = "STCG (Held <= 12 months, taxed at 20% post-July 23, 2024)"
        elif asset_type == "DEBT_FUND":
            # Debt funds with <=35% equity are always treated as STCG/slab rate, no LTCG
            is_long_term = False
            tax_rate = 0.30  # Assumed slab rate of 30%
            details = "Debt Fund (Always taxed at slab rate, assumed 30%)"
        else:  # GOLD, UNLISTED_SHARE, Immovable Property, etc.
            # Threshold is 24 months (2 years)
            if holding_months > 24:
                is_long_term = True
                tax_rate = 0.125  # 12.5% LTCG without indexation post July 2024
                details = "LTCG (Held > 24 months, taxed at 12.5% without indexation)"
            else:
                is_long_term = False
                tax_rate = 0.30  # Assumed slab rate of 30%
                details = "STCG (Held <= 24 months, taxed at slab rate, assumed 30%)"
                
        tax_liability = max(0.0, gains * tax_rate)
        if gains > 0:
            if is_long_term:
                total_ltcg += gains
                total_ltcg_tax += tax_liability
            else:
                total_stcg += gains
                total_stcg_tax += tax_liability
                
        results.append({
            "symbol": symbol,
            "asset_type": asset_type,
            "quantity": quantity,
            "holding_days": holding_days,
            "holding_months": round(holding_months, 2),
            "purchase_cost": purchase_cost,
            "sale_value": sale_value,
            "realized_gain": gains,
            "classification": "LTCG" if is_long_term else "STCG",
            "tax_rate_percent": tax_rate * 100,
            "tax_liability": tax_liability,
            "details": details
        })
        
    return {
        "transactions_analyzed": results,
        "summary": {
            "total_stcg": total_stcg,
            "total_ltcg": total_ltcg,
            "total_stcg_tax": total_stcg_tax,
            "total_ltcg_tax": total_ltcg_tax,
            "total_tax_liability": total_stcg_tax + total_ltcg_tax,
            "exemption_applied": "Note: ₹1.25 Lakh LTCG aggregate exemption applies globally on listed equities at filing."
        }
    }

@mcp.tool()
def regulatory_search(query: str) -> dict:
    """Retrieve regulatory information, tax rules, holding periods, and deadlines for India.
    
    Args:
        query: Search term (e.g. 'holding period', 'advance tax', 'tax rates').
    """
    q = query.lower()
    if "holding" in q or "period" in q or "short-term" in q or "long-term" in q or "stcg" in q or "ltcg" in q:
        return {
            "regulations": "Post Union Budget 2024 (effective July 23, 2024):",
            "listed_securities": "Holding period > 12 months is Long-Term (LTCG). Otherwise Short-Term (STCG).",
            "other_assets": "Holding period > 24 months (e.g. Property, Gold, Unlisted shares) is Long-Term (LTCG). Otherwise Short-Term (STCG).",
            "debt_mutual_funds": "Specified mutual funds (debt exposure > 65%) are always taxed at individual slab rates, no LTCG/indexation."
        }
    elif "advance" in q or "tax" in q or "deadline" in q or "milestone" in q:
        return {
            "advance_tax_installments_india": [
                {"deadline": "June 15", "percentage": "15% of estimated tax liability"},
                {"deadline": "September 15", "percentage": "45% of estimated tax liability"},
                {"deadline": "December 15", "percentage": "75% of estimated tax liability"},
                {"deadline": "March 15", "percentage": "100% of estimated tax liability"}
            ],
            "applicability": "Applicable if estimated tax liability exceeds ₹10,000 in a financial year."
        }
    elif "rate" in q or "percentage" in q or "slab" in q:
        return {
            "tax_rates_fy_2024_25": {
                "listed_equity_stcg": "20% (increased from 15% effective July 23, 2024)",
                "listed_equity_ltcg": "12.5% (increased from 10% effective July 23, 2024, with exemption limit of ₹1.25 Lakh)",
                "other_assets_stcg": "Taxed at individual slab rates (up to 30%+)",
                "other_assets_ltcg": "12.5% without indexation (indexation benefits removed for most assets after July 23, 2024)"
            }
        }
    else:
        return {
            "general_info": "India Capital Gains Tax Rules FY 2024-25 / FY 2025-26. Try searching for 'holding period', 'advance tax', or 'tax rates'."
        }

if __name__ == "__main__":
    mcp.run()
