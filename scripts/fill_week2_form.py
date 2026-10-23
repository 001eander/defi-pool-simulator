"""根据第1次课问题定义与 README 案例参数，填写第2次课「概念模型」提交模板。"""

import copy
import os
import subprocess
from pathlib import Path

from docx import Document
from docx.enum.text import WD_BREAK
from docx.shared import Cm

SRC = "docs/决策仿真_第2次课_阶段性成果提交模板_概念模型.docx"
DST = "docs/决策仿真_第2次课_概念模型_填写稿_DeFi流动性池.docx"
PDF = "docs/决策仿真_第2次课_概念模型_填写稿_DeFi流动性池.pdf"
IMG = "docs/diagrams/flowchart_week2.png"

doc = Document(SRC)


def set_cell(cell, text):
    """清空单元格并写入文本（保留首段格式）。"""
    para = cell.paragraphs[0]
    for r in list(para.runs):
        r._element.getparent().remove(r._element)
    for p in cell.paragraphs[1:]:
        p._element.getparent().remove(p._element)
    lines = text.split("\n")
    para.add_run(lines[0])
    for ln in lines[1:]:
        np = cell.add_paragraph()
        np.add_run(ln)


def fill_para(idx, text):
    """把下划线占位段落替换为正文。"""
    p = doc.paragraphs[idx]
    for r in list(p.runs):
        r._element.getparent().remove(r._element)
    p.add_run(text)


def clear_paras(indices):
    for i in indices:
        p = doc.paragraphs[i]
        for r in list(p.runs):
            r._element.getparent().remove(r._element)


def fill_table(table, rows, start=1):
    """按表头是否含序号列决定内容起始列。"""
    start_col = 1 if len(rows[0]) + 1 == len(table.columns) else 0
    has_seq = table.cell(0, 0).text.strip() == "序号"
    for i, row in enumerate(rows, start=start):
        if has_seq:
            set_cell(table.cell(i, 0), str(i))
        for j, txt in enumerate(row, start=start_col):
            set_cell(table.cell(i, j), txt)


def export_pdf(docx_path, pdf_path):
    """用 LibreOffice 无头模式导出 PDF，版式与 docx 一致。"""
    target = Path(pdf_path)
    target.unlink(missing_ok=True)
    env = dict(os.environ)
    # LibreOffice 26.8 在 macOS 上默认读不到系统中文字体，需显式指定 fontconfig 配置。
    for conf in ("/opt/homebrew/etc/fonts/fonts.conf", "/usr/local/etc/fonts/fonts.conf"):
        if Path(conf).exists():
            env.setdefault("FONTCONFIG_FILE", conf)
            break
    try:
        result = subprocess.run(
            [
                "soffice",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(target.parent),
                docx_path,
            ],
            capture_output=True,
            text=True,
            env=env,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 soffice，请先安装 LibreOffice") from exc
    if result.returncode != 0 or not target.exists():
        raise RuntimeError(f"PDF 导出失败：{result.stderr or result.stdout}")


def add_rows(table, count, src=1):
    """按模板行格式追加空行，返回追加的行。"""
    for _ in range(count):
        table._tbl.append(copy.deepcopy(table.rows[src]._tr))


def drop_rows(table, start):
    """从 start 行起删除末尾多余空行。"""
    for i in range(len(table.rows) - 1, start - 1, -1):
        table._tbl.remove(table.rows[i]._tr)


# ============ 一、项目基本信息（Table 0） ============
t0 = doc.tables[0]
set_cell(t0.cell(0, 1), "2")
set_cell(t0.cell(0, 3), "案例二十一")
set_cell(t0.cell(1, 1), "DeFi 流动性池仿真")
set_cell(t0.cell(1, 3), "陶唐")
set_cell(t0.cell(2, 1), "范心宇，吴曼骐，陶博文，林佳辉，曾镜月")
set_cell(t0.cell(2, 3), "邵志芳")
set_cell(t0.cell(3, 1), "☑ 是   □ 否")
set_cell(t0.cell(3, 3), "2026年10月23日")
set_cell(t0.cell(4, 1), "☑ Arena   ☑ 其他：Python（salabim）")
set_cell(t0.cell(4, 3), "V0.1（概念模型初稿）")

# ============ 三、仿真对象与系统边界确认（Table 1 + P9–P11） ============
t1 = doc.tables[1]
fill_table(
    t1,
    [
        (
            "交易订单按 EXPO(5 min) 到达；LP 添加、移除分别按 EXPO(2 h)、EXPO(3 h) 到达；"
            "外部价格事件与小时快照每 1 h 触发",
            "☑ 是   □ 否",
            "各到达流相互独立，共用一条事件日历",
        ),
        (
            "恒定乘积定价、滑点判定与成交结算；LP 增减储备与份额记账；小时价格更新与无常损失结算",
            "☑ 是   □ 否",
            "服务时长为 0，状态更新由事件直接完成",
        ),
        (
            "池内 Token A、Token B 储备构成可消耗资源，交易与撤资竞争同一份池深；LP 份额为记账资源",
            "☑ 是   □ 否",
            "储备无上限、下限为 0，余额不足构成放弃条件",
        ),
        (
            "不设实体等待队列，订单到达即结算",
            "□ 是   ☑ 否",
            "同刻事件仅按优先级排序，不形成排队，见第七节",
        ),
        (
            "成交交易离开系统；滑点超限或库存不足的交易作为放弃出口离开",
            "☑ 是   □ 否",
            "两类出口分别计数，失败按三类交易分组",
        ),
    ],
)

fill_para(
    9,
    "1. 池内储备的处理方式改变：第1次课把 Token A、Token B 储备当作状态变量，"
    "本次提升为受约束的核心资源，单笔交易与单次撤资都不得超过对应代币的可用余额，"
    "余额不足即判为失败，从「库存不足」出口离开。",
)
fill_para(
    10,
    "2. 外部价格事件与小时快照纳入同一事件日历，并规定同一时刻的处理顺序为"
    "「外部价格 > LP 操作 > 交易」，保证各次重复仿真中的状态更新顺序一致。",
)
fill_para(
    11,
    "3. 交易方向（A→B 或 B→A）在案例中未给参数，本次按各 50% 固定为建模假设。"
    "跨交易所套利、gas 费与确认延迟、外部价格对池内交易的反馈、LP 行为对收益的响应"
    "仍不纳入，理由与第1次课相同。",
)

# ============ 四、实体定义（Table 2 + P15–P17） ============
t2 = doc.tables[2]
fill_table(
    t2,
    [
        (
            "交易订单",
            "类型（小/中/大额）、方向（A→B 或 B→A）、输入量（枚）、滑点容忍度（1%/3%/5%）、到达时刻",
            "按 EXPO(5 min) 独立到达",
            "成交或放弃后离开",
        ),
        (
            "LP 添加指令",
            "添加规模（1 万—10 万枚 A，离散均匀）、到达时刻",
            "按 EXPO(2 h) 到达",
            "完成 A/B 注入与份额记账后离开",
        ),
        (
            "LP 移除指令",
            "移除规模（1 万—5 万枚 A，离散均匀）、到达时刻",
            "按 EXPO(3 h) 到达",
            "完成 A/B 撤出与份额扣减后离开",
        ),
        (
            "外部价格事件",
            "触发时刻、每小时价格变化率",
            "每 1 h 周期触发",
            "更新参照价格、结算无常损失后离开",
        ),
        (
            "小时快照",
            "采样时刻、储备 A/B、池内价格、累计手续费、无常损失",
            "每 1 h 触发，与外部价格事件同刻",
            "写入时间序列后离开",
        ),
    ],
)
drop_rows(t2, 6)

fill_para(
    15,
    "无实体转化、合并或批处理。分流有两处：交易经滑点判定分为成交与放弃两路；"
    "LP 指令按添加/移除分为两路。交易方向决定消耗哪一种储备，属于资源消耗方向的分流。",
)
clear_paras([16, 17])

# ============ 五、资源与容量约束（Table 3 + P20–P22） ============
t3 = doc.tables[3]
fill_table(
    t3,
    [
        (
            "Token A 储备",
            "初始 100 万枚；随交易与 LP 操作变化，无上限，下限为 0",
            "A→B 交易输出、LP 添加注入、LP 移除撤出",
            "按当前余额扣减或增加，余额不足则判定交易失败",
            "是：大额交易与集中撤资时",
        ),
        (
            "Token B 储备",
            "初始 200 万枚；同上",
            "B→A 交易输出、LP 添加注入、LP 移除撤出",
            "按当前余额扣减或增加，余额不足则判定交易失败",
            "是：大额交易与集中撤资时",
        ),
        (
            "LP 份额",
            "初始 100%，随添加/移除变化，无上限",
            "全部 LP 操作",
            "按注入价值占池深比例增发，按份额比例赎回",
            "否",
        ),
        (
            "交易处理通道",
            "1 个，瞬时占用，服务时长 0",
            "每笔交易",
            "同刻只结算一笔交易，不排队",
            "否",
        ),
    ],
)
drop_rows(t3, 5)

fill_para(
    20,
    "双边储备被交易与 LP 操作共同消耗：大额交易与集中撤资竞争同一份池深，两类主体无优先级差异，"
    "按到达时刻先后处理。LP 份额只被 LP 操作读写，与交易不竞争。"
    "交易处理通道为全局独占，但服务时长为 0，实际不构成竞争。",
)
clear_paras([21])

# ============ 六、事件与活动（Table 4） ============
t4 = doc.tables[4]
add_rows(t4, 1, src=8)
fill_table(
    t4,
    [
        (
            "交易订单到达",
            "按 EXPO(5 min) 抽到下一到达时刻",
            "生成订单实体，抽取类型、方向、输入量与容忍度；系统订单数 +1",
            "瞬时（间隔 EXPO 5 min）",
            "Token A/B 储备",
        ),
        (
            "库存校验",
            "订单到达后立即触发",
            "比较输入量与对应代币可用余额，不足则转入放弃出口",
            "0",
            "Token A/B 储备",
        ),
        (
            "定价与滑点判定",
            "库存充足",
            "按 x·y=k 计算成交价、滑点与手续费，与容忍度比较",
            "0",
            "Token A/B 储备",
        ),
        (
            "成交结算",
            "滑点不超过容忍度",
            "扣减输入代币、增加输出代币、手续费回流池中；累计成交量、手续费与滑点",
            "0",
            "Token A/B 储备",
        ),
        (
            "交易放弃",
            "库存不足或滑点超限",
            "失败笔数 +1，按交易类型分组统计，订单离开系统",
            "0",
            "无",
        ),
        (
            "LP 添加流动性",
            "按 EXPO(2 h) 抽到到达时刻",
            "抽取添加规模，按当前储备比例注入 A/B，池深与 LP 份额增加",
            "瞬时（间隔 EXPO 2 h）",
            "Token A/B 储备、LP 份额",
        ),
        (
            "LP 移除流动性",
            "按 EXPO(3 h) 抽到到达时刻",
            "抽取移除规模，按份额比例撤出 A/B，不足时按可用量部分执行；池深与份额减少",
            "瞬时（间隔 EXPO 3 h）",
            "Token A/B 储备、LP 份额",
        ),
        (
            "外部价格更新与小时快照",
            "每 1 h 定时触发",
            "参照价格乘以 (1+N(0,2%))；结算 LP 无常损失；记录储备、价格与手续费快照",
            "0（周期 1 h）",
            "无（外生输入）",
        ),
        (
            "仿真结束",
            "仿真时钟达到 168 h",
            "停止事件调度，汇总指标并输出结果",
            "0",
            "释放全部资源",
        ),
    ],
)

# ============ 七、队列与等待逻辑（Table 5） ============
t5 = doc.tables[5]
fill_table(
    t5,
    [
        (
            "交易等待队列",
            "交易订单",
            "不形成：订单到达后立即结算，服务时长为 0",
            "不适用",
            "无等待，结算完成即离开",
        ),
        (
            "同刻事件排序",
            "同时刻到期的交易、LP 指令、价格事件",
            "事件日历出现相同触发时刻",
            "优先级：外部价格更新 > LP 操作 > 交易；同级按到达顺序排序",
            "处理完即按序取下一事件",
        ),
        (
            "放弃统计",
            "库存不足或滑点超限的交易",
            "库存校验或滑点判定不通过",
            "不排队，直接离开并计入失败笔数",
            "立即离开",
        ),
        (
            "LP 操作等待",
            "LP 指令",
            "不形成：注入与撤出瞬时完成",
            "不适用",
            "操作完成即离开",
        ),
    ],
)
drop_rows(t5, 5)

# ============ 八、决策规则与逻辑判断（Table 6） ============
t6 = doc.tables[6]
fill_table(
    t6,
    [
        (
            "交易方向分流",
            "随机数小于 0.5",
            "A→B：输入 A、输出 B，扣减储备 A",
            "B→A：输入 B、输出 A，扣减储备 B",
        ),
        (
            "交易类型分流",
            "均匀随机数落入累计概率区间",
            "r<0.6 为小额：UNIF(100,1000)，容忍度 1%",
            "r≥0.6 转下一节点：r<0.9 为中额 UNIF(1000,10000)、3%；否则为大额 UNIF(10000,50000)、5%",
        ),
        (
            "库存是否充足",
            "输入量大于对应代币余额",
            "是：判为失败，走放弃出口",
            "否：进入定价与滑点计算",
        ),
        (
            "滑点是否在容忍度内",
            "（成交均价 − 池内即时价）/ 池内即时价 ≤ 该类交易容忍度",
            "是：成交，更新储备、手续费并记录",
            "否：放弃，计入失败笔数",
        ),
        (
            "撤出量是否可满足",
            "申请移除量大于当前可用储备",
            "是：按可用量部分执行，记录缺口",
            "否：全额执行",
        ),
        (
            "仿真是否终止",
            "仿真时钟达到 168 h",
            "是：停止调度并输出统计",
            "否：取下一事件继续",
        ),
    ],
)

# ============ 九、状态变量与关键指标（Table 7） ============
t7 = doc.tables[7]
add_rows(t7, 3, src=7)
fill_table(
    t7,
    [
        (
            "储备 A、储备 B",
            "池内两种代币的当前余额",
            "枚",
            "初值 100 万/200 万，逐笔交易与 LP 操作更新",
        ),
        ("池内价格", "储备 B 除以储备 A", "枚 B / 枚 A", "由储备比值实时计算"),
        ("外部参照价格", "外部市场 Token A 价格", "枚 B / 枚 A", "初值 2，每小时乘以 (1+N(0,2%))"),
        (
            "单笔滑点",
            "（成交均价 − 池内即时价）/ 池内即时价",
            "%",
            "由恒定乘积公式计算，按交易类型汇总均值",
        ),
        ("累计交易量", "成交交易输入代币量，折算为 A", "枚 A", "逐笔累加"),
        ("累计手续费收入", "按 0.3% 收取并留在池中的代币量，折算为 B", "枚 B", "逐笔累加"),
        (
            "失败笔数与失败率",
            "库存不足或滑点超限的笔数及其占到达笔数的比例",
            "笔 / %",
            "按三类交易分组统计",
        ),
        (
            "无常损失",
            "LP 持仓价值相对持币策略的损失",
            "% 或 枚 B",
            "每小时按外部参照价格结算",
        ),
        (
            "LP 份额与净收益",
            "份额总量；手续费收入减无常损失",
            "% / 枚 B",
            "期末汇总，10 次重复取均值与方差",
        ),
        ("池深", "储备 A、储备 B 规模折算为 A", "枚 A", "随 LP 操作更新，每小时快照"),
    ],
)

# ============ 十一、概念模型假设（Table 8） ============
t8 = doc.tables[8]
add_rows(t8, 1, src=6)
fill_table(
    t8,
    [
        (
            "交易即时成交，服务时长为 0，忽略区块确认延迟、gas 费与失败重试",
            "AMM 按储备比例在区块内结算，案例未给延迟与费用参数",
            "模型不产生等待与排队；失败只来自滑点与库存不足",
        ),
        (
            "交易方向 A→B 与 B→A 各占 50%",
            "案例未给方向参数，取对称设定",
            "若真实成交偏单向，储备比例与滑点会被低估",
        ),
        (
            "用户只按池内价格成交，不进行跨交易所套利",
            "案例限定单一流动性池",
            "池内价格可长期偏离外部价，无常损失与滑点被高估",
        ),
        (
            "外部价格为外生随机游走 N(0,2%)/h，不受池内交易影响",
            "案例给定该外生过程",
            "忽略大额交易对市场价的反馈，价格冲击的影响被低估",
        ),
        (
            "LP 到达与规模独立于池内收益和价格",
            "案例给定指数到达与离散均匀规模",
            "忽略亏损时的集中撤资，池深下降风险被低估",
        ),
        (
            "手续费以输入代币计并全部留在池中，按份额归属 LP",
            "案例规定手续费添加到流动性池中",
            "LP 收益体现为份额净值上升，不体现为现金流",
        ),
        (
            "各随机过程在 168 h 内平稳，参数不随时间变化",
            "案例未给时变结构",
            "无法反映时段性行情，需用多情景实验补充",
        ),
    ],
)

# ============ 十二、与决策问题的对应关系（Table 9） ============
t9 = doc.tables[9]
fill_table(
    t9,
    [
        (
            "基准参数下的总交易量、总手续费收入；手续费能否覆盖 LP 无常损失",
            "交易到达→定价→成交结算；LP 增减储备",
            "累计交易量、累计手续费、无常损失、LP 净收益",
            "基准方案 10 次重复，输出均值与置信区间",
        ),
        (
            "大额交易平均滑点是否超出 5% 容忍度；大额占比升到 20% 时滑点增加多少",
            "交易类型分流、恒定乘积定价、滑点判定",
            "单笔滑点、大额交易占比、失败笔数",
            "把大额占比改为 20%，比较滑点均值与超限比例",
        ),
        (
            "费率从 0.3% 提高到 0.5% 对交易量与 LP 收入的影响",
            "成交结算中的手续费扣取",
            "费率、累计手续费、累计交易量",
            "两档费率各跑 10 次，比较交易量与 LP 净收益",
        ),
        (
            "波动率从 2% 增至 5% 时 LP 无常损失与净收益的变化",
            "外部价格更新与无常损失结算",
            "价格变化率标准差、外部参照价格、无常损失",
            "调整 N(0,σ) 的 σ，比较无常损失与净收益",
        ),
        (
            "波动加剧与大额占比上升时，费率能否稳定 LP 净收益；最优费率组合",
            "上述过程共同作用",
            "费率、σ、大额占比、LP 净收益均值与方差",
            "全因子实验，选取均值高且方差小的方案",
        ),
    ],
)

# ============ 十三、Arena 实现映射（Table 10） ============
t10 = doc.tables[10]
fill_table(
    t10,
    [
        (
            "实体到达",
            "Create（交易、LP 添加、LP 移除）＋ 定时 Create（价格事件）",
            "交易 EXPO(5 min)；LP EXPO(2 h)、EXPO(3 h)；价格每 1 h",
            "价格事件与小时快照是否合并为一条流",
        ),
        (
            "属性赋值/参数计算",
            "Assign",
            "类型、方向、输入量、容忍度；价格变化率用 NORM(0,2)",
            "恒定乘积定价需内嵌 VBA，Arena 表达式能力有限",
        ),
        (
            "逻辑判断/分流",
            "Decide",
            "库存校验、滑点比较、方向与类型分流",
            "须先算滑点再判断，Assign 与 Decide 的先后要固定",
        ),
        (
            "服务/加工",
            "Process（Delay 0）或 Assign",
            "成交结算与 LP 增减在 0 时长内完成",
            "是否保留 Process 以体现活动，或直接用 Assign",
        ),
        (
            "排队/等待",
            "Queue ＋ Seize/Release",
            "不期望出现排队，队列长度作为逻辑校验量",
            "队列长期非空即说明服务时长或顺序设置错误",
        ),
        (
            "资源",
            "Resource（处理通道）＋ Variable（储备、份额）",
            "处理通道容量 1；储备以全局变量表达",
            "Arena 的 Resource 不能表示余额，余额只能用 Variable",
        ),
        (
            "结果记录",
            "Record、Statistic、Output、ReadWrite",
            "成交量、手续费、滑点、失败率、储备与价格时间序列",
            "时间序列用 ReadWrite 逐小时输出",
        ),
        (
            "实体离开",
            "Dispose",
            "成交与放弃两个出口分别计数",
            "共用 Dispose 并用属性区分，或分设两个 Dispose",
        ),
    ],
)

# ============ 十五、AI 辅助使用记录（Table 11） ============
t11 = doc.tables[11]
fill_table(
    t11,
    [
        (
            "概念模型结构化",
            "提供案例材料与第1次课成果，请 AI 按「实体—资源—事件—队列—决策—指标」拆分要素",
            "小组逐项核对案例参数，删除套利、gas、跨池等案例未涉及的内容",
        ),
        (
            "事件与状态变量梳理",
            "请 AI 列出 AMM 交易的状态变化顺序，指出并发事件的排序问题",
            "小组确认储备更新顺序与手续费回流方式，补充同刻事件优先级",
        ),
        (
            "流程图与文档整理",
            "请 AI 生成 Mermaid 流程图初稿，并按模板表格整理文字",
            "小组调整节点与判断顺序，核对图中参数与案例一致",
        ),
    ],
)
drop_rows(t11, 4)

# ============ 十四、模型逻辑自检清单（P55–P62） ============
fill_para(55, "☑ 每一个实体都有明确的进入系统方式和离开系统条件。")
fill_para(
    56,
    "☑ 每一个主要服务活动都有对应资源及服务时间（AMM 结算服务时长为 0，资源为双边储备，见第五、六节）。",
)
fill_para(
    57,
    "☑ 队列形成条件、排队规则和放弃条件明确（本系统不形成等待队列，"
    "放弃条件为库存不足或滑点超限，见第七节）。",
)
fill_para(58, "☑ 主要决策节点的判断条件明确。")
fill_para(59, "☑ 资源数量和容量约束已经考虑（储备余额为软约束，无固定容量上限）。")
fill_para(60, "☑ 核心决策问题均能在概念模型中找到对应。")
fill_para(61, "☑ 已区分「现实系统」与「仿真模型」的合理简化。")
fill_para(62, "☑ 概念模型能够直接指导后续 Arena 模块搭建。")

# ============ 十、概念模型流程图 ============
# 先填后续段落再删除流程图空行，避免前面删段导致索引漂移。
fill_para(
    45,
    "交易流从订单到达、属性赋值、库存校验、定价与滑点判定走到成交或放弃出口；"
    "LP 流按添加/移除分为两支，直接更新池深与份额；外部价格事件每小时更新参照价格并结算无常损失。",
)
fill_para(
    46,
    "与第1次课流程图相比，新增库存校验节点与小时快照，把储备标为资源，并明确同刻事件的优先级。",
)
fill_para(
    47,
    "图中判断节点均为 0 时长，因此不存在队列。若后续 Arena 模型出现非空队列，"
    "即说明服务时长或事件顺序设置有误，可作为逻辑校验点。",
)

# 流程图独占一页：先让标题与说明同页，再放图，避免页尾孤行。
doc.paragraphs[30].add_run().add_break(WD_BREAK.PAGE)
doc.paragraphs[44].paragraph_format.keep_with_next = True
p_img = doc.paragraphs[33]
for r in list(p_img.runs):
    r._element.getparent().remove(r._element)
p_img.paragraph_format.space_before = Cm(0)
p_img.paragraph_format.space_after = Cm(0)
p_img.add_run().add_picture(IMG, width=Cm(11.5))
for i in range(43, 33, -1):
    p = doc.paragraphs[i]
    p._element.getparent().remove(p._element)

doc.save(DST)
export_pdf(DST, PDF)
print("saved:", DST)
print("saved:", PDF)
