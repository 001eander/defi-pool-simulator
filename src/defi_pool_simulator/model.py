"""基于 salabim 的离散事件仿真模型。"""

from __future__ import annotations

import salabim as sim

from .amm import Direction, LiquidityPool
from .metrics import MetricsRecorder, SimulationResult
from .parameters import SimulationParameters, TradeType

# 同一时刻的事件按「外部价格 > LP 操作 > 交易」处理，数值越小越先执行。
MARKET_PRIORITY = 0
LP_PRIORITY = 1
TRADE_PRIORITY = 2


class _TradeArrivals(sim.Component):
    def setup(
        self,
        pool: LiquidityPool,
        recorder: MetricsRecorder,
        params: SimulationParameters,
    ) -> None:
        self.pool = pool
        self.recorder = recorder
        self.params = params

    def process(self) -> None:
        rng = self.env.random
        while True:
            self.hold(
                rng.expovariate(1.0 / self.params.trade_arrival_mean_hours),
                priority=TRADE_PRIORITY,
            )
            self._handle_order()

    def _handle_order(self) -> None:
        params = self.params
        rng = self.env.random
        trade_type = params.sample_trade_type(rng.random())
        direction = (
            Direction.A_TO_B
            if rng.random() < params.direction_a_to_b_probability
            else Direction.B_TO_A
        )
        size_a = rng.uniform(trade_type.min_amount_a, trade_type.max_amount_a)
        execute_trade(self.pool, self.recorder, trade_type, direction, size_a)


def execute_trade(
    pool: LiquidityPool,
    recorder: MetricsRecorder,
    trade_type: TradeType,
    direction: Direction,
    size_a: float,
) -> None:
    """执行一笔交易：库存校验、定价、滑点判定与成交或放弃。"""
    recorder.record_order(trade_type)
    if pool.reserve_a <= 0.0 or pool.reserve_b <= 0.0:
        recorder.record_inventory_failure(trade_type)
        return

    # 案例以枚 A 定义交易规模；B→A 订单按池内即时价折算为等值 B 输入。
    amount_in = size_a if direction is Direction.A_TO_B else size_a * pool.spot_price

    # 交易在事件循环中串行结算，服务时长为 0，无需显式 Resource 或 Queue。
    if not pool.can_fill(direction, amount_in):
        recorder.record_inventory_failure(trade_type)
        return

    quote = pool.quote(direction, amount_in)
    recorder.record_slippage(trade_type, quote.slippage)
    if quote.slippage > trade_type.slippage_tolerance:
        recorder.record_slippage_failure(trade_type)
        return

    pool.settle(quote)
    recorder.record_fill(trade_type, size_a)


class _LpAddArrivals(sim.Component):
    def setup(
        self, pool: LiquidityPool, recorder: MetricsRecorder, params: SimulationParameters
    ) -> None:
        self.pool = pool
        self.recorder = recorder
        self.params = params

    def process(self) -> None:
        rng = self.env.random
        while True:
            self.hold(rng.expovariate(1.0 / self.params.lp_add_mean_hours), priority=LP_PRIORITY)
            amount_a = rng.randint(*self.params.lp_add_amount_a)
            self.recorder.record_lp_add(self.pool.add_liquidity(amount_a))


class _LpRemoveArrivals(sim.Component):
    def setup(
        self, pool: LiquidityPool, recorder: MetricsRecorder, params: SimulationParameters
    ) -> None:
        self.pool = pool
        self.recorder = recorder
        self.params = params

    def process(self) -> None:
        rng = self.env.random
        while True:
            self.hold(rng.expovariate(1.0 / self.params.lp_remove_mean_hours), priority=LP_PRIORITY)
            requested_a = rng.randint(*self.params.lp_remove_amount_a)
            self.recorder.record_lp_remove(self.pool.remove_liquidity(requested_a))


class _MarketTicker(sim.Component):
    def setup(
        self,
        pool: LiquidityPool,
        recorder: MetricsRecorder,
        params: SimulationParameters,
    ) -> None:
        self.pool = pool
        self.recorder = recorder
        self.params = params
        self.external_price = params.initial_external_price

    def process(self) -> None:
        while True:
            self.hold(1.0, priority=MARKET_PRIORITY)
            if self.env.now() > self.params.duration_hours:
                break
            self.external_price = max(
                self.external_price * (1.0 + self.env.random.gauss(0.0, self.params.price_sigma)),
                1e-9,
            )
            self.recorder.record_snapshot(
                self.env.now(),
                self.pool,
                self.external_price,
                self.params.initial_external_price,
            )


def run_once(params: SimulationParameters, seed: int) -> SimulationResult:
    """运行一次重复仿真，返回标量指标与小时快照。"""
    env = sim.Environment(trace=False, random_seed=seed, time_unit="hours")
    pool = LiquidityPool(
        reserve_a=params.initial_reserve_a,
        reserve_b=params.initial_reserve_b,
        fee_rate=params.fee_rate,
        initial_shares=params.initial_lp_shares,
    )
    recorder = MetricsRecorder()
    recorder.record_snapshot(
        0.0,
        pool,
        params.initial_external_price,
        params.initial_external_price,
    )
    _TradeArrivals(env=env, pool=pool, recorder=recorder, params=params)
    _LpAddArrivals(env=env, pool=pool, recorder=recorder, params=params)
    _LpRemoveArrivals(env=env, pool=pool, recorder=recorder, params=params)
    ticker = _MarketTicker(env=env, pool=pool, recorder=recorder, params=params)
    env.run(till=params.duration_hours)
    if recorder.snapshots[-1]["time_h"] < env.now():
        recorder.record_snapshot(
            env.now(),
            pool,
            ticker.external_price,
            params.initial_external_price,
        )
    return recorder.build_result(seed, pool, params)
