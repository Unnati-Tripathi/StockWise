import os
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.config import settings
import subprocess

router = APIRouter()

@router.post("/reset", status_code=status.HTTP_200_OK)
def reset_demo_data():
    if settings.environment != "development":
        raise HTTPException(status_code=403, detail="Demo reset is only available in development environment")
    
    # Run the seed script
    script_path = os.path.join(os.path.dirname(__file__), "../../../../scripts/seed_demo.py")
    try:
        result = subprocess.run(
            ["python", os.path.abspath(script_path)],
            capture_output=True,
            text=True,
            check=True
        )
        return {"status": "success", "message": "Demo data reset successfully", "output": result.stdout}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset demo data: {e.stderr}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset demo data: {str(e)}")
