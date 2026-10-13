from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.schemas.replenishment import ReplenishmentList, ReplenishmentRecommendation, RiskLevel
from app.services.replenishment import generate_recommendations
from app.models.medicine import Medicine

router = APIRouter()

@router.get("/recommendations", response_model=ReplenishmentList)
def get_recommendations(
    lookback_days: int = Query(30, ge=1, le=365),
    safety_stock_days: int = Query(3, ge=0, le=30),
    expiry_warning_days: int = Query(60, ge=0, le=365),
    limit: int = Query(50, ge=1, le=500),
    skip: int = Query(0, ge=0),
    risk_level: Optional[RiskLevel] = Query(None),
    db: Session = Depends(get_db)
):
    return generate_recommendations(
        db=db,
        lookback_days=lookback_days,
        safety_stock_days=safety_stock_days,
        expiry_warning_days=expiry_warning_days,
        limit=limit,
        skip=skip,
        risk_level=risk_level
    )

@router.get("/recommendations/{medicine_id}", response_model=ReplenishmentRecommendation)
def get_recommendation_for_medicine(
    medicine_id: int,
    lookback_days: int = Query(30, ge=1, le=365),
    safety_stock_days: int = Query(3, ge=0, le=30),
    expiry_warning_days: int = Query(60, ge=0, le=365),
    db: Session = Depends(get_db)
):
    # Check if medicine exists
    medicine = db.get(Medicine, medicine_id)
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")
        
    if not medicine.is_active:
        raise HTTPException(status_code=422, detail="Replenishment recommendations are only available for active medicines")
        
    result = generate_recommendations(
        db=db,
        lookback_days=lookback_days,
        safety_stock_days=safety_stock_days,
        expiry_warning_days=expiry_warning_days,
        limit=1,
        skip=0,
        medicine_id=medicine_id
    )
    
    if not result.items:
        # Should not happen since we checked it exists and is active, but fallback
        raise HTTPException(status_code=404, detail="Recommendation could not be generated for this medicine")
        
    return result.items[0]
