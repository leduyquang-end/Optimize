from typing import Dict, Any, List

class LokiAdapter:
    """
    Adapter for querying Loki logs for real behavior metrics.
    """
    def __init__(self, loki_url: str = "http://localhost:3100"):
        self.loki_url = loki_url

    async def query_feature_logs(self, feature_id: str, time_range: str) -> List[Dict[str, Any]]:
        # Mock adapter implementation
        return [
            {
                "timestamp": "2026-10-08T09:00:00Z",
                "feature_id": feature_id,
                "step": "step_3_subflow",
                "latency_ms": 4800.0,
                "token_count": 1200,
                "status": "success"
            }
        ]
