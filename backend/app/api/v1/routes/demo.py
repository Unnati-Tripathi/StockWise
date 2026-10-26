import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.session import get_db
from scripts.seed_demo import seed

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/reset", status_code=status.HTTP_200_OK)
def reset_demo_data(db: Session = Depends(get_db)):
    if settings.environment != "development":
        raise HTTPException(status_code=403, detail="Demo reset is only available in development environment")
    
    try:
        seed(db)
        return {"status": "success", "message": "Demo data reset successfully"}
    except Exception as e:
        logger.error(f"Failed to reset demo data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to reset demo data: {str(e)}")
