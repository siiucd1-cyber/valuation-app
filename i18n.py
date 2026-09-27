# -*- coding: utf-8 -*-
"""中英双语。界面文字以中文为键；英文模式下查 EN 表，查不到则原样显示中文。
长段落用大写英文键（如 MC_EXPLAIN），中英文分别在 ZH / EN 中给出。"""
from __future__ import annotations

import re


FORCE: str | None = None   # 临时固定语言（如 Excel 模板只出中文版）


def is_en() -> bool:
    if FORCE is not None:
        return FORCE == "en"
    try:
        import streamlit as st
        return st.session_state.get("lang") == "English"
    except Exception:  # noqa: BLE001  脱离 Streamlit 运行时（如单元测试）默认中文
        return False


def T(_k, /, **kw) -> str:
    k = "" if _k is None else str(_k)
    out = EN.get(k, ZH.get(k, k)) if is_en() else ZH.get(k, k)
    return out.format(**kw) if kw else out


def TL(seq) -> list[str]:
    return [T(x) for x in seq]


_MSG = [
    (r"东财「(.+)」板块成分，按市值 0\.25–4 倍筛选", r"Eastmoney board “\1” members, filtered to 0.25–4x market cap"),
    (r"不可用，改用默认清单", "Unavailable; fell back to the default list"),
    (r"无默认清单，请手动输入", "No default list; please enter peers manually"),
    (r"板块成分接口暂不可用", "board-member endpoint unavailable"),
    (r"财务报表抓取失败，无法继续", "Failed to fetch financial statements; cannot continue"),
    (r"行情接口未返回该代码的数据", "Quote endpoint returned no data for this code"),
    (r"请输入 6 位 A 股代码，例如 688230", "Please enter a 6-digit A-share code, e.g. 688230"),
    (r"无法识别的股票代码", "Unrecognised stock code"),
    (r"周线样本不足 30 周", "fewer than 30 weekly observations"),
    (r"折现率必须高于永续增长率", "The discount rate must exceed the terminal growth rate"),
    (r"默认清单（Wind 全球可比公司）", "Default list (Wind global comparables)"),
    (r"手动输入", "Manual input"),
    (r"失败：", "Failed: "),
    (r"东方财富", "Eastmoney"), (r"腾讯", "Tencent"), (r"新浪", "Sina"),
    ("（", " ("), ("）", ")"), ("：", ": "), ("，", ", "),
]


def tr_msg(s: str) -> str:
    """翻译数据层返回的状态、来源与报错信息（其中可能夹带动态内容）。"""
    if not is_en() or not s:
        return s
    for a, b in _MSG:
        s = re.sub(a, b, s)
    return s


ZH = {
    "STMT_EDIT_NOTE": ("点击蓝色格子即可直接修改（营收增速、核心经营利润率、投资收益及其他、资本开支 / 营收、折旧摊销 / 营收），"
                       "回车后三张表、折现法、蒙特卡洛与敏感性分析全部重算，改过的格子变成黄底；清空格子即恢复默认。"
                       "历史列来自财报接口，锁定不可修改；如需使用自己核对过的数据，请在左侧选择「上传年报 PDF」。"),
    "STMT_EDIT_NOTE_PDF": ("点击蓝色格子即可直接修改：预测列的蓝色行是假设，历史列的蓝色行是从年报识别出的科目（识别有误时可在此更正）。"
                           "回车后全部重算，改过的格子变成黄底；清空假设格即恢复默认。"),
    "CALC_EDIT_NOTE": ("点击预测年份（E 列）的蓝色格子直接修改，回车后三张表、折现法、蒙特卡洛和敏感性分析即时重算；"
                       "历史列（A 列）为财报实际值，仅供参考。改过的格子显示为黄底。"),
    "HIST_LOCK_NOTE": "历史数据来自财报接口，保持与披露一致，不可修改。若要使用自己核对过的数据，可在左侧选择「上传年报 PDF」，识别结果可以逐项修改。",
    "SHARES_HELP": "年报中识别到的股本会自动使用；未识别到或想用其他股本（如非上市公司的注册资本折算股数）时在此填写。",
    "STMT_NOTE_利润表": ("核心经营利润 = 营业总收入 − 营业总成本；投资收益及其他 = 利润总额 − 核心经营利润（含理财收益、补助等）。"
                        "预测期：营收按增速滚动，核心经营利润 = 营收 × 利润率，所得税 = 利润总额 × 有效税率。"),
    "STMT_NOTE_现金流量表": ("预测期经营活动现金流 = 归母净利润 + 折旧摊销 − 营运资金增加（简化口径）；自由现金流 = 经营活动现金流 − 资本开支；"
                          "分红 = 归母净利润 × 分红率。历史列为财报披露的经营活动现金流与资本开支。"),
    "STMT_NOTE_资产负债表": ("经营视角的资产负债表：营运资本 = 应收账款 + 存货 − 应付账款；净现金 = 货币资金 + 交易性金融资产 − 有息负债；"
                          "其他净资产为倒挤项（长期股权投资、其他资产与负债等），预测期保持基期水平。预测期按滚动关系编制："
                          "固定资产 += 资本开支 − 折旧摊销，净现金 += 归母净利润 + 折旧摊销 − 资本开支 − 营运资金增加 − 分红，"
                          "归母权益 += 归母净利润 − 分红，因此「平衡检查」恒为 0。"),
    "VERDICT_1": ("按当前假设，{name}每股内在价值 {v:.2f} 元，{dir}现价 {px:.2f} 元约 {x:.0%}；"
                  "蒙特卡洛 90% 区间 {p5:.2f}–{p95:.2f} 元，价值高于现价的概率 {pa:.1%}。"),
    "VERDICT_2": "企业价值中 {tv:.0f}% 来自终值；净现金贡献 {nc:.2f} 元/股，占每股价值的 {ncp:.0%}。",
    "VERDICT_3": "估值对「{f}」最敏感：该假设变动 {r}，每股价值在 {lo:.2f}–{hi:.2f} 元之间。",
    "VERDICT_4": ("要让折现法等于现价，折现率需降到 {iw:.2f}%（模型为 {w:.2f}%）。"
                  "判断现价是否合理，关键在于这一隐含回报要求、以及上方「现价隐含了什么」所列的增长和利润率条件是否站得住。"),
    "VERDICT_4N": "在当前经营假设下，任何高于永续增长率的折现率都无法使折现法达到现价。",
    "VERDICT_NOTE": "结论完全由上方假设推出，改动任一假设都会即时更新；仅供学习研究，不构成投资建议。",
    "FCFF_NEG": ("预测期最后一年的自由现金流为负，终值也随之为负，折现法结果没有意义。常见原因是公司处于扩张期："
                 "资本开支 / 营收（当前 {cx:.1f}%）远高于折旧摊销 / 营收（{da:.1f}%），而模型把这个比例延续到了永续期。"
                 "可在左侧「资本开支与营运资金」中把资本开支调到接近折旧的维持性水平后再看。"),
    "MODE_HELP": ("实时数据：输入股票代码，从东方财富、新浪公开接口拉取；演示数据：预存快照，无网络也能打开；"
                  "上传年报 PDF：从年报中自动抽取合并报表，适合接口取不到数据或想用原始披露数据时。"),
    "PDF_UP_HELP": "上传同一家公司的 1–6 份年度报告（沪深交易所标准格式）。多份年报可拼成更长的历史序列。",
    "PRICE_HELP": ("上市公司识别到股票代码后会自动取实时股价，这里填 0 即可；"
                   "非上市公司或想用其他价格时，填入每股价格（如最近一轮融资价格）。"),
    "PDF_INTRO": (
        "在左侧上传一份或多份**年度报告 PDF**，程序会：\n\n"
        "1. 找到「合并资产负债表、合并利润表、合并现金流量表」和「现金流量表补充资料」，按表格结构抽取 25 个科目"
        "（营业总收入、营业总成本、利润总额、所得税、归母净利润、折旧摊销、资本开支、应收账款、存货、借款等），"
        "自动跳过母公司报表；\n"
        "2. 每份年报取本年和上年两期；多份年报拼接时，某一年优先用**次年年报里的上年数**（已按追溯调整重述）；\n"
        "3. 识别到股票代码时，自动获取实时股价、贝塔和国债利率；\n"
        "4. 抽取结果可在页面上逐项核对、修改，折现法、蒙特卡洛、敏感性分析全部按修改后的数据重算；"
        "在「导出 Excel」页签可下载**已填好数据的折现法模板**。\n\n"
        "解析一份年报约 10–20 秒。用金开新能（600821）2016–2021 年 6 份年报测试，"
        "除 2021 年数据此后被追溯调整、旧准则下金融资产科目口径不同外，其余 125 项与东方财富数据逐项一致。"),
    "PDF_MERGE_NOTE": ("每份年报包含本年和上年两期。同一年度优先采用次年年报中的上年数（已按追溯调整重述，与后续年度口径一致），"
                       "没有次年年报时用该年年报的本年数。表中数据可以直接修改，修改后全部估值即时重算。"),
    "TEMPLATE_FILLED_HELP": "把当前公司最近 5 年的数据填入模板的「历史数据」表，假设表填入当前左侧的假设，打开即可看到与网页一致的结果。",
    "TORNADO_NOTE": ("左图每次只动一个假设（其余不变），上下各变动一个标准差或给定幅度，条越长说明估值对它越敏感；"
                     "营收增速、利润率、折现率的变动幅度取上方不确定性参数。右图来自蒙特卡洛：所有不确定因素同时随机变化时，"
                     "用每个输入与每股价值的秩相关系数平方分解估值波动的来源。"),
    "BRIDGE_NOTE": ("左图从当前假设出发，逐步换成更乐观的假设，看每股价值累积到哪里能追上现价；"
                    "右表是只动一个参数、其他全部不变时需要的取值。所需取值越离谱，说明现价隐含的预期越难实现。"),
    "SW_HELP": ("默认 = 贝塔回归标准误 {se:.2f} × 市场风险溢价 {erp:.1f}% ≈ {v:.2f} 个百分点："
                "贝塔是用 100 周数据回归估出来的，本身有误差，这里把它传导到折现率。"),
    "MC_EXPLAIN": (
        "**它不是用来“预测营收”的。** 营收增速和利润率的**中枢**仍是左侧你设定的假设；"
        "蒙特卡洛回答的是另一个问题：**这些假设如果像历史上那样上下波动，估值会落在什么区间？**\n\n"
        "做法：每一次模拟，为未来 5 年逐年随机抽一组（营收增速、核心经营利润率），"
        "波动幅度（标准差）和两者的联动关系（相关系数）取自公司历史；然后把这条路径完整地走一遍"
        "折现法，得到一个每股价值。重复 2 万次，就得到每股价值的分布——P50 是中位数，P5–P95 覆盖 90% 的情形。\n\n"
        "**为什么要用历史数据估参数：** 标准差和相关系数如果凭感觉填，结论就没有依据。"
        "从历史里测出来，至少说明“这家公司过去就是这么波动的”。\n\n"
        "**为什么有“滚动 TTM”这个选项：** 以芯导为例，年报数据从 2018 年开始，只能算出 7 个年度增速，"
        "估标准差太少；用单季数据滚动 4 个季度求 TTM，可以得到 17 个观测。"
        "但相邻两个 TTM 共用 3 个季度，彼此高度相关，**等效独立样本只有约 17 ÷ 4 ≈ 4 个**，"
        "并不比年度数据多出多少信息——这也是相关系数随窗口变号的原因。\n\n"
        "**历史很长的公司：** 年报有十年以上时，直接用年度同比更干净（观测互不重叠），"
        "本工具在年度观测 ≥ 10 个时默认改用年度口径。但太久远的数据可能反映的是另一个商业模式，"
        "可以用下方的窗口滑块只取最近 N 年。\n\n"
        "**折现率和永续增长率也会随机变化：** 贝塔是回归估计值，有标准误；折现率的波动默认取“贝塔标准误 × 市场风险溢价”，"
        "永续增长率默认上下波动 0.5 个百分点。这样模拟结果同时反映经营和折现两方面的不确定性，"
        "再用龙卷风图和贡献分解回答“估值到底对什么最敏感”。"),
    "MC_SRC_HELP": ("单季滚动 TTM：观测多，但相邻观测重叠，适合上市时间短的公司；"
                    "年度同比：观测互不重叠，历史长时更可靠；手动输入：自己给定标准差与相关系数。"),
    "MC_CMP_NOTE": ("两种口径并排对比。滚动 TTM 的相邻观测共享 3 个季度，等效独立样本约为观测数 ÷ 4；"
                    "年度口径观测不重叠。两者结论差异大时，说明参数本身不确定，应以区间而非单点看待模拟结果。"),
    "DUPONT_NOTE": ("净资产收益率 = 归母净利率 × 资产周转率 × 权益乘数（均用期初期末平均值）。"
                    "经营性ROE = 扣非归母净利润 ÷（平均归母权益 − 平均货币资金与交易性金融资产），"
                    "用于剔除闲置资金对回报率的稀释。"),
    "FCFF_NOTE": ("NOPAT =（核心经营利润 + 投资收益及其他 × 计入比例）×（1 − 税率）；"
                  "FCFF = NOPAT + 折旧摊销 − 资本开支 − 营运资金增加；年末折现。"),
    "IW_HELP": ("反向折现：其他假设不变，求使折现法每股价值恰好等于现价的折现率。"
                "它比模型折现率低得越多，说明市场定价隐含的风险越低或长期增长越高。"),
    "TEMPLATE_NOTE": ("不依赖网页的折现法模板：「历史数据」表放 5 年报表科目，历史指标和参考假设自动算出；"
                      "「假设」表填写假设后，折现法与敏感性自动计算。左边按钮下载已填好当前公司数据与假设的版本，右边是空白版。"),
    "METHOD_NOTES": (
        "- **数据**：三张报表、单季利润表、股价、沪深300、10年期国债来自 akshare（东方财富、新浪公开接口）；"
        "实时行情与可比公司来自东方财富行情接口。非官方授权数据，接口可能随网站改版失效。\n"
        "- **核心经营利润** =（营业总收入 − 营业总成本），营业总成本已含四项费用；"
        "**投资收益及其他** = 利润总额 − 核心经营利润。\n"
        "- **贝塔**：最近 100 周个股与沪深300 周收益率回归。\n"
        "- **蒙特卡洛**：均值取用户假设；标准差与相关系数可选单季滚动 TTM、年度同比或手动输入。\n"
        "- 本工具为个人学习项目，所有结论基于用户假设，不构成投资建议。"),
}

EN = {
    # ── 页面与侧边栏
    "估值工作台": "Valuation Workbench",
    "输入 A 股代码，自动拉取财报；左侧所有假设可调，结果即时重算。":
        "Enter an A-share code to pull financials automatically. Every assumption on the left is adjustable and results update instantly.",
    "数据来源": "Data source",
    "实时数据": "Live",
    "演示数据（离线）": "Demo (offline)",
    "演示数据是预存的快照，无网络也能打开；实时数据从东方财富、新浪公开接口获取。":
        "Demo data is a saved snapshot that works offline; live data comes from Eastmoney and Sina public endpoints.",
    "股票代码": "Stock code",
    "加载": "Load",
    "可用演示代码：": "Demo codes available: ",
    "正在从东方财富、新浪拉取数据（首次约 30–60 秒，之后一小时内有缓存）……":
        "Fetching data from Eastmoney and Sina (about 30–60 s the first time, cached for an hour afterwards)…",
    "实时数据获取失败，已改用演示快照。原因：{e}": "Live data failed; using the demo snapshot instead. Reason: {e}",
    "数据获取失败：{e}": "Data fetch failed: {e}",
    "恢复数据默认值": "Reset to data-driven defaults",
    "收入与利润": "Revenue & profit",
    "第1年营收增速（%）": "Year-1 revenue growth (%)",
    "第5年营收增速（%）": "Year-5 revenue growth (%)",
    "第1年核心经营利润率（%）": "Year-1 core operating margin (%)",
    "第5年核心经营利润率（%）": "Year-5 core operating margin (%)",
    "第1年投资收益及其他（万元）": "Year-1 investment income & other (RMB 10k)",
    "投资收益及其他年变化（%）": "Annual change in investment income & other (%)",
    "其中计入经营现金流的比例（%）": "Share counted in operating cash flow (%)",
    "有效税率（%）": "Effective tax rate (%)",
    "资本开支与营运资金": "Capex & working capital",
    "折旧摊销 / 营收（%）": "D&A / revenue (%)",
    "资本开支 / 营收（%）": "Capex / revenue (%)",
    "营运资金增加 / 营收增量（%）": "Increase in working capital / revenue increase (%)",
    "折现率": "Discount rate",
    "无风险利率（%）": "Risk-free rate (%)",
    "贝塔": "Beta",
    "市场风险溢价（%）": "Equity risk premium (%)",
    "规模溢价（%）": "Size premium (%)",
    "税前债务成本（%）": "Pre-tax cost of debt (%)",
    "永续增长率（%）": "Terminal growth rate (%)",
    "货币资金计入净现金": "Include cash in net cash",
    "交易性金融资产计入净现金": "Include trading financial assets in net cash",
    "市盈率法": "P/E method",
    "目标市盈率（倍）": "Target P/E (x)",
    "默认值：{v}%，取最新一期累计营收同比或滚动 TTM 增速":
        "Default: {v}%, from the latest year-to-date revenue growth or rolling TTM growth",
    "中间年份按线性插值": "Years in between are linearly interpolated",
    "默认值：{v}%，取最新滚动 TTM；定义为（营业总收入−营业总成本）÷ 营业总收入":
        "Default: {v}%, latest rolling TTM; defined as (total revenue − total operating cost) ÷ total revenue",
    "= 利润总额 − 核心经营利润，含理财收益、政府补助、公允价值变动等":
        "= pre-tax profit − core operating profit; includes wealth-management income, subsidies, fair-value changes, etc.",
    "默认 0：折现法只对核心主业定价，金融资产在净现金中加回。若补助、退税属经常性，可调高":
        "Default 0: the DCF values the core business only; financial assets are added back via net cash. Raise it if subsidies or tax rebates are recurring.",
    "默认取近三年中位数与折旧率的较大者，即长期至少覆盖折旧":
        "Default: the larger of the 3-year median and the D&A ratio, so capex at least covers depreciation",
    "默认取最新 10 年期国债收益率": "Default: latest 10-year China government bond yield",
    "默认由最近 100 周个股与沪深300周收益率回归计算":
        "Default: regression of 100 weekly returns against the CSI 300",
    "默认取可比公司市盈率(TTM)中位数：{v} 倍": "Default: median TTM P/E of comparables: {v}x",

    # ── 页眉与标签页
    "数据时间": "Data as of",
    "演示快照": "Demo snapshot",
    "实时": "Live",
    "半导体": "Semiconductors",
    "电子": "Electronics",
    "首页": "Dashboard",
    "历史财务": "Financial history",
    "盈利预测与折现法": "Forecast & DCF",
    "蒙特卡洛模拟": "Monte Carlo",
    "导出 Excel": "Export Excel",

    # ── 首页
    "行情获取时间：{t}（每 30 秒可刷新）": "Quote fetched at {t} (refreshable every 30 s)",
    "实时行情刷新失败，显示加载时的报价": "Live quote refresh failed; showing the quote from load time",
    "演示快照，行情截至 {t}": "Demo snapshot; prices as of {t}",
    "刷新行情": "Refresh quote",
    "{p:+.1%} vs 现价": "{p:+.1%} vs price",
    "现价（元）": "Price (RMB)",
    "总市值（亿元）": "Market cap (RMB 100m)",
    "折现法（元/股）": "DCF (RMB/share)",
    "市盈率法（元/股）": "P/E method (RMB/share)",
    "蒙特卡洛中位数（元/股）": "MC median (RMB/share)",
    "收盘价": "Close",
    "折现法": "DCF",
    "蒙特卡洛 P5–P95": "Monte Carlo P5–P95",
    "近一年股价与估值": "Share price over the past year vs valuation",
    "元/股": "RMB/share",
    "关键指标": "Key metrics",
    "指标": "Metric",
    "数值": "Value",
    "市盈率 TTM": "P/E (TTM)",
    "可比公司市盈率中位数": "Peer median P/E (TTM)",
    "市净率": "P/B",
    "52周区间（元）": "52-week range (RMB)",
    "贝塔（100周）": "Beta (100 weeks)",
    "10年国债": "10-year CGB yield",
    "折现率 WACC": "WACC",
    "永续增长率": "Terminal growth",
    "终值占企业价值": "Terminal value / EV",
    "每股净现金（元）": "Net cash per share (RMB)",
    "目标市盈率": "Target P/E",
    "52周股价区间": "52-week price range",
    "折现法敏感性区间": "DCF sensitivity range",
    "市盈率法（目标倍数±20%）": "P/E method (target multiple ±20%)",
    "估值区间汇总（元/股）": "Valuation summary (RMB/share)",
    "现价 {p:.2f}": "Price {p:.2f}",
    "营业总收入（亿元）": "Total revenue (RMB 100m)",
    "归母净利润（亿元）": "Net profit to parent (RMB 100m)",
    "营收与利润：历史与预测（亿元）": "Revenue & profit: history and forecast (RMB 100m)",
    "结果说明": "Summary",
    "- **折现法**：折现率 {w:.2f}%（股权成本 {ke:.2f}%，贝塔 {b:.2f}），永续增长率 {g:.2f}%，得到每股 {v:.2f} 元；终值占企业价值 {tv:.1f}%。其中净现金贡献 {nc:.2f} 元/股，占每股价值的 {ncp:.0%}。\n- **现价隐含折现率**：要让折现法结果等于现价 {px:.2f} 元，折现率需为 {iw}，模型用的是 {w:.2f}%。\n- **蒙特卡洛**：{n:,} 次模拟（参数来源：{src}），折现法每股价值中位数 {p50:.2f} 元，90% 的结果落在 {p5:.2f}–{p95:.2f} 元。":
        ("- **DCF**: WACC {w:.2f}% (cost of equity {ke:.2f}%, beta {b:.2f}), terminal growth {g:.2f}%, giving "
         "RMB {v:.2f} per share; terminal value is {tv:.1f}% of EV. Net cash contributes RMB {nc:.2f} per share, "
         "{ncp:.0%} of the value.\n"
         "- **Implied discount rate**: for the DCF to equal the current price of RMB {px:.2f}, the discount rate "
         "would need to be {iw}; the model uses {w:.2f}%.\n"
         "- **Monte Carlo**: {n:,} simulations (parameters: {src}); median DCF value RMB {p50:.2f} per share, with 90% "
         "of outcomes between RMB {p5:.2f} and {p95:.2f}."),
    "现价隐含折现率": "Implied discount rate",
    "模型折现率 {w:.2f}%": "Model WACC {w:.2f}%",
    "IW_HELP": ("Reverse DCF: keep every other assumption unchanged and solve for the discount rate at which the DCF "
                "value per share equals the current price. The further it is below the model WACC, the more the market "
                "is pricing in lower risk or higher long-term growth."),
    "：原始值 {raw:.2f}（R² {r2:.2f}），Blume 调整后 {adj:.2f}（= 0.67 × 原始 + 0.33）":
        ": raw {raw:.2f} (R² {r2:.2f}); Blume-adjusted {adj:.2f} (= 0.67 × raw + 0.33)",
    "折现率 {w:.2f}% 与永续增长率 {g:.2f}% 只差 {d:.2f} 个百分点，终值被大幅放大，折现法结果不可靠。":
        "WACC {w:.2f}% is only {d:.2f} pp above terminal growth {g:.2f}%, which inflates the terminal value; the DCF result is not reliable.",
    "贝塔回归的 R² 仅 {r2:.2f}，个股与大盘几乎不相关，回归贝塔 {b:.2f} 统计上不可靠。可在左侧「折现率」中改用 Blume 调整后贝塔 {adj:.2f} 或行业贝塔。":
        "The beta regression has an R² of only {r2:.2f}: the stock barely moves with the market, so the regression beta of {b:.2f} is statistically unreliable. Consider the Blume-adjusted beta {adj:.2f} or an industry beta under “Discount rate” on the left.",
    "终值占企业价值 {v:.0f}%，估值高度依赖永续假设，结果稳健性有限。":
        "Terminal value is {v:.0f}% of EV, so the valuation depends heavily on the perpetuity assumption.",
    "所有结果基于左侧假设，调整任一参数即时重算。数据来自东方财富、新浪公开接口，仅供学习研究，不构成投资建议。":
        "All results follow from the assumptions on the left and update instantly. Data comes from Eastmoney and Sina public endpoints; for study purposes only, not investment advice.",
    "数据获取状态": "Data fetch status",
    "数据项": "Item",
    "状态": "Status",
    "实时行情": "Live quote",
    "三张报表": "Financial statements",
    "个股行情": "Price history",
    "沪深300": "CSI 300",
    "所属板块": "Sector boards",
    "板块成分": "Board members",
    "可比公司": "Comparables",

    # ── 历史财务
    "主要财务数据（万元 / %）": "Key financials (RMB 10k / %)",
    "营业总收入": "Total revenue",
    "营收增速%": "Revenue growth %",
    "毛利率%": "Gross margin %",
    "核心经营利润": "Core operating profit",
    "核心经营利润率%": "Core operating margin %",
    "投资收益及其他": "Investment income & other",
    "利润总额": "Pre-tax profit",
    "有效税率%": "Effective tax rate %",
    "归母净利润": "Net profit to parent",
    "扣非归母净利润": "Recurring net profit to parent",
    "非经常性损益": "Non-recurring items",
    "研发费用率%": "R&D / revenue %",
    "研发费用": "R&D expense",
    "经营现金流": "Operating cash flow",
    "货币资金": "Cash",
    "交易性金融资产": "Trading financial assets",
    "有息负债": "Interest-bearing debt",
    "金融资产占总资产%": "Financial assets / total assets %",
    "营业总成本": "Total operating cost",
    "资本开支": "Capex",
    "折旧摊销": "D&A",
    "资产总计": "Total assets",
    "归母权益": "Parent equity",
    "模型结构回归检验": "Model structure check (back-test)",
    "{y} 年：营业总收入 {rev} × 核心经营利润率 {m:.2f}% = 核心经营利润 {core}<br>核心经营利润 + 投资收益及其他 {oth} = 利润总额 {pt}<br>利润总额 × (1 − 有效税率 {tax:.2f}%) × (1 − 少数股东 {mi:.2f}%) = 归母净利润 {np_}<br>披露值 {dis}，偏差 <b>{dev:+.2f} 万元</b>":
        "FY{y}: total revenue {rev} × core operating margin {m:.2f}% = core operating profit {core}<br>core operating profit + investment income & other {oth} = pre-tax profit {pt}<br>pre-tax profit × (1 − tax {tax:.2f}%) × (1 − minority {mi:.2f}%) = net profit to parent {np_}<br>reported {dis}, difference <b>{dev:+.2f} (RMB 10k)</b>",
    "预测模型沿用同一结构，保证与披露科目一一对应、不设轧差项。":
        "The forecast uses the same structure, so every line maps to a reported item with no plug.",
    "营业总收入与增速": "Total revenue and growth",
    "同比（%，右轴）": "YoY (%, right axis)",
    "利润率（%）": "Margins (%)",
    "毛利率": "Gross margin",
    "核心经营利润率": "Core operating margin",
    "归母净利润构成（亿元）": "Net profit to parent breakdown (RMB 100m)",
    "资产结构（亿元）": "Asset mix (RMB 100m)",
    "其他资产": "Other assets",
    "杜邦拆解": "DuPont analysis",
    "DUPONT_NOTE": ("ROE = net margin × asset turnover × equity multiplier (using average opening and closing balances). "
                    "Operating ROE = recurring net profit to parent ÷ (average parent equity − average cash and trading "
                    "financial assets), which strips out the dilution from idle cash."),
    "净资产收益率%": "ROE %",
    "归母净利率%": "Net margin %",
    "资产周转率(次)": "Asset turnover (x)",
    "权益乘数": "Equity multiplier",
    "剔除金融资产后的经营性ROE%": "Operating ROE excl. financial assets %",

    # ── 折现法
    "折现率 \\ 永续增长率": "WACC \\ terminal growth",
    "项目": "Item",
    "无风险利率": "Risk-free rate",
    "市场风险溢价": "Equity risk premium",
    "规模溢价": "Size premium",
    "股权成本": "Cost of equity",
    "税后债务成本": "After-tax cost of debt",
    "债务权重": "Debt weight",
    "10年期国债": "10-year CGB",
    "100周回归": "100-week regression",
    "手动": "Manual",
    "Rf + β×ERP + 规模溢价": "Rf + β×ERP + size premium",
    "Kd × (1 − 税率)": "Kd × (1 − tax rate)",
    "有息负债 ÷（有息负债 + 市值）": "Debt ÷ (debt + market cap)",
    "估值桥": "Valuation bridge",
    "预测期现值合计　{pv}<br>终值 = {f} × (1 + {g:.2f}%) ÷ ({w:.2f}% − {g:.2f}%) = {tv}<br>终值现值 = {tv} × {df:.4f} = {tpv}<br>企业价值 = {ev}　（终值占比 {tvp:.1f}%）<br>＋ 货币资金 {cash}　＋ 交易性金融资产 {fin}　− 有息负债 {debt}<br>股权价值 = {eq}　÷ 总股本 {sh} 万股<br><b>每股价值 = {ps:.2f} 元</b>":
        "PV of forecast FCFF  {pv}<br>Terminal value = {f} × (1 + {g:.2f}%) ÷ ({w:.2f}% − {g:.2f}%) = {tv}<br>PV of terminal value = {tv} × {df:.4f} = {tpv}<br>Enterprise value = {ev}  (terminal share {tvp:.1f}%)<br>+ cash {cash}  + trading financial assets {fin}  − debt {debt}<br>Equity value = {eq}  ÷ shares {sh} (10k)<br><b>Value per share = RMB {ps:.2f}</b>",
    "金额单位：万元；净现金取 {d} 资产负债表": "Amounts in RMB 10k; net cash from the {d} balance sheet",
    "盈利预测与自由现金流（万元）": "Forecast and free cash flow (RMB 10k)",
    "NOPAT": "NOPAT", "FCFF": "FCFF",
    "营运资金增加": "Increase in working capital",
    "折现因子": "Discount factor",
    "现值": "Present value",
    "FCFF_NOTE": ("NOPAT = (core operating profit + investment income & other × share counted) × (1 − tax); "
                  "FCFF = NOPAT + D&A − capex − increase in working capital; year-end discounting."),
    "敏感性：每股价值（元）": "Sensitivity: value per share (RMB)",

    # ── 市盈率法
    "来源：{s}。勾选「纳入」决定是否参与统计；市盈率(TTM) 不在 0–200 倍区间的样本自动剔除。":
        "Source: {s}. Tick “Include” to use a company in the statistics; TTM P/E outside 0–200x is excluded automatically.",
    "可比公司代码（逗号分隔，可增删后点刷新）": "Peer codes (comma-separated; edit and click refresh)",
    "刷新可比公司": "Refresh peers",
    "获取失败：{e}": "Fetch failed: {e}",
    "纳入": "Include",
    "代码": "Code",
    "名称": "Name",
    "股价": "Price",
    "市盈率(TTM)": "P/E (TTM)",
    "市盈率(动)": "P/E (fwd, annualised)",
    "总市值(亿元)": "Market cap (RMB 100m)",
    "市盈率(TTM) 中位数": "Median P/E (TTM)",
    "平均数": "Mean",
    "有效样本": "Valid sample",
    "{v:.1f} 倍": "{v:.1f}x",
    "{n} 家": "{n}",
    "剔除 {n} 家": "{n} excluded",
    "本公司市盈率 TTM {pe:.1f} 倍，较可比中位数 {d:+.0%}。目标市盈率在左侧「市盈率法」中设置，默认取中位数。":
        "This company trades at {pe:.1f}x TTM, {d:+.0%} vs the peer median. Set the target P/E under “P/E method” on the left; it defaults to the median.",
    "暂无可比公司数据，请在左侧手动设定目标市盈率。": "No comparable data; please set a target P/E on the left.",
    "测算": "Calculation",
    "{y}年预测归母净利润　{np_} 万元<br>÷ 总股本 {sh} 万股 = 每股收益 {eps:.4f} 元<br>× 目标市盈率 {pe:.1f} 倍 = <b>每股价值 {v:.2f} 元</b>":
        "{y}E net profit to parent  {np_} (RMB 10k)<br>÷ shares {sh} (10k) = EPS RMB {eps:.4f}<br>× target P/E {pe:.1f}x = <b>value per share RMB {v:.2f}</b>",
    "给予市盈率（倍）": "P/E applied (x)",
    "对应市值（亿元）": "Implied market cap (RMB 100m)",
    "对应每股（元）": "Implied value per share (RMB)",
    "较现价": "vs price",

    # ── 蒙特卡洛
    "蒙特卡洛在做什么？": "What does the Monte Carlo do?",
    "MC_EXPLAIN": (
        "**It does not forecast revenue.** The central path for revenue growth and margin is still the assumptions "
        "you set on the left. The simulation answers a different question: **if those assumptions move around the way "
        "they have historically, where does the valuation land?**\n\n"
        "Each run draws a revenue growth rate and a core operating margin for each of the next five years. The size of "
        "the swings (standard deviation) and how the two move together (correlation) come from the company's history. "
        "The whole path is then run through the DCF to get one value per share. After 20,000 runs you have a "
        "distribution: P50 is the median and P5–P95 covers 90% of outcomes.\n\n"
        "**Why estimate the parameters from history:** a standard deviation or correlation typed in by feel has no "
        "basis. Measuring them at least says “this is how the company has actually behaved”.\n\n"
        "**Why offer rolling TTM:** take Shanghai Prisemi (688230): its annual data starts in 2018, giving only seven annual "
        "growth rates, too few to estimate a standard deviation. Rolling four quarters of single-quarter data gives 17 "
        "TTM observations. But neighbouring TTM values share three quarters and are highly correlated, so the "
        "**effective independent sample is only about 17 ÷ 4 ≈ 4**. It adds less information than it seems, which is "
        "also why the correlation flips sign as the window changes.\n\n"
        "**Companies with long histories:** with ten or more years of annual reports, annual YoY data is cleaner "
        "(observations do not overlap), and this tool defaults to it when there are at least 10 annual observations. "
        "Very old data may reflect a different business, so use the window slider below to keep only the last N years.\n\n"
        "**The discount rate and terminal growth are random too:** beta is a regression estimate with a standard error, so "
        "the discount-rate volatility defaults to “beta standard error × equity risk premium”, and terminal growth varies by "
        "0.5 pp. The simulation therefore reflects both operating and discount-rate uncertainty, and the tornado chart and "
        "contribution breakdown answer “what is the valuation most sensitive to?”"),
    "分布参数": "Distribution parameters",
    "单季滚动 TTM": "Rolling TTM (quarterly)",
    "年度同比": "Annual YoY",
    "手动输入": "Manual input",
    "参数来源": "Parameter source",
    "MC_SRC_HELP": ("Rolling TTM: more observations, but neighbours overlap; suits recently listed companies. "
                    "Annual YoY: non-overlapping observations; more reliable with a long history. "
                    "Manual: enter the standard deviations and correlation yourself."),
    "模拟次数": "Simulations",
    "口径": "Method",
    "观测数": "Observations",
    "区间": "Period",
    "增速σ": "Growth σ",
    "利润率σ": "Margin σ",
    "相关系数": "Correlation",
    "等效独立样本": "Effective independent obs.",
    "MC_CMP_NOTE": ("The two methods side by side. Neighbouring rolling-TTM observations share three quarters, so the "
                    "effective independent sample is roughly the count ÷ 4; annual observations do not overlap. If the "
                    "two disagree a lot, the parameters themselves are uncertain and the simulation should be read as a "
                    "range, not a point."),
    "营收增速标准差（pp）": "Revenue growth σ (pp)",
    "核心经营利润率标准差（pp）": "Core margin σ (pp)",
    "使用最近 N 个观测": "Use the most recent N observations",
    "相关系数对样本窗口敏感，可拖动观察变化": "The correlation is sensitive to the window; drag to see how it changes",
    "{n} 个": "{n}",
    "营收增速标准差": "Revenue growth σ",
    "核心经营利润率标准差": "Core margin σ",
    "两者相关系数": "Correlation",
    "最近观测数": "Last N obs.",
    "相关系数随样本窗口的变化（稳健性检查）": "Correlation by sample window (robustness check)",
    "若相关系数随窗口大幅变化甚至变号，说明两者关系不稳定，解读模拟结果时应更谨慎。":
        "If the correlation swings or flips sign across windows, the relationship is unstable and the simulation should be read with caution.",
    "营收同比": "Revenue YoY",
    "营收同比增速（%）": "Revenue YoY growth (%)",
    "观测": "Observation",
    "营收增速与核心经营利润率": "Revenue growth vs core operating margin",
    "营收同比（%）": "Revenue YoY (%)",
    "核心经营利润率（%）": "Core operating margin (%)",
    "模拟设定": "Simulation setup",
    "每年独立抽取营收增速与核心经营利润率的冲击，二者相关系数取上方参数。均值取左侧假设，标准差取上方参数；第1年已披露 {nq} 个季度，增速波动按剩余 {rest:.0%} 缩小；远期波动逐年放大。各年增速σ：{sg}；利润率σ：{sm}（单位：个百分点）。":
        "Each year draws independent shocks to revenue growth and core margin, correlated as above. Means follow the assumptions on the left and standard deviations follow the parameters above. {nq} quarter(s) of year 1 are already reported, so year-1 growth volatility is scaled to the remaining {rest:.0%}; volatility widens in later years. Growth σ by year: {sg}; margin σ: {sm} (percentage points).",
    "{y}年实际": "FY{y} actual",
    "{y}年归母净利润分布（亿元）": "{y}E net profit to parent distribution (RMB 100m)",
    "折现法每股价值分布（元）": "DCF value per share distribution (RMB)",
    "{y}年归母净利润（万元）": "{y}E net profit to parent (RMB 10k)",
    "折现法每股价值（元）": "DCF value per share (RMB)",
    "{y1}年归母净利润低于{y0}年实际值的概率：{a:.1%}；每股价值高于现价的概率：{b:.1%}。":
        "Probability that {y1}E net profit falls below FY{y0}: {a:.1%}; probability that value per share exceeds the current price: {b:.1%}.",

    # ── 导出
    "导出估值模型": "Export the valuation model",
    "Excel 中的预测、折现法、敏感性均为**活公式**：蓝色为输入，改动「假设」表任一蓝色单元格，全部结果自动重算。蒙特卡洛结果以数值形式附上。当前语言决定 Excel 的语言。":
        "The forecast, DCF and sensitivity sheets in Excel are **live formulas**: blue cells are inputs, and changing any blue cell on the Assumptions sheet recalculates everything. Monte Carlo results are included as values. The Excel file uses the current language.",
    "下载 Excel 估值模型": "Download the Excel model",
    "空白 Excel 模板": "Blank Excel template",
    "下载空白折现法模板（中文）": "Download the blank DCF template (Chinese)",
    "TEMPLATE_NOTE": ("A stand-alone DCF template: the History sheet holds five years of statement items, from which historical "
                      "ratios and reference assumptions are calculated; fill in the Assumptions sheet and the DCF and sensitivity "
                      "update. The left button gives a version pre-filled with this company and the current assumptions; the right "
                      "one is blank."),
    "{n}_{c}_估值模型.xlsx": "{c}_valuation_model.xlsx",
    "方法与数据说明": "Method and data notes",
    "METHOD_NOTES": (
        "- **Data**: financial statements, quarterly income statements, share prices, CSI 300 and 10-year CGB yields come "
        "from akshare (Eastmoney and Sina public endpoints); live quotes and comparables come from the Eastmoney quote "
        "endpoint. The data is not officially licensed and endpoints may break when the sites change.\n"
        "- **Core operating profit** = total revenue − total operating cost (which already includes the four expense "
        "lines); **investment income & other** = pre-tax profit − core operating profit.\n"
        "- **Beta**: regression of the last 100 weekly returns against the CSI 300.\n"
        "- **Monte Carlo**: means follow your assumptions; standard deviations and correlation come from rolling TTM, "
        "annual YoY or manual input.\n"
        "- A personal study project. All conclusions depend on user assumptions and are not investment advice."),

    # ── 敏感性分析（新增）
    "敏感性分析": "Sensitivity",
    "分位数": "Percentile", "每股价值（元）": "Value per share (RMB)",
    "不确定性参数": "Uncertainty parameters",
    "经营变量的参数来源": "Source for operating parameters",
    "营收增速σ": "Revenue growth σ",
    "核心经营利润率σ": "Core margin σ",
    "两者相关系数 {r:+.3f}": "Correlation {r:+.3f}",
    "折现率σ（pp）": "WACC σ (pp)",
    "永续增长率σ（pp）": "Terminal growth σ (pp)",
    "永续增长率的不确定性，默认 0.5 个百分点": "Uncertainty in terminal growth; default 0.5 pp",
    "SW_HELP": ("Default = beta standard error {se:.2f} × equity risk premium {erp:.1f}% ≈ {v:.2f} pp: beta is estimated from "
                "100 weeks of data and carries estimation error, which is passed through to the discount rate."),
    "模拟结果：每股价值的分布": "Simulation result: distribution of value per share",
    "每股价值高于现价的概率：{b:.1%}；{y1}年归母净利润低于{y0}年实际值的概率：{a:.1%}。":
        "Probability that value per share exceeds the price: {b:.1%}; probability that {y1}E net profit falls below FY{y0}: {a:.1%}.",
    "每次模拟同时随机抽取：未来5年的营收增速与核心经营利润率（按上方相关系数联动），以及折现率、永续增长率。均值取左侧假设；第1年已披露 {nq} 个季度，增速波动按剩余 {rest:.0%} 缩小；远期波动逐年放大。":
        "Each run draws five years of revenue growth and core margin (linked by the correlation above) plus the discount rate and terminal growth. Means follow the assumptions on the left; {nq} quarter(s) of year 1 are reported, so year-1 growth volatility is scaled to the remaining {rest:.0%}; volatility widens in later years.",
    "哪些假设最影响估值": "Which assumptions matter most",
    "单因素敏感性（元/股）": "One-at-a-time sensitivity (RMB/share)",
    "不利方向": "Adverse", "有利方向": "Favourable",
    "基准 {v:.2f}": "Base {v:.2f}",
    "蒙特卡洛：估值波动来自哪里": "Monte Carlo: where the variance comes from",
    "TORNADO_NOTE": ("Left: each bar moves one assumption at a time (others fixed) by one standard deviation or the stated amount; "
                     "longer bars mean higher sensitivity. Growth, margin and WACC shifts use the uncertainty parameters above. "
                     "Right: from the Monte Carlo, with all uncertain inputs moving together, the squared rank correlation of "
                     "each input with value per share splits the valuation variance by source."),
    "折现率 × 永续增长率：每股价值（元）": "WACC × terminal growth: value per share (RMB)",
    "参数估计细节：历史观测与稳健性检查": "Parameter estimation details: history and robustness",
    "相关系数随样本窗口的变化": "Correlation by sample window",
    "各年增速σ：{sg}；利润率σ：{sm}（单位：个百分点）。": "Growth σ by year: {sg}; margin σ: {sm} (percentage points).",
    "折现率 × 永续增长率的敏感性表、龙卷风图和蒙特卡洛模拟见「敏感性分析」页签。":
        "The WACC × terminal growth table, tornado chart and Monte Carlo are on the Sensitivity tab.",
    "营收增速": "Revenue growth", "核心经营利润率": "Core operating margin", "永续增长率": "Terminal growth",
    "营收增速（各年）": "Revenue growth (all years)", "核心经营利润率（各年）": "Core margin (all years)",
    "资本开支 / 营收": "Capex / revenue", "营运资本 / 营收": "Working capital / revenue", "有效税率": "Effective tax rate",
    # ── 首页新增
    "估值的不确定性（蒙特卡洛 {n:,} 次）": "Valuation uncertainty (Monte Carlo, {n:,} runs)",
    "现价 {p:.2f}（高于现价概率 {b:.1%}）": "Price {p:.2f} (P(value > price) {b:.1%})",
    "90% 的模拟结果落在 {p5:.2f}–{p95:.2f} 元，高于现价的概率 {b:.1%}。估值波动的 {s:.0f}% 来自{f}（蒙特卡洛秩相关分解，详见「敏感性分析」页签）。":
        "90% of simulated values fall between RMB {p5:.2f} and {p95:.2f}; the probability of exceeding the price is {b:.1%}. {s:.0f}% of the valuation variance comes from {f} (rank-correlation decomposition; see the Sensitivity tab).",
    "现价隐含了什么": "What the price implies",
    "逐步放宽假设后的每股价值（累积）": "Value per share as assumptions are relaxed step by step (cumulative)",
    "当前假设": "Current assumptions",
    "贝塔调为 1.0（市场平均风险）": "Beta to 1.0 (market-average risk)",
    "去掉规模溢价": "Remove size premium",
    "投资收益全部计入现金流、不再下降": "Count all investment income as cash flow, no decline",
    "第5年营收增速 +10pp": "Year-5 revenue growth +10 pp",
    "第5年核心经营利润率 +5pp": "Year-5 core margin +5 pp",
    "永续增长率 +1pp": "Terminal growth +1 pp",
    "只调一个参数时，要达到现价需要：": "Changing one parameter only, reaching the price requires:",
    "参数": "Parameter", "当前": "Current", "达到现价所需": "Needed to reach price", "无解": "No solution",
    "无解（任何折现率都达不到）": "no solution (no discount rate reaches it)",
    "折现率（%）": "WACC (%)",
    "各年营收增速同时增加（pp）": "Add to revenue growth in every year (pp)",
    "各年核心经营利润率同时增加（pp）": "Add to core margin in every year (pp)",
    "BRIDGE_NOTE": ("Left: starting from the current assumptions and switching step by step to more optimistic ones, where "
                    "does value per share catch up with the price? Right: the value one parameter would need, all else "
                    "unchanged. The more extreme the required value, the harder the price's implied expectations are to meet."),
    # ── PDF 上传
    "上传年报 PDF": "Upload annual report PDF",
    "MODE_HELP": ("Live: enter a stock code and pull data from Eastmoney and Sina public endpoints. Demo: a saved snapshot "
                  "that works offline. Upload annual report PDF: extract the consolidated statements from annual reports, "
                  "useful when the endpoints fail or you want the original disclosures."),
    "上传年度报告 PDF（可多份）": "Upload annual report PDFs (several allowed)",
    "PDF_UP_HELP": "Upload 1–6 annual reports of the same company (standard SSE/SZSE format). Several reports give a longer history.",
    "识别到股票代码时，获取实时股价与贝塔": "Fetch live price and beta when a stock code is found",
    "每股价格（元，0 = 自动）": "Price per share (RMB, 0 = automatic)",
    "PRICE_HELP": ("For listed companies the live price is fetched once the stock code is recognised, so leave 0. For unlisted "
                   "companies or a different price, enter a price per share (e.g. the latest funding round)."),
    "上传年报 PDF，自动抽取报表并估值": "Upload annual reports: automatic extraction and valuation",
    "PDF_INTRO": (
        "Upload one or more **annual report PDFs** on the left. The tool will:\n\n"
        "1. Locate the consolidated balance sheet, income statement, cash flow statement and the cash-flow supplementary "
        "note, and extract 25 line items by table structure (revenue, operating cost, pre-tax profit, tax, net profit, "
        "D&A, capex, receivables, inventory, borrowings, etc.), skipping the parent-company statements;\n"
        "2. Take the current and prior year from each report; when combining reports, a year's figures come preferably "
        "from the **following year's report** (restated for retrospective adjustments);\n"
        "3. Fetch the live price, beta and bond yield when a stock code is recognised;\n"
        "4. Let you check and edit every extracted figure; DCF, Monte Carlo and sensitivity all recalculate on the edited "
        "data, and the Export tab offers a **pre-filled DCF Excel template**.\n\n"
        "Parsing takes about 10–20 s per report. Tested on six annual reports (2016–2021) of Gold Kai New Energy (600821): "
        "apart from 2021 figures later restated and a legacy financial-asset line item, all 125 figures match Eastmoney exactly."),
    "正在解析 {n}（{i}/{k}）……": "Parsing {n} ({i}/{k})…",
    "以下文件未识别为年度报告，已跳过：{f}": "These files were not recognised as annual reports and were skipped: {f}",
    "没有可用的年度报告。": "No usable annual report.",
    "识别到股票代码 {c}，正在获取实时股价与贝塔……": "Stock code {c} recognised; fetching live price and beta…",
    "年报解析结果（万元，可直接修改）": "Extracted figures (RMB 10k, editable)",
    "文件": "File", "报告年度": "Report year", "公司": "Company", "资产负债表页码": "Balance sheet page",
    "利润表页码": "Income statement page", "现金流量表页码": "Cash flow page", "补充资料页码": "Supplementary note page",
    "提示": "Notes",
    "PDF_MERGE_NOTE": ("Each report contains the current and prior year. A year's figures come preferably from the following "
                       "year's report (restated, consistent with later years); otherwise from that year's own report. "
                       "Edit any cell and the whole valuation recalculates."),
    "未取得股价：请在左侧填写每股价格（非上市公司可填最近一轮融资价格）后继续。":
        "No share price available: enter a price per share on the left (for unlisted companies, e.g. the latest funding round).",
    "年报中未找到股本，无法计算每股价值。请在上方表格中补充「股本（万股）」。":
        "Share capital was not found in the reports, so value per share cannot be computed. Add “Shares (10k)” in the table above.",
    "年报 PDF": "Annual report PDF",
    "财务数据来自上传的 {n} 份年报（{y0}–{y1}）；股价{p}。": "Financials from {n} uploaded annual report(s) ({y0}–{y1}); share price {p}.",
    "为手动输入": "entered manually", "来自实时行情": "from the live quote",
    "无股价数据（非上市公司或行情获取失败）": "No price history (unlisted company or quote unavailable)",
    "Excel 模板": "Excel template",
    "下载已填入本公司数据的模板（中文）": "Download the template filled with this company (Chinese)",
    "TEMPLATE_FILLED_HELP": ("Fills the History sheet with this company's last five years and the Assumptions sheet with the "
                             "current assumptions; the results match the web page."),
    "股本（万股）": "Shares (10k)", "税金及附加": "Taxes and surcharges", "销售费用": "Selling expenses",
    "管理费用": "Admin expenses", "财务费用": "Finance expenses", "营业利润": "Operating profit",
    "固定资产": "Fixed assets", "固定资产折旧": "Depreciation of fixed assets", "使用权资产折旧": "Right-of-use depreciation",
    "无形资产摊销": "Amortisation of intangibles", "长期待摊费用摊销": "Amortisation of long-term prepaid expenses",
    "短期借款": "Short-term borrowings", "长期借款": "Long-term borrowings", "应付债券": "Bonds payable",
    "一年内到期非流动负债": "Non-current liabilities due within one year", "应收账款": "Accounts receivable",
    "存货": "Inventory", "应付账款": "Accounts payable", "营业收入": "Operating revenue", "营业成本": "Cost of sales",
    "所得税": "Income tax", "净利润": "Net profit",
    "FCFF_NEG": ("Free cash flow in the final forecast year is negative, so the terminal value is negative too and the DCF is "
                 "not meaningful. A common cause is an expansion phase: capex / revenue ({cx:.1f}%) is far above D&A / "
                 "revenue ({da:.1f}%), and the model carries that ratio into perpetuity. Lower capex towards a maintenance "
                 "level close to D&A under “Capex & working capital” on the left."),
    # ── 计算表
    "蓝字 = 可直接修改": "Blue = editable",
    "STMT_EDIT_NOTE": ("Click a blue cell to edit it (revenue growth, core margin, investment income & other, capex / revenue, "
                       "D&A / revenue). After Enter, the statements, DCF, Monte Carlo and sensitivity all recalculate and the "
                       "edited cell turns yellow; clear a cell to restore the default. Historical columns come from the data "
                       "endpoint and are locked; to use figures you have checked, choose “Upload annual report PDF”."),
    "STMT_EDIT_NOTE_PDF": ("Click a blue cell to edit it: blue rows in forecast columns are assumptions, blue rows in historical "
                           "columns are line items extracted from the reports (correct them here if needed). Everything "
                           "recalculates after Enter and edited cells turn yellow; clear an assumption cell to restore the default."),
    "年报原始科目（全部年份，可修改）": "All extracted line items (all years, editable)",
    "计算表": "Model",
    "蓝字 = 由假设驱动": "Blue = driven by assumptions", "黄底 = 手动修改过": "Yellow = edited",
    "灰底 = 历史实际": "Grey = historical actual",
    "关键假设（逐年，可直接修改）": "Key assumptions by year (editable)",
    "营收增速（%）": "Revenue growth (%)", "核心经营利润率（%）": "Core operating margin (%)",
    "投资收益及其他（万元）": "Investment income & other (RMB 10k)",
    "资本开支 / 营收（%）": "Capex / revenue (%)", "折旧摊销 / 营收（%）": "D&A / revenue (%)",
    "走势（历史 → 预测）": "Trend (history → forecast)",
    "已手动修改 {n} 格：{items}。其余年份仍按左侧首末年假设线性插值。":
        "{n} cell(s) edited: {items}. Other years still interpolate between the first- and last-year assumptions on the left.",
    "撤销全部手动修改": "Undo all edits",
    "CALC_EDIT_NOTE": ("Click a blue forecast cell (E columns) to edit it; after Enter the statements, DCF, Monte Carlo and "
                       "sensitivity recalculate. Historical columns (A) are reported figures for reference. Edited cells turn yellow."),
    "其余假设在左侧调整：有效税率 {tax:.1f}%、营运资本 / 营收增量 {nwc:.1f}%、投资收益计入现金流比例 {of:.0f}%、分红率 {po:.0f}%（只影响预测资产负债表）。":
        "Other assumptions are set on the left: effective tax {tax:.1f}%, working capital / revenue increase {nwc:.1f}%, "
        "investment income counted in cash flow {of:.0f}%, payout ratio {po:.0f}% (forecast balance sheet only).",
    "营收与增速：历史与预测": "Revenue and growth: history and forecast",
    "营收增速（%，右轴）": "Revenue growth (%, right axis)",
    "利润率与资本开支（%）": "Margin and capex (%)",
    "历史数据（来自上传的年报，可修改）": "Historical data (from uploaded reports, editable)",
    "解析来源与说明": "Extraction sources and notes",
    "HIST_LOCK_NOTE": ("Historical figures come from the financial data endpoint and are locked to match the disclosures. "
                       "To use figures you have checked yourself, choose “Upload annual report PDF” on the left; extracted "
                       "figures can be edited."),
    "三张表（万元）": "Three statements (RMB 10k)",
    "利润表": "Income statement", "现金流量表": "Cash flow statement",
    "资产负债表（经营视角）": "Balance sheet (operating view)",
    "营运资本": "Working capital", "净现金": "Net cash", "其他净资产": "Other net assets",
    "营运资本/营收%": "Working capital / revenue %", "平衡检查": "Balance check",
    "经营活动现金流": "Operating cash flow", "自由现金流": "Free cash flow", "分红": "Dividends",
    "资本开支/营收%": "Capex / revenue %", "折旧摊销/营收%": "D&A / revenue %",
    "STMT_NOTE_利润表": ("Core operating profit = revenue − total operating cost; investment income & other = pre-tax profit − "
                        "core operating profit (wealth-management income, subsidies, etc.). Forecast: revenue rolls forward by "
                        "growth, core profit = revenue × margin, tax = pre-tax profit × effective rate."),
    "STMT_NOTE_现金流量表": ("Forecast operating cash flow = net profit to parent + D&A − increase in working capital (simplified); "
                          "free cash flow = operating cash flow − capex; dividends = net profit × payout ratio. Historical "
                          "columns show reported operating cash flow and capex."),
    "STMT_NOTE_资产负债表": ("Operating-view balance sheet: working capital = receivables + inventory − payables; net cash = cash + "
                          "trading financial assets − interest-bearing debt; other net assets is the balancing item (equity "
                          "investments, other assets and liabilities) held at the base-year level. Forecasts roll forward: fixed "
                          "assets += capex − D&A, net cash += net profit + D&A − capex − Δworking capital − dividends, equity += "
                          "net profit − dividends, so the balance check is always 0."),
    "自由现金流与折现（万元）": "Free cash flow and discounting (RMB 10k)",
    "终值": "Terminal value",
    "估值结论": "Valuation conclusion",
    "每股内在价值（元）": "Intrinsic value per share (RMB)",
    "蒙特卡洛 90% 区间（元）": "Monte Carlo 90% range (RMB)",
    "价值高于现价的概率": "P(value > price)",
    "模型 {w:.2f}%": "Model {w:.2f}%",
    "高于": "above", "低于": "below",
    "VERDICT_1": ("On the current assumptions, {name}'s intrinsic value is RMB {v:.2f} per share, about {x:.0%} {dir} the price "
                  "of RMB {px:.2f}; the Monte Carlo 90% range is RMB {p5:.2f}–{p95:.2f}, with a {pa:.1%} probability of "
                  "exceeding the price."),
    "VERDICT_2": "{tv:.0f}% of enterprise value comes from the terminal value; net cash contributes RMB {nc:.2f} per share ({ncp:.0%} of value).",
    "VERDICT_3": "The valuation is most sensitive to “{f}”: moving it by {r} puts value per share between RMB {lo:.2f} and {hi:.2f}.",
    "VERDICT_4": ("For the DCF to equal the price, the discount rate would have to fall to {iw:.2f}% (model: {w:.2f}%). Whether the "
                  "price is reasonable depends on whether this implied required return, and the growth and margin conditions "
                  "listed under “What the price implies”, are credible."),
    "VERDICT_4N": "Under the current operating assumptions, no discount rate above terminal growth brings the DCF up to the price.",
    "其中 {n} 个逐年假设为手动修改（见上方黄底单元格）。": "{n} of the yearly assumptions were edited manually (yellow cells above).",
    "VERDICT_NOTE": "The conclusion follows entirely from the assumptions above and updates as they change; for study purposes only, not investment advice.",
    "分红率（%）": "Payout ratio (%)",
    "只影响计算表中预测资产负债表的净现金与权益，不影响折现法": "Affects only net cash and equity in the forecast balance sheet on the Model tab, not the DCF",
    "总股本（万股，0 = 取年报）": "Shares outstanding (10k, 0 = from report)",
    "SHARES_HELP": "Share capital found in the reports is used automatically; enter a number if it was not found or to use a different share count.",
    "年报中未找到股本，无法计算每股价值。请在左侧填写总股本。": "Share capital was not found in the reports; enter shares outstanding on the left.",
    "单位：万元；蓝色为逐年假设，可直接修改": "Units: RMB 10k; blue rows are yearly assumptions and can be edited",
    # ── Excel
    "{n}（{c}）估值模型": "{n} ({c}) valuation model",
    "说明": "Notes",
    "单位": "Units",
    "金额：万元；每股：元；比率：%": "Amounts: RMB 10k; per share: RMB; ratios: %",
    "格式约定": "Conventions",
    "蓝色字体为输入，黑色字体为公式。改动「假设」表中任一蓝色单元格，全部结果自动重算。":
        "Blue = input, black = formula. Change any blue cell on the Assumptions sheet and everything recalculates.",
    "工作表": "Sheets",
    "假设 → 预测与折现法 → 敏感性；历史数据与蒙特卡洛结果为数值。":
        "Assumptions → Forecast & DCF → Sensitivity; History and Monte Carlo are values.",
    "模型结构": "Model structure",
    "营业总收入 × 核心经营利润率 = 核心经营利润；+ 投资收益及其他 = 利润总额；× (1 − 有效税率) × (1 − 少数股东占比) = 归母净利润。":
        "Total revenue × core operating margin = core operating profit; + investment income & other = pre-tax profit; × (1 − effective tax) × (1 − minority share) = net profit to parent.",
    "akshare（东方财富、新浪公开接口）；东方财富行情接口。非官方授权数据。":
        "akshare (Eastmoney and Sina public endpoints); Eastmoney quote endpoint. Not officially licensed data.",
    "声明": "Disclaimer",
    "个人学习项目，结论基于用户假设，不构成投资建议。":
        "Personal study project; conclusions depend on user assumptions and are not investment advice.",
    "假设": "Assumptions",
    "假设与输入": "Assumptions and inputs",
    "{y}A 营业总收入（万元）": "FY{y} total revenue (RMB 10k)",
    "财报": "Financial statements",
    "中间年份线性插值": "Linear interpolation in between",
    "（营业总收入−营业总成本）÷ 营业总收入": "(total revenue − total operating cost) ÷ total revenue",
    "利润总额 − 核心经营利润": "Pre-tax profit − core operating profit",
    "其中计入经营现金流比例（%）": "Share counted in operating cash flow (%)",
    "0 表示折现法只对核心主业定价": "0 means the DCF values the core business only",
    "少数股东占比（%）": "Minority share (%)",
    "货币资金（万元）": "Cash (RMB 10k)",
    "交易性金融资产（万元）": "Trading financial assets (RMB 10k)",
    "有息负债（万元）": "Interest-bearing debt (RMB 10k)",
    "货币资金计入净现金（1=是，0=否）": "Include cash in net cash (1 = yes, 0 = no)",
    "交易性金融资产计入净现金（1=是，0=否）": "Include trading financial assets in net cash (1 = yes, 0 = no)",
    "总股本（万股）": "Shares outstanding (10k)",
    "总市值（万元）": "Market cap (RMB 10k)",
    "行情接口": "Quote endpoint",
    "默认可比公司中位数": "Default: peer median",
    "预测与折现法": "Forecast & DCF",
    "单位：万元": "Units: RMB 10k",
    "营收增速（%）": "Revenue growth (%)",
    "自由现金流 FCFF": "Free cash flow (FCFF)",
    "折现年数": "Discount period (years)",
    "估值": "Valuation",
    "股权成本（%）": "Cost of equity (%)",
    "税后债务成本（%）": "After-tax cost of debt (%)",
    "债务权重（%）": "Debt weight (%)",
    "折现率 WACC（%）": "WACC (%)",
    "预测期现值合计": "PV of forecast FCFF",
    "终值": "Terminal value",
    "终值现值": "PV of terminal value",
    "企业价值": "Enterprise value",
    "加：货币资金": "Add: cash",
    "加：交易性金融资产": "Add: trading financial assets",
    "减：有息负债": "Less: interest-bearing debt",
    "股权价值": "Equity value",
    "每股价值（元）": "Value per share (RMB)",
    "终值占企业价值（%）": "Terminal value / EV (%)",
    "敏感性": "Sensitivity",
    "行：折现率（%）；列：永续增长率（%）。坐标轴随「假设」联动。":
        "Rows: WACC (%); columns: terminal growth (%). Axes are linked to the Assumptions sheet.",
    "{y}年预测归母净利润（万元）": "{y}E net profit to parent (RMB 10k)",
    "预测每股收益（元）": "Forecast EPS (RMB)",
    "倍数调整": "Multiple change",
    "市盈率（倍）": "P/E (x)",
    "市值（亿元）": "Market cap (RMB 100m)",
    "每股（元）": "Per share (RMB)",
    "可比公司（数值，截至导出时）": "Comparables (values as of export)",
    "纳入统计": "Included",
    "市盈率(TTM) 中位数（纳入=1）": "Median P/E (TTM) (included = 1)",
    "历史数据": "History",
    "历史财务数据（万元 / %）": "Historical financials (RMB 10k / %)",
    "蒙特卡洛": "Monte Carlo",
    "蒙特卡洛模拟（数值）": "Monte Carlo simulation (values)",
    "观测区间": "Observation period",
    "第1年增速波动缩放": "Year-1 growth volatility scaling",
    "年份": "Year",
    "增速σ（pp）": "Growth σ (pp)",
    "利润率σ（pp）": "Margin σ (pp)",
    "蒙特卡洛依赖随机抽样，无法用单元格公式表达，此处为导出时的计算结果。":
        "The Monte Carlo relies on random sampling and cannot be written as cell formulas; these are the results at export time.",
}
