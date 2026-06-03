from app.services.analytics_service import calculate_tier


def test_calculate_tier_uses_expected_boundaries():
    assert calculate_tier(0)["name"] == "Bronze"
    assert calculate_tier(200)["name"] == "Bronze"
    assert calculate_tier(201)["name"] == "Silver"
    assert calculate_tier(500)["name"] == "Silver"
    assert calculate_tier(501)["name"] == "Gold"
    assert calculate_tier(1001)["name"] == "Platinum"
    assert calculate_tier(2001)["name"] == "DevOps Master"


def test_calculate_tier_progress_stays_in_range():
    for score in (0, 20, 200, 201, 500, 501, 1000, 1001, 2000, 2001, 10000):
        progress = calculate_tier(score)["progress"]
        assert 0 <= progress <= 100
