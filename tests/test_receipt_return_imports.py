from app.models.receipt import Receipt, ReceiptLine
from app.models.stock_return import StockReturn, StockReturnLine
from app.services.receipt import ReceiptService
from app.services.stock_return import StockReturnService


def test_receipt_return_modules_import():
    assert Receipt.__tablename__ == "receipts"
    assert ReceiptLine.__tablename__ == "receipt_lines"
    assert StockReturn.__tablename__ == "stock_returns"
    assert StockReturnLine.__tablename__ == "stock_return_lines"
    assert ReceiptService is not None
    assert StockReturnService is not None
