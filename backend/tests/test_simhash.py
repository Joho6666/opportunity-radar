from app.services.simhash import hamming_distance, is_near_duplicate, simhash64


def test_identical_text_has_zero_distance():
    assert simhash64("AI 视频批量生成工具 求推荐") == simhash64("AI 视频批量生成工具 求推荐")
    assert hamming_distance(simhash64("abc"), simhash64("abc")) == 0


def test_similar_text_is_near_duplicate():
    left = simhash64("小商家不会做短视频内容，想找人批量生成 AI 视频")
    right = simhash64("小商家不会做短视频内容，想找人批量生成 AI 视频，预算有限")
    assert is_near_duplicate(left, right) is True


def test_different_text_is_not_near_duplicate():
    left = simhash64("AI 视频求推荐")
    right = simhash64("STM32 单片机毕业设计辅导，硬件调试求助")
    assert is_near_duplicate(left, right, threshold=12) is False


def test_empty_text_returns_zero_fingerprint():
    assert simhash64("") == 0
    assert is_near_duplicate(0, simhash64("anything")) is False
