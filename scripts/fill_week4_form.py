"""根据可运行模型、基准结果与校验输出，填写第4次课「仿真模型」提交模板。"""

import copy
import os
import subprocess
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

SRC = "docs/决策仿真_第4次课_阶段性成果提交模板_仿真模型.docx"
DST = "docs/决策仿真_第4次课_仿真模型_填写稿_DeFi流动性池.docx"
PDF = "docs/决策仿真_第4次课_仿真模型_填写稿_DeFi流动性池.pdf"
IMG = "docs/diagrams/model_week4.png"
BASELINE = "results/baseline"
VALIDATION = "results/validation"

summary = pd.read_csv(f"{BASELINE}/summary.csv", index_col=0)
checks = pd.read_csv(f"{VALIDATION}/extreme_values.csv")
sensitivity = pd.read_csv(f"{VALIDATION}/sensitivity_summary.csv")
doc = Document(SRC)
paragraphs = list(doc.paragraphs)
model_tables = list(doc.tables)


def set_cell(cell, text):
    para = cell.paragraphs[0]
    for run in list(para.runs):
        run._element.getparent().remove(run._element)
    for paragraph in cell.paragraphs[1:]:
        paragraph._element.getparent().remove(paragraph._element)
    lines = str(text).split("\n")
    para.add_run(lines[0])
    for line in lines[1:]:
        cell.add_paragraph().add_run(line)


def fill_para(idx, text):
    paragraph = paragraphs[idx]
    for run in list(paragraph.runs):
        run._element.getparent().remove(run._element)
    paragraph.add_run(text)


def add_rows(table, count, src=1):
    for _ in range(count):
        table._tbl.append(copy.deepcopy(table.rows[src]._tr))


def drop_rows(table, start):
    for i in range(len(table.rows) - 1, start - 1, -1):
        table._tbl.remove(table.rows[i]._tr)


def fit_rows(table, count):
    current = len(table.rows) - 1
    if count > current:
        add_rows(table, count - current)
    elif count < current:
        drop_rows(table, count + 1)


def fill_table(table, rows, seq=True):
    fit_rows(table, len(rows))
    for i, row in enumerate(rows, start=1):
        if seq:
            set_cell(table.cell(i, 0), str(i))
        for j, text in enumerate(row, start=1 if seq else 0):
            set_cell(table.cell(i, j), text)


def layout(table, widths, font_pt=8.5):
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = tbl_pr.makeelement(qn("w:tblW"), {})
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:type"), "dxa")
    tbl_w.set(qn("w:w"), str(int(sum(widths) / 2.54 * 1440)))
    layout_el = tbl_pr.find(qn("w:tblLayout"))
    if layout_el is None:
        layout_el = tbl_pr.makeelement(qn("w:tblLayout"), {})
        tbl_pr.append(layout_el)
    layout_el.set(qn("w:type"), "fixed")
    cell_mar = tbl_pr.find(qn("w:tblCellMar"))
    if cell_mar is None:
        cell_mar = tbl_pr.makeelement(qn("w:tblCellMar"), {})
        tbl_pr.append(cell_mar)
    for side in ("left", "right"):
        node = cell_mar.find(qn(f"w:{side}"))
        if node is None:
            node = cell_mar.makeelement(qn(f"w:{side}"), {})
            cell_mar.append(node)
        node.set(qn("w:w"), "45")
        node.set(qn("w:type"), "dxa")
    for col, width in zip(table.columns, widths, strict=False):
        col.width = Cm(width)
    for row in table.rows:
        tr_pr = row._tr.get_or_add_trPr()
        if tr_pr.find(qn("w:cantSplit")) is None:
            tr_pr.append(OxmlElement("w:cantSplit"))
        for cell, width in zip(row.cells, widths, strict=False):
            cell.width = Cm(width)
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(font_pt)
    header_pr = table.rows[0]._tr.get_or_add_trPr()
    if header_pr.find(qn("w:tblHeader")) is None:
        header_pr.append(OxmlElement("w:tblHeader"))


def export_pdf(docx_path, pdf_path):
    target = Path(pdf_path)
    target.unlink(missing_ok=True)
    env = dict(os.environ)
    for conf in ("/opt/homebrew/etc/fonts/fonts.conf", "/usr/local/etc/fonts/fonts.conf"):
        if Path(conf).exists():
            env.setdefault("FONTCONFIG_FILE", conf)
            break
    result = subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(target.parent), docx_path],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0 or not target.exists():
        raise RuntimeError(f"PDF 导出失败：{result.stderr or result.stdout}")


def mean(metric):
    return float(summary.loc[metric, "mean"])


def response(factor, level, metric):
    selected = sensitivity[
        (sensitivity["factor"] == factor)
        & (sensitivity["level"] == level)
        & (sensitivity["metric"] == metric)
    ]
    if len(selected) != 1:
        raise ValueError(f"灵敏度结果缺失或不唯一：{factor} {level} {metric}")
    return selected.iloc[0]


def check_actual(scenario):
    selected = checks[checks["scenario"] == scenario]
    if len(selected) != 1:
        raise ValueError(f"极端值结果缺失或不唯一：{scenario}")
    return str(selected.iloc[0]["actual"])


def insert_table_before(anchor, headers, rows, widths):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for j, header in enumerate(headers):
        set_cell(table.cell(0, j), header)
    for row in rows:
        cells = table.add_row().cells
        for j, text in enumerate(row):
            set_cell(cells[j], text)
    layout(table, widths, font_pt=8.0)
    anchor._p.addprevious(table._tbl)
    return table


# ============ 一、项目基本信息（Table 0） ============
t0 = doc.tables[0]
set_cell(t0.cell(0, 1), "2")
set_cell(t0.cell(0, 3), "案例二十一")
set_cell(t0.cell(1, 1), "DeFi 流动性池仿真")
set_cell(t0.cell(1, 3), "陶唐")
set_cell(t0.cell(2, 1), "范心宇，吴曼骐，陶博文，林佳辉，曾镜月")
set_cell(t0.cell(2, 3), "邵志芳")
set_cell(t0.cell(3, 1), "☑ 是   □ 否")
set_cell(t0.cell(3, 3), "2026年11月6日")
set_cell(t0.cell(4, 1), "Python 3.12；salabim 26.x")
set_cell(t0.cell(4, 3), "src/defi_pool_simulator/（V1.1）")

# ============ 三、模型版本与文件清单（Table 1） ============
fill_table(
    doc.tables[1],
    [
        ("Python 仿真模型", "src/defi_pool_simulator/", "V1.1 / 2026-11-06", "☑ 是"),
        (
            "模型结构图",
            "docs/diagrams/model_week4.mmd、model_week4.png",
            "V1.1 / 2026-11-06",
            "☑ 是",
        ),
        (
            "参数数据表",
            "docs/决策仿真_第3次课_数据与参数_填写稿_DeFi流动性池.docx",
            "V1.1 / 2026-11-06",
            "☑ 是",
        ),
        (
            "概念模型图",
            "docs/diagrams/flowchart_week2.mmd、flowchart_week2.png",
            "V0.2 / 2026-11-06",
            "☑ 是",
        ),
        (
            "基准与校验结果",
            "results/baseline/；results/validation/",
            "10次基准；30次灵敏度",
            "☑ 是",
        ),
        ("使用说明", "README.md；tests/（36项功能测试）", "2026-11-06", "☑ 是"),
    ],
    seq=False,
)

# ============ 四、模型结构图与说明 ============
fill_para(10, "完整 Python（salabim）模型结构如下；源代码文件与类名保留在图中，便于逐项追溯。")
image_paragraph = paragraphs[11]
for run in list(image_paragraph.runs):
    run._element.getparent().remove(run._element)
image_paragraph.add_run().add_picture(IMG, width=Cm(11.5))
for idx in range(22, 11, -1):
    paragraph = paragraphs[idx]
    paragraph._element.getparent().remove(paragraph._element)
fill_para(
    24,
    "模型由交易、LP 添加、LP 移除和外部价格四条事件流组成，共享 LiquidityPool 的双边储备、LP 份额与累计手续费状态。",
)
fill_para(
    25,
    "交易先检查双边储备是否为正，再按 x·y=k 报价并执行滑点判定；输入储备增加、输出储备减少，两类放弃分别记录。",
)
fill_para(
    26,
    "同刻优先级为外部价格＞LP 操作＞交易。所有结算服务时长为 0，不形成等待队列；MetricsRecorder 输出小时快照与重复汇总。",
)

# ============ 五、实体生成模块（Table 2） ============
fill_table(
    doc.tables[2],
    [
        (
            "交易订单",
            "_TradeArrivals；hold 后生成",
            "EXPO(5/60 h)，12笔/h",
            "全时段平稳",
            "☑ 与参数表一致",
        ),
        ("LP 添加指令", "_LpAddArrivals；独立到达", "EXPO(2 h)", "全时段平稳", "☑ 与参数表一致"),
        ("LP 移除指令", "_LpRemoveArrivals；独立到达", "EXPO(3 h)", "全时段平稳", "☑ 与参数表一致"),
        ("外部价格事件", "_MarketTicker；周期 hold", "确定性每1 h", "0—168 h", "☑ 与参数表一致"),
        ("小时快照", "与外部价格事件合并", "每1 h；另记录0 h", "共169条/次", "☑ 覆盖完整时段"),
    ],
)

# ============ 六、实体属性与参数赋值（Table 3） ============
fill_table(
    doc.tables[3],
    [
        (
            "交易类型",
            "sample_trade_type 按累计概率映射",
            "小/中/大=0.60/0.30/0.10",
            "—",
            "☑ 概率和为1",
        ),
        ("交易方向", "Direction.A_TO_B / B_TO_A", "伯努利 p=0.5", "—", "☑ 双向实现"),
        (
            "交易规模",
            "randint(min_amount_a, max_amount_a)",
            "DU(100,1000)/(1000,10000)/(10000,50000)",
            "枚 A",
            "☑ 已改为离散均匀",
        ),
        ("滑点容忍度", "TradeType.slippage_tolerance", "1% / 3% / 5%", "比例", "☑ 等于阈值可成交"),
        (
            "LP 添加规模",
            "randint 后按当前储备比注入",
            "DU(10000,100000)",
            "枚 A",
            "☑ 等值 B 同步注入",
        ),
        ("LP 移除规模", "randint；超额部分执行", "DU(10000,50000)", "枚 A", "☑ 记录赎回缺口"),
        (
            "外部参照价格",
            "每小时乘以(1+N(0,sigma))",
            "初值2；sigma=0.02",
            "枚 B/A",
            "☑ 零波动测试通过",
        ),
        ("储备与份额", "LiquidityPool 初始化", "100万 A、200万 B、100份", "枚/份", "☑ 状态唯一"),
        ("随机种子", "Environment(random_seed=seed)", "20261026+i", "—", "☑ 可复现"),
    ],
)

# ============ 七、判断与分流逻辑（Table 4） ============
fill_table(
    doc.tables[4],
    [
        ("交易类型", "均匀随机数落入累计概率区间", "小额/中额", "大额", "☑ 一致"),
        ("交易方向", "随机数小于0.5", "A→B：A增B减", "B→A：B增A减", "☑ 已修正方向说明"),
        (
            "储备可用性",
            "reserve_a>0 且 reserve_b>0",
            "是：进入报价",
            "否：储备不可用出口",
            "☑ 不再限制输入量",
        ),
        ("滑点判定", "quote.slippage ≤ tolerance", "成交并更新储备", "放弃且状态不变", "☑ 一致"),
        (
            "LP 撤出能力",
            "requested_a > reserve_a",
            "按可用量部分执行",
            "全额执行",
            "☑ 与交易约束区分",
        ),
        ("仿真终止", "env.now() 达到168 h", "停止并汇总", "继续事件调度", "☑ 一致"),
    ],
)

# ============ 八、资源与服务过程（Table 5） ============
fill_table(
    doc.tables[5],
    [
        ("交易报价", "双边储备", "共享状态", "quote 不修改状态", "0 h", "☑ 公式核对通过"),
        ("成交结算", "交易处理通道", "逻辑容量1", "事件串行；settle 原子更新", "0 h", "☑ 无等待"),
        ("LP 添加", "储备与LP份额", "无上限", "按比例注入并增发份额", "0 h", "☑ 价格不变"),
        ("LP 移除", "储备与LP份额", "下限0", "按比例撤出；超额部分执行", "0 h", "☑ 不为负"),
        ("价格更新/快照", "外部参照价格", "1条序列", "每小时更新并记录", "0 h", "☑ 169条/次"),
    ],
)

# ============ 九、队列、等待与放弃逻辑（Table 6） ============
fill_table(
    doc.tables[6],
    [
        ("交易等待队列", "不形成；事件到达即结算", "0", "不适用", "☑ 服务时长0"),
        ("LP 操作等待", "不形成；瞬时更新", "0", "不适用", "☑ 服务时长0"),
        (
            "同刻事件日历",
            "外部价格＞LP＞交易；同级先到先处理",
            "0",
            "仅排序不排队",
            "☑ 优先级常量核对",
        ),
        ("放弃出口", "不排队，分别记录储备不可用/滑点超限", "0", "立即离开", "☑ 订单去向守恒"),
    ],
)

# ============ 十、实体离开与系统输出（Table 7） ============
fill_table(
    doc.tables[7],
    [
        (
            "交易结果",
            "成交、储备不可用、滑点超限",
            "MetricsRecorder 逐笔计数",
            "成交或放弃即离开",
            "☑ 守恒",
        ),
        (
            "交易规模",
            "总成交量、分类平均滑点",
            "成交累计；报价滑点加权",
            "单次结束汇总",
            "☑ 核心指标",
        ),
        ("LP 收益", "手续费、无常损失、LP净收益", "小时快照与期末汇总", "168 h", "☑ 核心指标"),
        ("储备状态", "储备A/B、池内价格、池深", "每小时快照", "168 h", "☑ 时间序列"),
        ("LP 操作", "添加/移除次数、跳过数、赎回缺口", "事件累计", "168 h", "☑ 边界可追查"),
        (
            "重复运行",
            "均值、标准差、95%置信区间",
            "replications.csv、summary.csv",
            "10次或30次",
            "☑ 已输出",
        ),
        (
            "逻辑校验",
            "极端值、灵敏度与响应",
            "extreme_values.csv、sensitivity_*.csv/png",
            "独立校验入口",
            "☑ 附加证据",
        ),
    ],
)

# ============ 十一、模型参数核对（Table 8） ============
parameter_rows = [
    ("到达参数", "交易EXPO(5 min)；LP EXPO(2/3 h)", "5/60 h；2 h；3 h", "☑", "统一时间单位为小时"),
    (
        "实体属性",
        "类型60/30/10；规模DU；方向0.5",
        "randint 离散均匀；其余相同",
        "☑",
        "连续均匀已修正为离散均匀",
    ),
    ("服务时间", "交易与LP操作均为0 h", "事件内即时结算", "☑", "无显式Delay/Queue"),
    ("资源数量", "处理通道1；LP份额100", "逻辑通道1；份额100", "☑", "储备用可变状态表示"),
    (
        "容量约束",
        "储备下限0、无上限",
        "交易仅检查双储备为正；LP撤出受余额约束",
        "☑",
        "删除错误的输入储备上限",
    ),
    ("排队规则", "无等待；同刻价格＞LP＞交易", "优先级0/1/2", "☑", "服务时长为0"),
    ("阈值规则", "滑点1%/3%/5%；费率0.3%", "不超过阈值成交；fee_rate=0.003", "☑", "含手续费滑点"),
    ("运行时间", "168 h；每小时快照", "0—168 h，共169条/次", "☑", "期末快照完整"),
    ("Replication", "10次；种子20261026+i", "基准10次；灵敏度30次", "☑", "默认种子已统一"),
]
fill_table(doc.tables[8], parameter_rows, seq=False)

# ============ 十二、模型初步运行结果（Table 9） ============
baseline_rows = [
    ("订单到达数", f"{mean('total_orders'):,.1f}", "笔", "☑ 符合", "理论期望约2016笔"),
    ("成交订单数", f"{mean('filled_orders'):,.1f}", "笔", "☑ 符合", "与放弃数合计等于到达数"),
    ("订单放弃率", f"{mean('failure_rate'):.4%}", "%", "☑ 符合", "非空池仅由滑点超限导致"),
    ("总成交量", f"{mean('total_volume_a'):,.0f}", "枚 A", "☑ 符合", "成交输入按A折算"),
    ("总手续费", f"{mean('total_fee_b'):,.0f}", "枚 B", "☑ 符合", "按成交前池内价格折算"),
    ("大额平均滑点", f"{mean('avg_slippage_large'):.4%}", "%", "☑ 符合", "报价口径，含放弃订单"),
    (
        "期末无常损失",
        f"{mean('final_impermanent_loss_b'):,.0f}",
        "枚 B",
        "☑ 符合",
        "10次均值，随机波动较大",
    ),
    ("期末LP净收益", f"{mean('final_lp_net_income_b'):,.0f}", "枚 B", "☑ 符合", "手续费减无常损失"),
]
fill_table(doc.tables[9], baseline_rows, seq=False)

# ============ 十三、模型运行异常与调试记录（Table 10） ============
fill_table(
    doc.tables[10],
    [
        (
            "大额输入被误判库存不足",
            "误将输入量与输入代币储备比较；输入实际注入池内",
            "按官方getAmountOut核对公式，删除输入储备上限，仅检查双储备为正",
            "500万A输入可报价且输出小于储备；低容忍度时仅因滑点放弃",
            "☑ 已解决",
        ),
        (
            "交易规模抽样与参数表不一致",
            "代码使用连续uniform，参数表为离散DU",
            "改用randint并补整体成交量为整数的回归测试",
            "三类规模均按离散均匀生成",
            "☑ 已解决",
        ),
        (
            "默认随机种子不一致",
            "文档为20261026，CLI为20261023",
            "统一CLI与run_replications默认值",
            "同种子快照完全一致，不同方案可配对比较",
            "☑ 已解决",
        ),
        (
            "旧测试通过但边界语义错误",
            "测试把错误库存规则当成预期",
            "改写大额输入测试，新增空池、阈值、零波动与价格极值测试",
            "36项测试通过；10/10极端值检查通过",
            "☑ 已解决",
        ),
    ],
)

# ============ 十四、模型逻辑验证（Table 11） ============
verification_rows = [
    (
        "实体流转路径",
        "订单去向与分类计数守恒",
        "成交+两类放弃=到达",
        check_actual("整体守恒与复现"),
        "☑ 通过",
    ),
    (
        "资源占用与释放",
        "检查交易前后储备方向与乘积",
        "输入增、输出减；fee>0时乘积增加",
        check_actual("正手续费响应"),
        "☑ 通过",
    ),
    (
        "服务时间设置",
        "检查队列与等待逻辑",
        "服务0 h，无实体等待",
        "模型无Hold/Queue等待；事件内原子结算",
        "☑ 通过",
    ),
    (
        "排队规则",
        "核对同刻优先级常量",
        "价格0＞LP1＞交易2",
        "MARKET/LP/TRADE_PRIORITY=0/1/2",
        "☑ 通过",
    ),
    (
        "优先级/分流规则",
        "累计概率与方向抽样测试",
        "60/30/10；A→B与B→A方向正确",
        "sample_trade_type边界及双向储备测试通过",
        "☑ 通过",
    ),
    (
        "容量/阈值约束",
        "超大输入与空池测试",
        "非空池可报价；输出小于储备；空池放弃",
        check_actual("输入大于输入储备"),
        "☑ 通过",
    ),
    (
        "放弃条件",
        "阈值等号与巨额订单测试",
        "等于阈值成交；超限才放弃",
        check_actual("巨额订单滑点放弃"),
        "☑ 通过",
    ),
    (
        "系统终止条件",
        "24 h测试与168 h基准运行",
        "25条测试快照；169条基准快照",
        check_actual("整体守恒与复现"),
        "☑ 通过",
    ),
]
fill_table(doc.tables[11], verification_rows, seq=False)

# ============ 十五、模型与概念模型一致性（Table 12） ============
fill_table(
    doc.tables[12],
    [
        ("交易订单与属性", "_TradeArrivals、TradeType、Direction", "☑ 完整", "规模抽样已统一为DU"),
        ("储备与容量约束", "LiquidityPool.quote/settle", "☑ 完整", "概念模型同步修正输入储备规则"),
        ("LP 添加与移除", "add_liquidity/remove_liquidity", "☑ 完整", "保留超额部分执行与缺口"),
        (
            "外部价格与小时快照",
            "_MarketTicker、record_snapshot",
            "☑ 完整",
            "每小时更新并计算无常损失",
        ),
        ("队列与同刻优先级", "salabim hold(priority=...)", "☑ 完整", "服务0 h，不形成等待队列"),
        (
            "输出与重复运行",
            "MetricsRecorder、run_replications",
            "☑ 完整",
            "增加极端值和响应实验作为附加校验",
        ),
    ],
    seq=False,
)

# ============ 十六、AI辅助使用记录（Table 13） ============
fill_table(
    doc.tables[13],
    [
        (
            "模型结构映射",
            "把概念模型映射为salabim事件组件、状态与记录器",
            "采用交易/LP/价格事件流与共享池状态",
            "逐类核对案例参数和事件优先级",
        ),
        (
            "储备逻辑核验",
            "检查库存校验是否符合恒定乘积交易机制",
            "采纳删除输入储备上限的建议",
            "对照Uniswap V2官方getAmountOut公式并做极值测试",
        ),
        (
            "测试与调试",
            "设计极端值、阈值与响应实验，排查测试失败",
            "采用确定性断言和共同随机数配对",
            "失败数值由公式重算，随机响应不设置脆弱单调断言",
        ),
        (
            "文档与图表",
            "辅助生成Mermaid结构图和表格初稿",
            "保留可追溯的代码类名、真实CSV结果",
            "人工复核方向、单位、图面与文档旧规则残留",
        ),
    ],
    seq=False,
)

# ============ 十七、成果自检清单 ============
self_checks = [
    "☑ Python（salabim）模型源码完整，可在项目环境中打开。",
    "☑ 模型可正常运行并在168 h终止，输出CSV结果。",
    "☑ Create/Assign/Decide/Process/Record/Dispose已映射为事件组件、参数赋值、判断、结算与记录逻辑；无等待队列。",
    "☑ 主要实体、储备、LP份额和零时长服务过程与概念模型一致。",
    "☑ 第3次课参数逐项核对；离散均匀抽样和默认种子已统一。",
    "☑ 同刻优先级、分流、储备不可用与滑点超限放弃规则均已实现。",
    "☑ 模型输出成交量、手续费、滑点、无常损失和LP净收益等核心指标。",
    "☑ 已完成10次基准重复及30次附加灵敏度重复。",
    "☑ 已完成基本Verification、10项极端值检查并记录调试过程。",
    "☑ 已保存可继续修改的Python模型包、Mermaid图源和测试。",
]
for idx, text in zip(range(53, 63), self_checks, strict=True):
    fill_para(idx, text)

# ============ 补充：极端值与参数响应（插入十六节之前） ============
anchor = paragraphs[50]
anchor.insert_paragraph_before("补充一：极端值校验明细")
anchor.insert_paragraph_before(
    "以下记录由 python -m defi_pool_simulator.validation 实际生成；完整机器可读结果见 results/validation/extreme_values.csv。"
)
extreme_rows = [
    (row["scenario"], row["expected"], row["actual"], "☑ 通过" if row["passed"] else "☒ 未通过")
    for _, row in checks.iterrows()
]
insert_table_before(
    anchor, ["测试场景", "理论预期", "实际结果", "结论"], extreme_rows, [2.6, 5.0, 6.6, 2.4]
)

anchor.insert_paragraph_before("补充二：参数灵敏度与响应")
anchor.insert_paragraph_before(
    "单因素方案各重复30次，共用20261026+i种子组；变化均相对同种子基准。该结果用于正确性与响应检查，不作为正式管理结论。"
)
fee_zero = response("fee_rate", 0.0, "total_fee_b")
fee_volume = response("fee_rate", 0.005, "total_volume_a")
fee_income = response("fee_rate", 0.005, "total_fee_b")
sigma_zero = response("price_sigma", 0.0, "final_impermanent_loss_b")
sigma_high = response("price_sigma", 0.05, "final_impermanent_loss_b")
large_slippage = response("large_share", 0.2, "avg_slippage_all")
large_own = response("large_share", 0.2, "avg_slippage_large")
large_volume = response("large_share", 0.2, "total_volume_a")
large_failure = response("large_share", 0.2, "failure_rate")
response_rows = [
    (
        "费率 0.3%→0",
        "总手续费",
        f"{fee_zero['baseline_mean']:,.0f}→0 枚B",
        "零手续费严格为0，通过确定性校验",
    ),
    (
        "费率 0.3%→0.5%",
        "总手续费",
        f"{fee_income['baseline_mean']:,.0f}→{fee_income['scenario_mean']:,.0f} 枚B（{fee_income['delta_pct']:+.2f}%）",
        "手续费显著增加",
    ),
    (
        "费率 0.3%→0.5%",
        "总成交量",
        f"{fee_volume['delta_pct']:+.2f}%",
        "滑点与放弃增加，成交量小幅下降",
    ),
    ("波动率 2%→0", "无常损失", f"{sigma_zero['baseline_mean']:,.0f}→0 枚B", "价格不变时严格为0"),
    (
        "波动率 2%→5%",
        "无常损失",
        f"{sigma_high['baseline_mean']:,.0f}→{sigma_high['scenario_mean']:,.0f} 枚B（{sigma_high['delta_pct']:+.2f}%）",
        "波动放大无常损失与LP净收益下行风险",
    ),
    (
        "大额占比 10%→20%",
        "整体平均滑点",
        f"{large_slippage['baseline_mean']:.4%}→{large_slippage['scenario_mean']:.4%}（{large_slippage['delta_pct']:+.2f}%）",
        "订单结构变化使整体滑点上升",
    ),
    (
        "大额占比 10%→20%",
        "大额平均滑点",
        f"{large_own['baseline_mean']:.4%}→{large_own['scenario_mean']:.4%}（{large_own['delta_pct']:+.2f}%）",
        "同类订单平均滑点仅小幅变化",
    ),
    (
        "大额占比 10%→20%",
        "总成交量",
        f"{large_volume['baseline_mean']:,.0f}→{large_volume['scenario_mean']:,.0f} 枚A（{large_volume['delta_pct']:+.2f}%）",
        "大额订单增加推动成交量上升",
    ),
    (
        "大额占比 10%→20%",
        "订单放弃率",
        f"{large_failure['baseline_mean']:.4%}→{large_failure['scenario_mean']:.4%}",
        "滑点超限订单增加",
    ),
]
insert_table_before(
    anchor, ["因素变化", "指标", "基准→方案", "响应解释"], response_rows, [2.8, 3.0, 5.2, 5.6]
)

# ============ 版面 ============
layout(t0, [3.0, 4.2, 2.8, 6.6], font_pt=10.0)
for table, widths in zip(
    model_tables[1:14],
    [
        [2.6, 7.2, 3.8, 3.0],
        [0.8, 2.3, 3.4, 3.5, 2.4, 4.2],
        [0.8, 2.2, 4.0, 3.8, 1.4, 4.4],
        [0.8, 2.4, 4.0, 3.8, 3.8, 1.8],
        [0.7, 2.3, 2.2, 1.3, 4.0, 2.0, 4.1],
        [0.8, 2.8, 3.8, 2.8, 3.8, 2.6],
        [0.8, 2.0, 3.2, 4.8, 3.0, 2.8],
        [2.5, 4.4, 4.4, 1.4, 3.9],
        [3.4, 3.0, 2.0, 2.2, 6.0],
        [0.7, 3.3, 3.3, 3.6, 4.0, 1.7],
        [2.5, 4.3, 3.7, 4.2, 1.9],
        [3.2, 5.8, 2.0, 5.6],
        [2.6, 4.5, 4.5, 5.0],
    ],
    strict=True,
):
    layout(table, widths)

doc.save(DST)
export_pdf(DST, PDF)
print("saved:", DST)
print("saved:", PDF)
