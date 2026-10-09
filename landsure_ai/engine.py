from __future__ import annotations

from typing import List, Dict, Any


def calculate_risk_score(record: Dict[str, Any]) -> int:
    """Return a simple risk score for demonstration purposes."""
    score = 0

    if record.get("mutation_count", 0) > 3:
        score += 25
    if record.get("document_match_score", 0) < 75:
        score += 30
    if record.get("owner_mismatch"):
        score += 20
    if record.get("duplicate_entry"):
        score += 25

    return min(score, 100)


def get_risk_level(score: int) -> str:
    if score >= 75:
        return "High Risk"
    if score >= 45:
        return "Medium Risk"
    return "Low Risk"


def analyze_record(record: Dict[str, Any]) -> Dict[str, Any]:
    score = calculate_risk_score(record)
    flags = []

    if record.get("mutation_count", 0) > 3:
        flags.append("Multiple mutation entries")
    if record.get("document_match_score", 0) < 75:
        flags.append("Document mismatch detected")
    if record.get("owner_mismatch"):
        flags.append("Owner name mismatch")
    if record.get("duplicate_entry"):
        flags.append("Potential duplicate record")

    return {
        "record_id": record.get("record_id", "N/A"),
        "owner_name": record.get("owner_name", "Unknown"),
        "district": record.get("district", "Unknown"),
        "area_ha": record.get("area_ha", 0),
        "risk_score": score,
        "risk_level": get_risk_level(score),
        "flags": flags,
    }


def analyze_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [analyze_record(record) for record in records]
