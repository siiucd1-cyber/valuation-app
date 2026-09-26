# -*- coding: utf-8 -*-
"""导出 Excel 估值模型：预测、折现法、敏感性、市盈率法全部为活公式。
约定：蓝色字体 = 输入；黑色字体 = 公式。"""
from __future__ import annotations

import io

import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.formula import ArrayFormula

from i18n import T, TL

BLUE = Font(name="等线", size=10, color="0000CC")
BLACK = Font(name="等线", size=10)
BOLD = Font(name="等线", size=10, bold=True)
TITLE = Font(name="等线", size=14, bold=True)
NOTE = Font(name="等线", size=9, italic=True, color="808080")
HEAD = PatternFill("solid", fgColor="E7E6E6")
KEY = PatternFill("solid", fgColor="F2F2F2")
thin = Side(style="thin", color="BFBFBF")
BOX = Border(top=thin, bottom=thin, left=thin, right=thin)
N2, N0, N4, PCT = "#,##0.00", "#,##0", "0.0000", "0.00"


def _c(ws, r, c, v, font=BLACK, fmt=None, fill=None, al=None):
    x = ws.cell(row=r, column=c, value=v)
    x.font, x.border = font, BOX
    if fmt:
        x.number_format = fmt
    if fill:
        x.fill = fill
    if al:
        x.alignment = Alignment(horizontal=al, vertical="center", wrap_text=True)
    return x


def _head(ws, r, labels, c0=1):
    for i, t in enumerate(TL(labels)):
        _c(ws, r, c0 + i, t, BOLD, fill=HEAD, al="center")


def _sheet(name: str) -> str:
    """Excel 表名不能含 / \\ ? * [ ] :，且不超过 31 个字符。"""
    t = T(name)
    for ch in '/\\?*[]:':
        t = t.replace(ch, "")
    return t[:31]


def build_workbook(cd: dict, A, res: dict) -> bytes:
    q, an, bs = cd["quote"], cd["annual"], cd["bs_latest"]
    base = int(an.index.max())
    wb = Workbook()
    wb.remove(wb.active)
    SA, SF, SS, SP = [_sheet(x) for x in ("假设", "预测与折现法", "敏感性", "市盈率法")]
    F = f"'{SF}'!"

    # ── 说明
    ws = wb.create_sheet(_sheet("说明"))
    ws.column_dimensions["A"].width = 18; ws.column_dimensions["B"].width = 90
    ws["A1"] = T("{n}（{c}）估值模型", n=q["name"], c=q["code"]); ws["A1"].font = TITLE
    rows = [("数据时间", cd.get("asof", "")),
            ("单位", "金额：万元；每股：元；比率：%"),
            ("格式约定", "蓝色字体为输入，黑色字体为公式。改动「假设」表中任一蓝色单元格，全部结果自动重算。"),
            ("工作表", "假设 → 预测与折现法 → 敏感性 → 市盈率法；历史数据与蒙特卡洛结果为数值。"),
            ("模型结构", "营业总收入 × 核心经营利润率 = 核心经营利润；+ 投资收益及其他 = 利润总额；"
                     "× (1 − 有效税率) × (1 − 少数股东占比) = 归母净利润。"),
            ("数据来源", "akshare（东方财富、新浪公开接口）；东方财富行情接口。非官方授权数据。"),
            ("声明", "个人学习项目，结论基于用户假设，不构成投资建议。")]
    for i, (k, v) in enumerate(rows, start=3):
        _c(ws, i, 1, T(k), BOLD, fill=KEY); _c(ws, i, 2, T(v), al="left")

    # ── 假设（命名单元格位置）
    wa = wb.create_sheet(SA)
    wa.column_dimensions["A"].width = 30; wa.column_dimensions["B"].width = 14
    wa.column_dimensions["C"].width = 60
    wa["A1"] = T("假设与输入"); wa["A1"].font = TITLE
    _head(wa, 3, ["项目", "数值", "说明"])
    items = [
        ("base_rev", T("{y}A 营业总收入（万元）", y=base), float(an.loc[base, "营业总收入"]), "财报"),
        ("g1", "第1年营收增速（%）", A.g_first, "中间年份线性插值"),
        ("g5", "第5年营收增速（%）", A.g_last, ""),
        ("m1", "第1年核心经营利润率（%）", A.m_first, "（营业总收入−营业总成本）÷ 营业总收入"),
        ("m5", "第5年核心经营利润率（%）", A.m_last, ""),
        ("o1", "第1年投资收益及其他（万元）", A.other_first, "利润总额 − 核心经营利润"),
        ("oc", "投资收益及其他年变化（%）", A.other_change, ""),
        ("of", "其中计入经营现金流比例（%）", A.other_in_fcf, "0 表示折现法只对核心主业定价"),
        ("tax", "有效税率（%）", A.tax, ""),
        ("mino", "少数股东占比（%）", A.minority, ""),
        ("da", "折旧摊销 / 营收（%）", A.da_pct, ""),
        ("cx", "资本开支 / 营收（%）", A.capex_pct, ""),
        ("nwc", "营运资金增加 / 营收增量（%）", A.nwc_pct, ""),
        ("rf", "无风险利率（%）", A.rf, "10年期国债"),
        ("beta", "贝塔", A.beta, "100周回归"),
        ("erp", "市场风险溢价（%）", A.erp, ""),
        ("sp", "规模溢价（%）", A.size_prem, ""),
        ("kd", "税前债务成本（%）", A.kd, ""),
        ("gt", "永续增长率（%）", A.g_term, ""),
        ("cash", "货币资金（万元）", bs["货币资金"], bs["报告期"]),
        ("fin", "交易性金融资产（万元）", bs["交易性金融资产"], bs["报告期"]),
        ("debt", "有息负债（万元）", bs["有息负债"], bs["报告期"]),
        ("add_cash", "货币资金计入净现金（1=是，0=否）", int(A.add_cash), ""),
        ("add_fin", "交易性金融资产计入净现金（1=是，0=否）", int(A.add_fin), ""),
        ("shares", "总股本（万股）", q["shares"] / 1e4, "行情接口"),
        ("mcap", "总市值（万元）", q["mcap_yi"] * 1e4, "行情接口"),
        ("price", "现价（元）", q["price"], "行情接口"),
        ("pe", "目标市盈率（倍）", A.target_pe, "默认可比公司中位数"),
    ]
    R = {}
    for i, (k, lab, v, note) in enumerate(items, start=4):
        _c(wa, i, 1, T(lab), al="left")
        _c(wa, i, 2, float(v), BLUE, N2 if abs(float(v)) >= 100 else "0.00")
        _c(wa, i, 3, T(note), NOTE, al="left")
        R[k] = f"'{SA}'!$B${i}"

    # ── 预测与折现法
    wf = wb.create_sheet(SF)
    wf.column_dimensions["A"].width = 30
    for col in range(2, 9):
        wf.column_dimensions[get_column_letter(col)].width = 14
    wf["A1"] = T("盈利预测与折现法"); wf["A1"].font = TITLE
    wf["A2"] = T("单位：万元"); wf["A2"].font = NOTE
    n = 5
    _head(wf, 4, ["项目", f"{base}A"] + [f"{base + i + 1}E" for i in range(n)])
    lab = {5: "营收增速（%）", 6: "营业总收入", 7: "核心经营利润率（%）", 8: "核心经营利润",
           9: "投资收益及其他", 10: "利润总额", 11: "归母净利润", 12: "NOPAT",
           13: "折旧摊销", 14: "资本开支", 15: "营运资金增加", 16: "自由现金流 FCFF",
           17: "折现年数", 18: "折现因子", 19: "现值"}
    for r_, t in lab.items():
        _c(wf, r_, 1, T(t), BOLD if r_ in (6, 11, 16, 19) else BLACK, fill=KEY if r_ in (6, 11, 16) else None,
           al="left")
    _c(wf, 6, 2, f"={R['base_rev']}", fmt=N2)
    _c(wf, 7, 2, float(an.loc[base, "核心经营利润率%"]), BLUE, PCT)
    _c(wf, 8, 2, float(an.loc[base, "核心经营利润"]), BLUE, N2)
    _c(wf, 9, 2, float(an.loc[base, "投资收益及其他"]), BLUE, N2)
    _c(wf, 10, 2, float(an.loc[base, "利润总额"]), BLUE, N2)
    _c(wf, 11, 2, float(an.loc[base, "归母净利润"]), BLUE, N2)
    for i in range(n):
        C = get_column_letter(3 + i); P = get_column_letter(2 + i)
        _c(wf, 5, 3 + i, f"={R['g1']}+({R['g5']}-{R['g1']})*{i}/{n - 1}", fmt=PCT)
        _c(wf, 6, 3 + i, f"={P}6*(1+{C}5/100)", fmt=N2, fill=KEY)
        _c(wf, 7, 3 + i, f"={R['m1']}+({R['m5']}-{R['m1']})*{i}/{n - 1}", fmt=PCT)
        _c(wf, 8, 3 + i, f"={C}6*{C}7/100", fmt=N2)
        _c(wf, 9, 3 + i, f"={R['o1']}*(1+{R['oc']}/100)^{i}", fmt=N2)
        _c(wf, 10, 3 + i, f"={C}8+{C}9", fmt=N2)
        _c(wf, 11, 3 + i, f"={C}10*(1-{R['tax']}/100)*(1-{R['mino']}/100)", fmt=N2, fill=KEY)
        _c(wf, 12, 3 + i, f"=({C}8+{C}9*{R['of']}/100)*(1-{R['tax']}/100)", fmt=N2)
        _c(wf, 13, 3 + i, f"={C}6*{R['da']}/100", fmt=N2)
        _c(wf, 14, 3 + i, f"={C}6*{R['cx']}/100", fmt=N2)
        _c(wf, 15, 3 + i, f"=({C}6-{P}6)*{R['nwc']}/100", fmt=N2)
        _c(wf, 16, 3 + i, f"={C}12+{C}13-{C}14-{C}15", fmt=N2, fill=KEY)
        _c(wf, 17, 3 + i, i + 1, fmt="0")
        _c(wf, 18, 3 + i, f"=1/(1+$B$26/100)^{C}17", fmt=N4)
        _c(wf, 19, 3 + i, f"={C}16*{C}18", fmt=N2)

    LC = get_column_letter(2 + n)  # 最后一年所在列
    blk = [(22, "股权成本（%）", f"={R['rf']}+{R['beta']}*{R['erp']}+{R['sp']}", PCT),
           (23, "税后债务成本（%）", f"={R['kd']}*(1-{R['tax']}/100)", PCT),
           (24, "债务权重（%）", f"=IF({R['debt']}+{R['mcap']}>0,{R['debt']}/({R['debt']}+{R['mcap']})*100,0)", PCT),
           (26, "折现率 WACC（%）", "=B22*(1-B24/100)+B23*B24/100", PCT),
           (27, "永续增长率（%）", f"={R['gt']}", PCT),
           (29, "预测期现值合计", f"=SUM(C19:{LC}19)", N2),
           (30, "终值", f"={LC}16*(1+B27/100)/(B26/100-B27/100)", N2),
           (31, "终值现值", f"=B30*{LC}18", N2),
           (32, "企业价值", "=B29+B31", N2),
           (33, "加：货币资金", f"={R['cash']}*{R['add_cash']}", N2),
           (34, "加：交易性金融资产", f"={R['fin']}*{R['add_fin']}", N2),
           (35, "减：有息负债", f"={R['debt']}", N2),
           (36, "股权价值", "=B32+B33+B34-B35", N2),
           (37, "总股本（万股）", f"={R['shares']}", N2),
           (38, "每股价值（元）", "=B36/B37", N2),
           (39, "终值占企业价值（%）", "=B31/B32*100", PCT),
           (40, "较现价", f"=B38/{R['price']}-1", "0.0%")]
    wf.cell(row=21, column=1, value=T("折现率")).font = TITLE
    wf.cell(row=28, column=1, value=T("估值")).font = TITLE
    for r_, t, f, fm in blk:
        _c(wf, r_, 1, T(t), BOLD if r_ in (26, 32, 36, 38) else BLACK, al="left",
           fill=KEY if r_ in (26, 38) else None)
        _c(wf, r_, 2, f, fmt=fm, fill=KEY if r_ in (26, 38) else None)

    # ── 敏感性
    wsn = wb.create_sheet(SS)
    wsn.column_dimensions["A"].width = 22
    wsn["A1"] = T("敏感性：每股价值（元）"); wsn["A1"].font = TITLE
    wsn["A2"] = T("行：折现率（%）；列：永续增长率（%）。坐标轴随「假设」联动。"); wsn["A2"].font = NOTE
    _c(wsn, 4, 1, "WACC \\ g", BOLD, fill=HEAD, al="center")
    dws, dgs = [-2, -1, 0, 1, 2], [-1.0, -0.5, 0, 0.5, 1.0]
    for j, dg in enumerate(dgs):
        _c(wsn, 4, 2 + j, f"={F}$B$27+({dg})", BOLD, PCT, HEAD, "center")
    exps = "{" + ",".join(str(i + 1) for i in range(n)) + "}"
    for i, dw in enumerate(dws):
        r_ = 5 + i
        _c(wsn, r_, 1, f"={F}$B$26+({dw})", BOLD, PCT, HEAD, "center")
        for j in range(len(dgs)):
            gc = f"{get_column_letter(2 + j)}$4"
            w_ = f"$A{r_}"
            f = (f"=IF({w_}<={gc},\"—\",(SUMPRODUCT({F}$C$16:${LC}$16/(1+{w_}/100)^{exps})"
                 f"+{F}${LC}$16*(1+{gc}/100)/({w_}/100-{gc}/100)/(1+{w_}/100)^{n}"
                 f"+{F}$B$33+{F}$B$34-{F}$B$35)/{F}$B$37)")
            _c(wsn, r_, 2 + j, f, fmt=N2, fill=KEY if (dw == 0 and dgs[j] == 0) else None, al="center")

    # ── 市盈率法
    wp = wb.create_sheet(SP)
    wp.column_dimensions["A"].width = 28
    for col in range(2, 9):
        wp.column_dimensions[get_column_letter(col)].width = 14
    wp["A1"] = T("市盈率法"); wp["A1"].font = TITLE
    steps = [(3, T("{y}年预测归母净利润（万元）", y=base + 1), f"={F}C11", N2),
             (4, "总股本（万股）", f"={R['shares']}", N2),
             (5, "预测每股收益（元）", "=B3/B4", N4),
             (6, "目标市盈率（倍）", f"={R['pe']}", "0.0"),
             (7, "每股价值（元）", "=B5*B6", N2),
             (8, "较现价", f"=B7/{R['price']}-1", "0.0%")]
    for r_, t, f, fm in steps:
        _c(wp, r_, 1, T(t), BOLD if r_ == 7 else BLACK, al="left", fill=KEY if r_ == 7 else None)
        _c(wp, r_, 2, f, fmt=fm, fill=KEY if r_ == 7 else None)
    _head(wp, 10, ["倍数调整", "市盈率（倍）", "市值（亿元）", "每股（元）"])
    for i, s in enumerate([-0.2, -0.1, 0, 0.1, 0.2]):
        r_ = 11 + i
        _c(wp, r_, 1, s, BLUE, "+0%;-0%;0%", al="center")
        _c(wp, r_, 2, f"=$B$6*(1+A{r_})", fmt="0.0")
        _c(wp, r_, 3, f"=B{r_}*$B$3/10000", fmt=N2)
        _c(wp, r_, 4, f"=B{r_}*$B$5", fmt=N2)
    comps = cd.get("comps")
    if comps is not None and len(comps):
        r0 = 18
        wp.cell(row=r0 - 1, column=1, value=T("可比公司（数值，截至导出时）")).font = BOLD
        cols = ["代码", "名称", "股价", "市盈率(TTM)", "市净率", "总市值(亿元)", "纳入统计"]
        _head(wp, r0, cols)
        for i, (_, row) in enumerate(comps.iterrows()):
            r_ = r0 + 1 + i
            pe = row.get("市盈率(TTM)")
            valid = pe == pe and 0 < pe < 200
            for j, cname in enumerate(cols[:-1]):
                v = row.get(cname)
                v = None if (isinstance(v, float) and np.isnan(v)) else v
                _c(wp, r_, 1 + j, v, BLUE if j >= 2 else BLACK, N2 if j >= 2 else None)
            _c(wp, r_, 7, 1 if valid else 0, BLUE, "0", al="center")
        last = r0 + len(comps)
        _c(wp, last + 2, 1, T("市盈率(TTM) 中位数（纳入=1）"), BOLD, fill=KEY)
        cell = f"B{last + 2}"
        wp[cell] = ArrayFormula(cell, f"=MEDIAN(IF(G{r0 + 1}:G{last}=1,D{r0 + 1}:D{last}))")
        wp[cell].number_format = "0.0"; wp[cell].font = BLACK; wp[cell].fill = KEY; wp[cell].border = BOX

    # ── 历史数据
    wh = wb.create_sheet(_sheet("历史数据"))
    wh.column_dimensions["A"].width = 24
    wh["A1"] = T("历史财务数据（万元 / %）"); wh["A1"].font = TITLE
    show = ["营业总收入", "营收增速%", "毛利率%", "营业总成本", "核心经营利润", "核心经营利润率%",
            "投资收益及其他", "利润总额", "有效税率%", "归母净利润", "扣非归母净利润", "非经常性损益",
            "研发费用", "经营现金流", "资本开支", "折旧摊销", "货币资金", "交易性金融资产",
            "有息负债", "资产总计", "归母权益"]
    _head(wh, 3, ["项目"] + [f"{y}A" for y in an.index])
    for i, k in enumerate(show, start=4):
        _c(wh, i, 1, T(k), al="left")
        for j, y in enumerate(an.index):
            v = an.loc[y, k]
            _c(wh, i, 2 + j, None if v != v else float(v), BLUE, N2)
    for j in range(len(an.index)):
        wh.column_dimensions[get_column_letter(2 + j)].width = 13

    # ── 蒙特卡洛
    wm = wb.create_sheet(_sheet("蒙特卡洛"))
    wm.column_dimensions["A"].width = 30
    for col in "BCDEF":
        wm.column_dimensions[col].width = 13
    wm["A1"] = T("蒙特卡洛模拟（数值）"); wm["A1"].font = TITLE
    e = res["emp"]
    info = [("参数来源", e.get("方法", "—")), ("观测区间", e.get("区间", "—")), ("观测数", e.get("观测数", 0)),
            ("营收增速标准差（pp）", e.get("增速标准差")), ("核心经营利润率标准差（pp）", e.get("利润率标准差")),
            ("相关系数", e.get("相关系数")), ("第1年增速波动缩放", res["y1_scale"]),
            ("模拟次数", res["sims"])]
    for i, (k, v) in enumerate(info, start=3):
        _c(wm, i, 1, T(k), al="left"); _c(wm, i, 2, v, BLUE, N2 if isinstance(v, float) else None)
    _head(wm, 12, ["年份"] + [f"{base + i + 1}E" for i in range(n)])
    _c(wm, 13, 1, T("增速σ（pp）"), al="left"); _c(wm, 14, 1, T("利润率σ（pp）"), al="left")
    for i in range(n):
        _c(wm, 13, 2 + i, float(res["mc_sg"][i]), BLUE, N2)
        _c(wm, 14, 2 + i, float(res["mc_sm"][i]), BLUE, N2)
    _head(wm, 16, ["指标", "P5", "P25", "P50", "P75", "P95"])
    for r_, (k, d) in enumerate([(T("{y}年归母净利润（万元）", y=base + 1), res["mc_np"]),
                                  (T("折现法每股价值（元）"), res["mc_ps"])], start=17):
        _c(wm, r_, 1, k, al="left")
        for j, p in enumerate(["P5", "P25", "P50", "P75", "P95"]):
            _c(wm, r_, 2 + j, float(d[p]), BLUE, N2)
    wm["A20"] = T("蒙特卡洛依赖随机抽样，无法用单元格公式表达，此处为导出时的计算结果。")
    wm["A20"].font = NOTE

    for w in wb.worksheets:
        w.sheet_view.showGridLines = False
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
