import pytest
from app.models.medicine import Medicine
from app.models.supplier import Supplier
from app.models.inventory import InventoryBatch, StockMovement
from app.models.associations import SupplierMedicine
from app.db.base import Base

def test_models_importable():
    # If this test runs, it means all models can be successfully imported
    # and SQLAlchemy is able to compile their declarative mappings.
    assert hasattr(Medicine, "__tablename__")
    assert hasattr(Supplier, "__tablename__")
    assert hasattr(InventoryBatch, "__tablename__")
    assert hasattr(StockMovement, "__tablename__")
    assert hasattr(SupplierMedicine, "__tablename__")

def test_metadata_contains_tables():
    tables = Base.metadata.tables
    assert "medicines" in tables
    assert "suppliers" in tables
    assert "inventory_batches" in tables
    assert "stock_movements" in tables
    assert "supplier_medicines" in tables
