import os
import sys
import random
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import text

# Add the backend directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.medicine import Medicine
from app.models.supplier import Supplier
from app.models.inventory import InventoryBatch, StockMovement, MovementType
from app.models.associations import SupplierMedicine

def clear_existing_data(db):
    print("Clearing existing data...")
    # Using DELETE FROM to be compatible with both PostgreSQL and SQLite
    db.execute(text("DELETE FROM stock_movements"))
    db.execute(text("DELETE FROM supplier_medicines"))
    db.execute(text("DELETE FROM inventory_batches"))
    db.execute(text("DELETE FROM suppliers"))
    db.execute(text("DELETE FROM medicines"))
    db.commit()

def seed():
    if settings.environment != "development":
        print("Error: Seed script can only be run in development environment.")
        return

    random.seed(42)  # Deterministic seed

    db = SessionLocal()
    try:
        clear_existing_data(db)

        # 1. Create Suppliers
        print("Creating suppliers...")
        suppliers_data = [
            {"name": "MedCorp International", "contact": "Alice Smith", "email": "alice@medcorp.com"},
            {"name": "Global Pharma Supplies", "contact": "Bob Jones", "email": "bob@globalpharma.com"},
            {"name": "LocalHealth Distributors", "contact": "Carol White", "email": "carol@localhealth.com"},
            {"name": "FastMeds Logistics", "contact": "David Brown", "email": "david@fastmeds.com"},
        ]
        
        suppliers = []
        for s_data in suppliers_data:
            supplier = Supplier(
                name=s_data["name"],
                contact_person=s_data["contact"],
                email=s_data["email"],
                phone=f"555-{random.randint(1000, 9999)}",
                default_lead_time_days=random.randint(2, 7)
            )
            db.add(supplier)
            suppliers.append(supplier)
        db.commit()

        # 2. Create Medicines
        print("Creating medicines...")
        categories = ["Pain Relief", "Antibiotics", "Cardiovascular", "Vitamins", "Allergy"]
        base_units = ["strip", "bottle", "box", "piece"]
        
        medicines = []
        for i in range(1, 41):
            med = Medicine(
                code=f"MED{i:03d}",
                name=f"Fictional Medicine {i}",
                category=random.choice(categories),
                base_unit=random.choice(base_units)
            )
            db.add(med)
            medicines.append(med)
        db.commit()

        # 3. Create SupplierMedicines associations
        print("Creating supplier-medicine associations...")
        for med in medicines:
            # Each medicine is supplied by 1 to 3 suppliers
            num_suppliers = random.randint(1, 3)
            chosen_suppliers = random.sample(suppliers, num_suppliers)
            
            for supplier in chosen_suppliers:
                sm = SupplierMedicine(
                    supplier_id=supplier.id,
                    medicine_id=med.id,
                    supplier_product_code=f"SUP-{supplier.id}-{med.code}",
                    unit_purchase_price=Decimal(f"{random.uniform(5.0, 50.0):.2f}"),
                    minimum_order_quantity=random.choice([10, 50, 100]),
                    lead_time_days=supplier.default_lead_time_days + random.randint(-1, 2)
                )
                db.add(sm)
        db.commit()

        # 4. Create Inventory Batches and Stock Movements
        print("Creating inventory batches and stock movements...")
        today = date.today()
        
        for med in medicines:
            num_batches = random.randint(1, 4)
            for b in range(num_batches):
                # Receipt
                qty_received = random.randint(100, 500)
                unit_price = Decimal(f"{random.uniform(5.0, 50.0):.2f}")
                expiry_offset = random.randint(-30, 365)  # Some might be expired
                expiry = today + timedelta(days=expiry_offset)
                
                batch = InventoryBatch(
                    medicine_id=med.id,
                    batch_number=f"BATCH-{med.code}-{b+1}",
                    expiry_date=expiry,
                    quantity_on_hand=qty_received,
                    unit_purchase_price=unit_price
                )
                db.add(batch)
                db.commit()
                
                receipt_movement = StockMovement(
                    medicine_id=med.id,
                    batch_id=batch.id,
                    movement_type=MovementType.RECEIPT,
                    quantity_change=qty_received,
                    unit_cost=unit_price,
                    reference=f"PO-{random.randint(1000, 9999)}"
                )
                db.add(receipt_movement)
                
                # Simulate some sales
                num_sales = random.randint(0, 5)
                for _ in range(num_sales):
                    if batch.quantity_on_hand <= 0:
                        break
                        
                    sale_qty = random.randint(1, min(20, batch.quantity_on_hand))
                    sale_movement = StockMovement(
                        medicine_id=med.id,
                        batch_id=batch.id,
                        movement_type=MovementType.SALE,
                        quantity_change=-sale_qty,
                        reference=f"INV-{random.randint(10000, 99999)}"
                    )
                    batch.quantity_on_hand -= sale_qty
                    db.add(sale_movement)
                    
        db.commit()
        print("Demo data seeded successfully.")

    except Exception as e:
        db.rollback()
        print(f"Error seeding data: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
