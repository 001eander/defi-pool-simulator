"""仿真参数与基准情景配置。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

_PROBABILITY_TOLERANCE = 1e-9


@dataclass(frozen=True)
class TradeType:
    """交易类型：出现概率、规模区间与滑点容忍度。"""

    code: str
    label: str
    probability: float
    min_amount_a: float
    max_amount_a: float
    slippage_tolerance: float

    def __post_init__(self) -> None:
        if not self.code or not self.label:
            raise ValueError("交易类型的编码与名称不能为空")
        if not 0.0 < self.probability <= 1.0:
            raise ValueError(f"{self.code} 的出现概率必须在 (0, 1] 内")
        if self.min_amount_a <= 0.0 or self.max_amount_a < self.min_amount_a:
            raise ValueError(f"{self.code} 的规模区间无效")
        if not 0.0 < self.slippage_tolerance < 1.0:
            raise ValueError(f"{self.code} 的滑点容忍度必须在 (0, 1) 内")


def default_trade_types() -> tuple[TradeType, ...]:
    """案例给定的三类交易，概率合计为 1。"""
    return (
        TradeType("small", "小额", 0.60, 100.0, 1_000.0, 0.01),
        TradeType("medium", "中额", 0.30, 1_000.0, 10_000.0, 0.03),
        TradeType("large", "大额", 0.10, 10_000.0, 50_000.0, 0.05),
    )


@dataclass(frozen=True)
class SimulationParameters:
    """一次仿真运行所需的全部输入参数，时间单位为小时。"""

    duration_hours: float = 168.0
    initial_reserve_a: float = 1_000_000.0
    initial_reserve_b: float = 2_000_000.0
    initial_lp_shares: float = 100.0
    initial_external_price: float = 2.0
    fee_rate: float = 0.003
    trade_arrival_mean_hours: float = 5.0 / 60.0
    lp_add_mean_hours: float = 2.0
    lp_remove_mean_hours: float = 3.0
    lp_add_amount_a: tuple[int, int] = (10_000, 100_000)
    lp_remove_amount_a: tuple[int, int] = (10_000, 50_000)
    price_sigma: float = 0.02
    direction_a_to_b_probability: float = 0.5
    trade_types: tuple[TradeType, ...] = field(default_factory=default_trade_types)

    def __post_init__(self) -> None:
        if self.duration_hours <= 0.0:
            raise ValueError("仿真时长必须为正")
        if self.initial_reserve_a <= 0.0 or self.initial_reserve_b <= 0.0:
            raise ValueError("初始储备必须为正")
        if self.initial_lp_shares <= 0.0:
            raise ValueError("初始 LP 份额必须为正")
        if self.initial_external_price <= 0.0:
            raise ValueError("初始外部价格必须为正")
        if not 0.0 <= self.fee_rate < 1.0:
            raise ValueError("手续费率必须在 [0, 1) 内")
        if self.trade_arrival_mean_hours <= 0.0:
            raise ValueError("交易到达间隔均值必须为正")
        if self.lp_add_mean_hours <= 0.0 or self.lp_remove_mean_hours <= 0.0:
            raise ValueError("LP 到达间隔均值必须为正")
        if self.lp_add_amount_a[0] <= 0 or self.lp_add_amount_a[1] < self.lp_add_amount_a[0]:
            raise ValueError("LP 添加规模区间无效")
        if (
            self.lp_remove_amount_a[0] <= 0
            or self.lp_remove_amount_a[1] < self.lp_remove_amount_a[0]
        ):
            raise ValueError("LP 移除规模区间无效")
        if self.price_sigma < 0.0:
            raise ValueError("价格波动率不能为负")
        if not 0.0 <= self.direction_a_to_b_probability <= 1.0:
            raise ValueError("A→B 方向概率必须在 [0, 1] 内")
        if not self.trade_types:
            raise ValueError("至少需要一类交易")
        if len({t.code for t in self.trade_types}) != len(self.trade_types):
            raise ValueError("交易类型编码不能重复")
        total_probability = sum(t.probability for t in self.trade_types)
        if not math.isclose(total_probability, 1.0, abs_tol=_PROBABILITY_TOLERANCE):
            raise ValueError("交易类型概率之和必须为 1")

    def sample_trade_type(self, u: float) -> TradeType:
        """按累计概率区间把 [0, 1) 上的随机数映射为交易类型。"""
        cumulative = 0.0
        for trade_type in self.trade_types:
            cumulative += trade_type.probability
            if u < cumulative:
                return trade_type
        return self.trade_types[-1]
