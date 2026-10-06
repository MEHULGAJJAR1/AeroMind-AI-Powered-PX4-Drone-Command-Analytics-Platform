from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import operator_user
from app.models import User

router = APIRouter(prefix="/api/analytics", tags=["AI analytics"])


@router.get("/summary")
async def analytics_summary(request: Request, user: User = Depends(operator_user)) -> dict:
    state = request.app.state.hub.latest
    history = request.app.state.hub.history[-120:]
    return {
        "flight_risk_score": state["flight_risk_score"],
        "drone_health_score": state["drone_health_score"],
        "anomaly_count": state["anomaly_count"],
        "active_alerts": state["active_alerts"],
        "recommendations": state["recommendations"],
        "anomaly_timeline": [
            {
                "timestamp": item["timestamp"],
                "flight_risk_score": item["flight_risk_score"],
                "drone_health_score": item["drone_health_score"],
                "anomaly_count": item["anomaly_count"],
            }
            for item in history
        ],
        "history_samples": len(history),
        "model": "rules + rolling IsolationForest",
        "source": state["source"],
    }
