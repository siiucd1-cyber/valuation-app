# -*- coding: utf-8 -*-
"""估值模型层：纯计算，不依赖界面。金额单位万元，每股单位元。

结构与 Wind 披露科目一一对应：
    营业总收入 × 核心经营利润率 = 核心经营利润（= 营业总收入 − 营业总成本）
    核心经营利润 + 投资收益及其他 = 利润总额
    利润总额 × (1 − 有效税率) × (1 − 少数股东占比) = 归母净利润
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass
class Assumptions:
    years: int = 5
    # 收入与利润
    g_first: float = 15.0          # 第 1 年营收增速 %
    g_last: float = 6.0            # 第 5 年营收增速 %
    m_first: float = 15.0          # 第 1 年核心经营利润率 %
    m_last: float = 15.0           # 第 5 年核心经营利润率 %
    other_first: float = 0.0       # 第 1 年投资收益及其他（万元）
    other_change: float = -10.0    # 投资收益及其他年变化 %
    other_in_fcf: float = 0.0      # 投资收益及其他中计入经营现金流的比例 %
    tax: float = 15.0              # 有效税率 %
    minority: float = 0.0          # 少数股东占比 %
    # 资本开支与营运资金
    da_pct: float = 2.5            # 折旧摊销 / 营收 %
    capex_pct: float = 3.0         # 资本开支 / 营收 %
    nwc_pct: float = 10.0          # 营运资金增加 / 营收增量 %
    # 折现率
    rf: float = 1.7
    beta: float = 1.2
    erp: float = 5.5
    size_prem: float = 1.0
    kd: float = 3.5
    g_term: float = 2.5
    # 净现金口径
    add_cash: bool = True
    add_fin: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────── 折现率
def wacc(a: Assumptions, debt: float, mcap_wan: float) -> dict:
    ke = a.rf + a.beta * a.erp + a.size_prem
    d = max(debt, 0.0)
    wd = d / (d + mcap_wan) if (d + mcap_wan) > 0 else 0.0
    kd_after = a.kd * (1 - a.tax / 100)
    w = ke * (1 - wd) + kd_after * wd
    return {"股权成本": ke, "税后债务成本": kd_after, "债务权重": wd * 100, "WACC": w}


# ─────────────────────────── 预测
def forecast(rev0: float, base_year: int, a: Assumptions) -> pd.DataFrame:
    n = a.years
    g = np.linspace(a.g_first, a.g_last, n)
    m = np.linspace(a.m_first, a.m_last, n)
    other = a.other_first * (1 + a.other_change / 100) ** np.arange(n)
    rev = rev0 * np.cumprod(1 + g / 100)
    prev = np.concatenate([[rev0], rev[:-1]])
    core = rev * m / 100
    pbt = core + other
    parent = pbt * (1 - a.tax / 100) * (1 - a.minority / 100)
    nopat = (core + other * a.other_in_fcf / 100) * (1 - a.tax / 100)
    da = rev * a.da_pct / 100
    capex = rev * a.capex_pct / 100
    dnwc = (rev - prev) * a.nwc_pct / 100
    fcff = nopat + da - capex - dnwc
    return pd.DataFrame({
        "年份": [f"{base_year + i + 1}E" for i in range(n)],
        "营收增速%": g, "营业总收入": rev, "核心经营利润率%": m, "核心经营利润": core,
        "投资收益及其他": other, "利润总额": pbt, "归母净利润": parent,
        "NOPAT": nopat, "折旧摊销": da, "资本开支": capex, "营运资金增加": dnwc, "FCFF": fcff,
    })


def net_cash(bs: dict, a: Assumptions) -> dict:
    cash = bs.get("货币资金", 0.0) if a.add_cash else 0.0
    fin = bs.get("交易性金融资产", 0.0) if a.add_fin else 0.0
    debt = bs.get("有息负债", 0.0)
    return {"货币资金": cash, "交易性金融资产": fin, "有息负债": debt, "净现金": cash + fin - debt}


def dcf(fc: pd.DataFrame, w: float, g_term: float, nc: float, shares_wan: float) -> dict:
    if w <= g_term:
        raise ValueError("折现率必须高于永续增长率")
    t = np.arange(1, len(fc) + 1)
    disc = 1 / (1 + w / 100) ** t
    f = fc["FCFF"].values
    pv = f * disc
    tv = f[-1] * (1 + g_term / 100) / (w / 100 - g_term / 100)
    tv_pv = tv * disc[-1]
    ev = pv.sum() + tv_pv
    eq = ev + nc
    return {"折现因子": disc, "现值": pv, "预测期现值合计": pv.sum(), "终值": tv,
            "终值现值": tv_pv, "企业价值": ev, "净现金": nc, "股权价值": eq,
            "每股价值": eq / shares_wan, "终值占比%": tv_pv / ev * 100 if ev else np.nan}


def sensitivity(fc: pd.DataFrame, nc: float, shares_wan: float, w0: float, g0: float,
                dw: float = 1.0, dg: float = 0.5, k: int = 2) -> pd.DataFrame:
    ws = [w0 + dw * i for i in range(-k, k + 1)]      # 不取整，保证中心格 = 主结果
    gs = [g0 + dg * j for j in range(-k, k + 1)]
    out = pd.DataFrame(index=[f"{w:.2f}%" for w in ws], columns=[f"{g:.1f}%" for g in gs],
                       dtype=float)
    for w in ws:
        for g in gs:
            out.loc[f"{w:.2f}%", f"{g:.1f}%"] = (
                dcf(fc, w, g, nc, shares_wan)["每股价值"] if w > g else np.nan)
    out.index.name = "折现率 \\ 永续增长率"
    return out


# ─────────────────────────── 反推：现价隐含的折现率
def implied_wacc(fc: pd.DataFrame, g_term: float, nc: float, shares_wan: float, price: float,
                 lo: float | None = None, hi: float = 60.0) -> float:
    """二分法求使折现法每股价值等于现价的折现率（%）；无解时返回 nan。"""
    lo = g_term + 0.05 if lo is None else lo
    f = lambda w: dcf(fc, w, g_term, nc, shares_wan)["每股价值"] - price
    if f(lo) < 0 or f(hi) > 0:
        return float("nan")
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) > 0 else (lo, mid)
    return (lo + hi) / 2


# ─────────────────────────── 历史检验与杜邦
def regression_check(row: pd.Series) -> dict:
    """用模型结构还原最近一个年度的归母净利润"""
    core = row["营业总收入"] * row["核心经营利润率%"] / 100
    pbt = core + row["投资收益及其他"]
    np_ = pbt * (1 - row["有效税率%"] / 100) * (1 - row["少数股东占比%"] / 100)
    return {"核心经营利润": core, "利润总额": pbt, "模型归母": np_,
            "披露归母": row["归母净利润"], "偏差": np_ - row["归母净利润"]}


def dupont(annual: pd.DataFrame) -> pd.DataFrame:
    a = annual.copy()
    avg = lambda c: (a[c] + a[c].shift(1)) / 2
    a["平均总资产"] = avg("资产总计")
    a["平均归母权益"] = avg("归母权益")
    a["平均金融资产"] = avg("交易性金融资产") + avg("货币资金")
    out = pd.DataFrame(index=a.index)
    out["净资产收益率%"] = a["归母净利润"] / a["平均归母权益"] * 100
    out["归母净利率%"] = a["归母净利润"] / a["营业总收入"] * 100
    out["资产周转率(次)"] = a["营业总收入"] / a["平均总资产"]
    out["权益乘数"] = a["平均总资产"] / a["平均归母权益"]
    out["剔除金融资产后的经营性ROE%"] = (
        a["扣非归母净利润"] / (a["平均归母权益"] - a["平均金融资产"]) * 100)
    return out.dropna(how="all")


# ─────────────────────────── 滚动 TTM 与蒙特卡洛
def rolling_ttm(q: pd.DataFrame) -> pd.DataFrame:
    rev = q["营业总收入"].values
    cost = q["营业总成本"].values
    if len(rev) < 8:
        return pd.DataFrame()
    ttm_r = np.convolve(rev, np.ones(4), "valid")
    ttm_c = np.convolve(cost, np.ones(4), "valid")
    lab = q["季度"].values[3:]
    margin = (ttm_r - ttm_c) / ttm_r * 100
    g = (ttm_r[4:] / ttm_r[:-4] - 1) * 100
    return pd.DataFrame({"季度": lab[4:], "TTM营收": ttm_r[4:],
                         "TTM同比增速%": g, "TTM核心经营利润率%": margin[4:]})


def empirical_params(ttm: pd.DataFrame, last_n: int | None = None) -> dict:
    d = ttm.tail(last_n) if last_n else ttm
    g, m = d["TTM同比增速%"].values, d["TTM核心经营利润率%"].values
    return {"观测数": len(d), "区间": f"{d['季度'].iloc[0]} 至 {d['季度'].iloc[-1]}",
            "增速均值%": float(g.mean()), "增速标准差": float(g.std(ddof=1)),
            "利润率均值%": float(m.mean()), "利润率标准差": float(m.std(ddof=1)),
            "相关系数": float(np.corrcoef(g, m)[0, 1]) if len(d) > 2 else 0.0}


def ttm_series(ttm: pd.DataFrame) -> pd.DataFrame:
    """滚动 TTM 观测，统一成 期间 / 增速% / 利润率% 三列。"""
    return pd.DataFrame({"期间": ttm["季度"].values, "增速%": ttm["TTM同比增速%"].values,
                         "利润率%": ttm["TTM核心经营利润率%"].values})


def annual_series(al: pd.DataFrame) -> pd.DataFrame:
    """年度观测：营业总收入同比与核心经营利润率，相邻观测不重叠。"""
    rev, cost = al["营业总收入"].astype(float), al["营业总成本"].astype(float)
    df = pd.DataFrame({"期间": [f"{y}A" for y in al.index], "增速%": (rev.pct_change() * 100).values,
                       "利润率%": ((rev - cost) / rev * 100).values})
    return df.dropna().reset_index(drop=True)


def series_params(obs: pd.DataFrame, last_n: int | None = None) -> dict:
    """由观测序列估计增速、利润率的标准差与相关系数（键名与 empirical_params 一致）。"""
    d = obs.tail(last_n) if last_n else obs
    g, m = d["增速%"].values.astype(float), d["利润率%"].values.astype(float)
    return {"观测数": len(d), "区间": f"{d['期间'].iloc[0]} – {d['期间'].iloc[-1]}",
            "增速均值%": float(g.mean()), "增速标准差": float(g.std(ddof=1)),
            "利润率均值%": float(m.mean()), "利润率标准差": float(m.std(ddof=1)),
            "相关系数": float(np.corrcoef(g, m)[0, 1]) if len(d) > 2 else 0.0}


def monte_carlo(rev0: float, a: Assumptions, w: float, nc: float, shares_wan: float,
                sig_g: float, sig_m: float, rho: float, y1_scale: float = 1.0,
                n: int = 20000, seed: int = 20260921, sig_w: float = 0.0, sig_gt: float = 0.0) -> dict:
    """每年独立抽取营收增速与核心经营利润率的冲击，二者按实测相关系数相关。
    第 1 年增速波动按当年已披露季度比例缩小；远期波动逐年放大。
    sig_w / sig_gt > 0 时，折现率与永续增长率也逐次随机抽取（永续增长率至少比折现率低 1 个百分点）。"""
    rng = np.random.default_rng(seed)
    N = a.years
    g0 = np.linspace(a.g_first, a.g_last, N)
    m0 = np.linspace(a.m_first, a.m_last, N)
    sg = sig_g * np.array([y1_scale] + [1.0 + 0.1 * min(i, 1) for i in range(N - 1)])
    sm = sig_m * np.array([1.0] + [min(1.0 + 0.3 * (i + 1), 1.6) for i in range(N - 1)])
    z1 = rng.standard_normal((n, N))
    z2 = rho * z1 + np.sqrt(max(1 - rho ** 2, 0)) * rng.standard_normal((n, N))
    g = np.clip(g0 + sg * z1, -60, 150)
    m = np.clip(m0 + sm * z2, -30, 70)
    other = a.other_first * (1 + a.other_change / 100) ** np.arange(N)
    rev = rev0 * np.cumprod(1 + g / 100, axis=1)
    prev = np.concatenate([np.full((n, 1), rev0), rev[:, :-1]], axis=1)
    core = rev * m / 100
    parent = (core + other) * (1 - a.tax / 100) * (1 - a.minority / 100)
    nopat = (core + other * a.other_in_fcf / 100) * (1 - a.tax / 100)
    fcff = nopat + rev * a.da_pct / 100 - rev * a.capex_pct / 100 - (rev - prev) * a.nwc_pct / 100
    # 折现率与永续增长率的抽样放在最后，保证 sig_w = sig_gt = 0 时结果与只抽经营变量时完全一致
    ww = np.maximum(w + sig_w * rng.standard_normal(n), 2.0) if sig_w > 0 else np.full(n, w)
    gt = a.g_term + sig_gt * rng.standard_normal(n) if sig_gt > 0 else np.full(n, a.g_term)
    gt = np.minimum(gt, ww - 1.0)
    disc = 1 / (1 + ww[:, None] / 100) ** np.arange(1, N + 1)
    tv = fcff[:, -1] * (1 + gt / 100) / (ww / 100 - gt / 100) * disc[:, -1]
    ps = ((fcff * disc).sum(axis=1) + tv + nc) / shares_wan
    return {"第1年归母净利润": parent[:, 0], "第1年核心经营利润率": m[:, 0],
            "每股价值": ps, "增速σ": sg, "利润率σ": sm,
            "抽样": pd.DataFrame({"营收增速": g.mean(axis=1), "核心经营利润率": m.mean(axis=1),
                                "折现率": ww, "永续增长率": gt})}


def uncertainty_share(draws: pd.DataFrame, value: np.ndarray) -> pd.Series:
    """各随机输入对估值不确定性的贡献：秩相关系数平方归一化（常数输入记 0）。"""
    r = pd.Series(value).rank()
    rho = {}
    for c in draws.columns:
        x = draws[c]
        rho[c] = 0.0 if x.std() == 0 else float(np.corrcoef(x.rank(), r)[0, 1])
    rho = pd.Series(rho)
    share = rho ** 2 / (rho ** 2).sum() * 100 if (rho ** 2).sum() > 0 else rho * 0
    return pd.DataFrame({"秩相关系数": rho, "贡献%": share}).sort_values("贡献%", ascending=False)


# ─────────────────────────── 单因素敏感性、反向拆解
def value_of(a: Assumptions, rev0: float, base_year: int, bs: dict, mcap_wan: float,
             shares_wan: float, w: float | None = None) -> float:
    """按一组假设算折现法每股价值；w 给定时直接用该折现率。折现率不高于永续增长率时返回 nan。"""
    w = wacc(a, bs["有息负债"], mcap_wan)["WACC"] if w is None else w
    if w <= a.g_term:
        return float("nan")
    fc = forecast(rev0, base_year, a)
    return dcf(fc, w, a.g_term, net_cash(bs, a)["净现金"], shares_wan)["每股价值"]


def tornado(a: Assumptions, rev0: float, base_year: int, bs: dict, mcap_wan: float, shares_wan: float,
            sig_g: float, sig_m: float, sig_w: float, sig_gt: float) -> pd.DataFrame:
    """每次只动一个假设（上下各一个标准差或给定幅度），看每股价值变化，按影响大小排序。"""
    from dataclasses import replace
    w0 = wacc(a, bs["有息负债"], mcap_wan)["WACC"]
    base = value_of(a, rev0, base_year, bs, mcap_wan, shares_wan, w0)
    cases = [
        ("营收增速（各年）", f"±{sig_g:.1f}pp",
         replace(a, g_first=a.g_first - sig_g, g_last=a.g_last - sig_g), None,
         replace(a, g_first=a.g_first + sig_g, g_last=a.g_last + sig_g), None),
        ("核心经营利润率（各年）", f"±{sig_m:.1f}pp",
         replace(a, m_first=a.m_first - sig_m, m_last=a.m_last - sig_m), None,
         replace(a, m_first=a.m_first + sig_m, m_last=a.m_last + sig_m), None),
        ("折现率", f"±{sig_w:.1f}pp", a, w0 + sig_w, a, max(w0 - sig_w, a.g_term + 0.5)),
        ("永续增长率", f"±{sig_gt:.1f}pp", replace(a, g_term=a.g_term - sig_gt), w0,
         replace(a, g_term=min(a.g_term + sig_gt, w0 - 0.5)), w0),
        ("资本开支 / 营收", "±1.0pp", replace(a, capex_pct=a.capex_pct + 1), w0,
         replace(a, capex_pct=max(a.capex_pct - 1, 0)), w0),
        ("营运资本 / 营收", "±5.0pp", replace(a, nwc_pct=a.nwc_pct + 5), w0,
         replace(a, nwc_pct=max(a.nwc_pct - 5, 0)), w0),
        ("有效税率", "±5.0pp", replace(a, tax=a.tax + 5), w0, replace(a, tax=max(a.tax - 5, 0)), w0),
    ]
    rows = []
    for name, rng_, a_lo, w_lo, a_hi, w_hi in cases:
        lo = value_of(a_lo, rev0, base_year, bs, mcap_wan, shares_wan, w_lo)
        hi = value_of(a_hi, rev0, base_year, bs, mcap_wan, shares_wan, w_hi)
        lo, hi = min(lo, hi), max(lo, hi)
        rows.append({"因素": name, "变动幅度": rng_, "低": lo, "高": hi, "区间": hi - lo})
    out = pd.DataFrame(rows).sort_values("区间", ascending=False).reset_index(drop=True)
    out.attrs["基准"] = base
    return out


def bridge(a: Assumptions, rev0: float, base_year: int, bs: dict, mcap_wan: float,
           shares_wan: float) -> pd.DataFrame:
    """从当前假设出发，逐步放宽到更乐观的假设，看每股价值如何累积变化（反向拆解现价隐含了什么）。"""
    from dataclasses import replace
    steps = [
        ("当前假设", {}),
        ("贝塔调为 1.0（市场平均风险）", {"beta": 1.0}),
        ("去掉规模溢价", {"size_prem": 0.0}),
        ("投资收益全部计入现金流、不再下降", {"other_in_fcf": 100.0, "other_change": 0.0}),
        ("第5年营收增速 +10pp", {"g_last": a.g_last + 10}),
        ("第5年核心经营利润率 +5pp", {"m_last": a.m_last + 5}),
        ("永续增长率 +1pp", {"g_term": a.g_term + 1}),
    ]
    cur, rows = a, []
    for name, ch in steps:
        cur = replace(cur, **ch)
        rows.append({"步骤": name, "折现率%": wacc(cur, bs["有息负债"], mcap_wan)["WACC"],
                     "每股价值": value_of(cur, rev0, base_year, bs, mcap_wan, shares_wan)})
    return pd.DataFrame(rows)


def implied_single(a: Assumptions, rev0: float, base_year: int, bs: dict, mcap_wan: float,
                   shares_wan: float, price: float) -> pd.DataFrame:
    """其他假设不变，单独调整一个参数使折现法等于现价，求该参数需要的取值。"""
    from dataclasses import replace
    w0 = wacc(a, bs["有息负债"], mcap_wan)["WACC"]

    def solve(f, lo, hi):
        flo, fhi = f(lo) - price, f(hi) - price
        if not (np.isfinite(flo) and np.isfinite(fhi)) or flo * fhi > 0:
            return float("nan")
        for _ in range(70):
            mid = (lo + hi) / 2
            fm = f(mid) - price
            if not np.isfinite(fm):
                return float("nan")
            lo, hi, flo = (mid, hi, fm) if fm * flo > 0 else (lo, mid, flo)
        return (lo + hi) / 2

    v = lambda aa, w=None: value_of(aa, rev0, base_year, bs, mcap_wan, shares_wan, w)
    rows = [
        ("折现率（%）", w0, solve(lambda x: v(a, x), a.g_term + 0.05, 60)),
        ("贝塔", a.beta, solve(lambda x: v(replace(a, beta=x)), 0.0, 6.0)),
        ("各年营收增速同时增加（pp）", 0.0, solve(lambda x: v(replace(a, g_first=a.g_first + x, g_last=a.g_last + x)), -30, 150)),
        ("各年核心经营利润率同时增加（pp）", 0.0, solve(lambda x: v(replace(a, m_first=a.m_first + x, m_last=a.m_last + x)), -30, 80)),
        ("永续增长率（%）", a.g_term, solve(lambda x: v(replace(a, g_term=x), w0), -5.0, w0 - 0.05)),
    ]
    return pd.DataFrame(rows, columns=["参数", "当前", "达到现价所需"])


def pct_table(x: np.ndarray, ps=(5, 25, 50, 75, 95)) -> dict:
    return {f"P{p}": float(np.percentile(x, p)) for p in ps}
