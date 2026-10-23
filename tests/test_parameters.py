"""参数校验与交易类型抽样测试。"""

import pytest

from defi_pool_simulator.parameters import SimulationParameters, TradeType


def test_trade_type_sampling_follows_cumulative_probabilities() -> None:
    params = SimulationParameters()

    assert params.sample_trade_type(0.0).code == "small"
    assert params.sample_trade_type(0.599).code == "small"
    assert params.sample_trade_type(0.6).code == "medium"
    assert params.sample_trade_type(0.899).code == "medium"
    assert params.sample_trade_type(0.9).code == "large"
    assert params.sample_trade_type(0.999_999).code == "large"


def test_rejects_trade_probabilities_that_do_not_sum_to_one() -> None:
    trade_types = (
        TradeType("small", "小额", 0.5, 100.0, 1_000.0, 0.01),
        TradeType("large", "大额", 0.3, 10_000.0, 50_000.0, 0.05),
    )

    with pytest.raises(ValueError, match="概率之和"):
        SimulationParameters(trade_types=trade_types)


def test_rejects_invalid_lp_amount_range() -> None:
    with pytest.raises(ValueError, match="LP 添加规模区间"):
        SimulationParameters(lp_add_amount_a=(100_000, 10_000))
