# Routes init

from fastapi import APIRouter
from .health import router as health_router
from .medicines import router as medicines_router
from .suppliers import router as suppliers_router
from .inventory import router as inventory_router
from .demo import router as demo_router
from .replenishment import router as replenishment_router
from .invoices import router as invoices_router
from .assistant import router as assistant_router

router = APIRouter()
router.include_router(health_router, tags=["Health"])
router.include_router(medicines_router, prefix="/medicines", tags=["Medicines"])
router.include_router(suppliers_router, prefix="/suppliers", tags=["Suppliers"])
router.include_router(inventory_router, prefix="/inventory", tags=["Inventory"])
router.include_router(replenishment_router, prefix="/replenishment", tags=["Replenishment"])
router.include_router(invoices_router, prefix="/invoices", tags=["Invoices"])
router.include_router(assistant_router, prefix="/assistant", tags=["Assistant"])
router.include_router(demo_router, prefix="/demo", tags=["Demo"])
