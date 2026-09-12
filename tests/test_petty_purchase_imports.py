from app.models.petty_purchase import PettyPurchase, PettyPurchaseLine
from app.services.petty_purchase import PettyPurchaseService


def test_petty_purchase_module_import():
    assert PettyPurchase.__tablename__ == "petty_purchases"
    assert PettyPurchaseLine.__tablename__ == "petty_purchase_lines"
    assert PettyPurchaseService is not None
