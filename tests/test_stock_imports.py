from app.models.stock import OpeningStock, OpeningStockLine, StockAccount, StockMovement
from app.services.stock import StockService


def test_stock_modules_import():
    assert OpeningStock.__tablename__ == "opening_stocks"
    assert OpeningStockLine.__tablename__ == "opening_stock_lines"
    assert StockAccount.__tablename__ == "stock_accounts"
    assert StockMovement.__tablename__ == "stock_movements"
    assert StockService is not None
