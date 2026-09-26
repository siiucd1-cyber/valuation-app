# -*- coding: utf-8 -*-
"""中英双语。界面文字以中文为键；英文模式下查 EN 表，查不到则原样显示中文。
长段落用大写英文键（如 MC_EXPLAIN），中英文分别在 ZH / EN 中给出。"""
from __future__ import annotations

import re


def is_en() -> bool:
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
        "可以用下方的窗口滑块只取最近 N 年。"),
    "MC_SRC_HELP": ("单季滚动 TTM：观测多，但相邻观测重叠，适合上市时间短的公司；"
                    "年度同比：观测互不重叠，历史长时更可靠；手动输入：自己给定标准差与相关系数。"),
    "MC_CMP_NOTE": ("两种口径并排对比。滚动 TTM 的相邻观测共享 3 个季度，等效独立样本约为观测数 ÷ 4；"
                    "年度口径观测不重叠。两者结论差异大时，说明参数本身不确定，应以区间而非单点看待模拟结果。"),
    "DUPONT_NOTE": ("净资产收益率 = 归母净利率 × 资产周转率 × 权益乘数（均用期初期末平均值）。"
                    "经营性ROE = 扣非归母净利润 ÷（平均归母权益 − 平均货币资金与交易性金融资产），"
                    "用于剔除闲置资金对回报率的稀释。"),
    "FCFF_NOTE": ("NOPAT =（核心经营利润 + 投资收益及其他 × 计入比例）×（1 − 税率）；"
                  "FCFF = NOPAT + 折旧摊销 − 资本开支 − 营运资金增加；年末折现。"),
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
    "- **折现法**：折现率 {w:.2f}%（股权成本 {ke:.2f}%，贝塔 {b:.2f}），永续增长率 {g:.2f}%，得到每股 {v:.2f} 元；终值占企业价值 {tv:.1f}%。其中净现金贡献 {nc:.2f} 元/股，占每股价值的 {ncp:.0%}。\n- **市盈率法**：{y}年预测归母净利润 {np_:.2f} 亿元、每股收益 {eps:.2f} 元，给予 {pe:.1f} 倍，得到每股 {pv:.2f} 元。\n- **蒙特卡洛**：{n:,} 次模拟（参数来源：{src}），折现法每股价值中位数 {p50:.2f} 元，90% 的结果落在 {p5:.2f}–{p95:.2f} 元。":
        ("- **DCF**: WACC {w:.2f}% (cost of equity {ke:.2f}%, beta {b:.2f}), terminal growth {g:.2f}%, giving "
         "RMB {v:.2f} per share; terminal value is {tv:.1f}% of EV. Net cash contributes RMB {nc:.2f} per share, "
         "{ncp:.0%} of the value.\n"
         "- **P/E method**: {y}E net profit to parent RMB {npm:,.0f}m, EPS RMB {eps:.2f}; at {pe:.1f}x this gives "
         "RMB {pv:.2f} per share.\n"
         "- **Monte Carlo**: {n:,} simulations (parameters: {src}); median DCF value RMB {p50:.2f} per share, with 90% "
         "of outcomes between RMB {p5:.2f} and {p95:.2f}."),
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
        "Very old data may reflect a different business, so use the window slider below to keep only the last N years."),
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
    "Excel 中的预测、折现法、敏感性、市盈率法均为**活公式**：蓝色为输入，改动「假设」表任一蓝色单元格，全部结果自动重算。蒙特卡洛结果以数值形式附上。当前语言决定 Excel 的语言。":
        "The forecast, DCF, sensitivity and P/E sheets in Excel are **live formulas**: blue cells are inputs, and changing any blue cell on the Assumptions sheet recalculates everything. Monte Carlo results are included as values. The Excel file uses the current language.",
    "下载 Excel 估值模型": "Download the Excel model",
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

    # ── Excel
    "{n}（{c}）估值模型": "{n} ({c}) valuation model",
    "说明": "Notes",
    "单位": "Units",
    "金额：万元；每股：元；比率：%": "Amounts: RMB 10k; per share: RMB; ratios: %",
    "格式约定": "Conventions",
    "蓝色字体为输入，黑色字体为公式。改动「假设」表中任一蓝色单元格，全部结果自动重算。":
        "Blue = input, black = formula. Change any blue cell on the Assumptions sheet and everything recalculates.",
    "工作表": "Sheets",
    "假设 → 预测与折现法 → 敏感性 → 市盈率法；历史数据与蒙特卡洛结果为数值。":
        "Assumptions → Forecast & DCF → Sensitivity → P/E method; History and Monte Carlo are values.",
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
