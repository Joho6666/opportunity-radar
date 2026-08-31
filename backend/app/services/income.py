from ..schemas.domain import OpportunityRead


def potential_income_range(opportunities: list[OpportunityRead]) -> tuple[int, int]:
    """Estimate income as recommended budget range weighted by conversion probability."""
    recommended = [item for item in opportunities if item.recommendation == "强烈推荐"]
    low = sum(round(item.budget_min * item.conversion_probability / 100) for item in recommended)
    high = sum(round(item.budget_max * item.conversion_probability / 100) for item in recommended)
    return low, high
