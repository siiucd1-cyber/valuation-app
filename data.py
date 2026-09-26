# -*- coding: utf-8 -*-
"""数据层：抓取并整理上市公司财务与行情数据。

数据来源
- 三张报表（单季数据由累计报表相减得到）、个股周线、指数日线、国债收益率：akshare（东方财富 / 新浪公开接口）
- 实时行情：东方财富行情接口

所有金额统一换算为「万元」，每股数据为「元」。
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import warnings

import numpy as np
import pandas as pd
import requests

warnings.filterwarnings("ignore")

UA = {"User-Agent": "Mozilla/5.0"}
QUOTE_URL = "https://push2delay.eastmoney.com/api/qt/stock/get"
_HERE = os.path.dirname(os.path.abspath(__file__))
# 演示快照放在 demo/ 下；若不存在（如经网页上传时子文件夹丢失），退回程序所在目录
DEMO_DIR = os.path.join(_HERE, "demo") if os.path.isdir(os.path.join(_HERE, "demo")) else _HERE
WAN = 1e4


# ─────────────────────────── 基础工具
def retry(fn, tries: int = 3, wait: float = 1.5, timeout: float = 45):
    """东方财富接口对连续请求会限流，失败后退避重试。
    akshare 内部请求不设超时，接口无响应时会一直挂起，所以每次调用放进独立线程并限时。"""
    import time
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FTimeout
    last = None
    for i in range(tries):
        ex = ThreadPoolExecutor(max_workers=1)
        try:
            return ex.submit(fn).result(timeout=timeout)
        except FTimeout:
            last = RuntimeError(f"接口超时（{timeout:.0f} 秒无响应）")
        except Exception as e:  # noqa: BLE001
            last = e
        finally:
            ex.shutdown(wait=False)
        time.sleep(wait * (i + 1))
    raise last

def market_of(code: str) -> tuple[str, str]:
    """返回 (报表前缀, 东财 secid 市场号)"""
    code = code.strip()
    if len(code) != 6 or not code.isdigit():
        raise ValueError("请输入 6 位 A 股代码，例如 688230")
    if code.startswith(("6", "9")):
        return "SH", "1"
    if code.startswith(("0", "2", "3")):
        return "SZ", "0"
    if code.startswith(("4", "8")):
        return "BJ", "0"
    raise ValueError("无法识别的股票代码")


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=df.index)


def _first(df: pd.DataFrame, *cols: str) -> pd.Series:
    """按顺序取第一个存在且非全零的列"""
    for c in cols:
        if c in df.columns:
            s = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
            if s.abs().sum() > 0:
                return s
    return pd.Series(0.0, index=df.index)


def _qlabel(d: pd.Timestamp) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


# ─────────────────────────── 单项抓取
def fetch_quote(code: str) -> dict:
    _, mkt = market_of(code)
    p = {"secid": f"{mkt}.{code}", "fltt": 2, "invt": 2,
         "fields": "f43,f57,f58,f84,f116,f127,f167,f170"}
    j = retry(lambda: requests.get(QUOTE_URL, params=p, headers=UA, timeout=10).json()["data"])
    if not j or j.get("f58") in (None, "-"):
        raise RuntimeError("行情接口未返回该代码的数据")
    return {"code": j["f57"], "name": j["f58"], "price": float(j["f43"]),
            "shares": float(j["f84"]), "mcap_yi": float(j["f116"]) / 1e8,
            "industry": j.get("f127") or "", "pb": float(j["f167"]),
            "chg_pct": float(j["f170"]),
            "ts": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


def fetch_statements(code: str) -> dict[str, pd.DataFrame]:
    import akshare as ak
    pre, _ = market_of(code)
    sym = f"{pre}{code}"
    out = {
        "pl": retry(lambda: ak.stock_profit_sheet_by_report_em(symbol=sym)),
        "bs": retry(lambda: ak.stock_balance_sheet_by_report_em(symbol=sym)),
        "cf": retry(lambda: ak.stock_cash_flow_sheet_by_report_em(symbol=sym)),
    }
    for k, df in out.items():
        df["REPORT_DATE"] = pd.to_datetime(df["REPORT_DATE"])
    return out


def fetch_prices(code: str, years: int = 3) -> pd.Series:
    import akshare as ak
    start = (dt.date.today() - dt.timedelta(days=365 * years)).strftime("%Y%m%d")
    try:
        df = retry(lambda: ak.stock_zh_a_hist(symbol=code, period="daily",
                                              start_date=start, adjust="qfq"), tries=2)
        return df.assign(d=pd.to_datetime(df["日期"])).set_index("d")["收盘"].astype(float)
    except Exception:
        pre, _ = market_of(code)
        df = retry(lambda: ak.stock_zh_a_daily(symbol=f"{pre.lower()}{code}", adjust="qfq"))
        s = df.assign(d=pd.to_datetime(df["date"])).set_index("d")["close"].astype(float)
        return s[s.index >= pd.Timestamp(start)]


def fetch_index() -> pd.Series:
    import akshare as ak
    df = retry(lambda: ak.stock_zh_index_daily(symbol="sh000300"))
    return df.assign(d=pd.to_datetime(df["date"])).set_index("d")["close"].astype(float)


def fetch_rf() -> float:
    import akshare as ak
    start = (dt.date.today() - dt.timedelta(days=45)).strftime("%Y%m%d")
    df = retry(lambda: ak.bond_zh_us_rate(start_date=start))
    s = pd.to_numeric(df["中国国债收益率10年"], errors="coerce").dropna()
    return float(s.iloc[-1])


# ─────────────────────────── 整理
def build_annual(st: dict[str, pd.DataFrame], n_years: int = 6) -> pd.DataFrame:
    pl, bs, cf = st["pl"], st["bs"], st["cf"]
    pa = pl[pl["REPORT_TYPE"].astype(str).str.contains("年报")].copy()
    pa = pa.sort_values("REPORT_DATE").tail(n_years)
    out = pd.DataFrame(index=pa["REPORT_DATE"].dt.year.values)
    out.index.name = "年度"
    g = lambda c: _num(pa, c).values / WAN
    out["营业总收入"] = g("TOTAL_OPERATE_INCOME")
    out["营业收入"] = _first(pa, "OPERATE_INCOME", "TOTAL_OPERATE_INCOME").values / WAN
    out["营业成本"] = g("OPERATE_COST")
    out["营业总成本"] = g("TOTAL_OPERATE_COST")
    out["研发费用"] = g("RESEARCH_EXPENSE")
    out["营业利润"] = g("OPERATE_PROFIT")
    out["利润总额"] = g("TOTAL_PROFIT")
    out["所得税"] = g("INCOME_TAX")
    out["净利润"] = g("NETPROFIT")
    out["归母净利润"] = g("PARENT_NETPROFIT")
    out["扣非归母净利润"] = g("DEDUCT_PARENT_NETPROFIT")

    def at_year_end(df: pd.DataFrame, cols: dict) -> pd.DataFrame:
        d = df[df["REPORT_DATE"].dt.month == 12].copy()
        d["年度"] = d["REPORT_DATE"].dt.year
        d = d.drop_duplicates("年度").set_index("年度")
        res = pd.DataFrame(index=d.index)
        for name, src in cols.items():
            srcs = src if isinstance(src, (list, tuple)) else [src]
            res[name] = _first(d, *srcs).values / WAN
        return res

    b = at_year_end(bs, {
        "货币资金": "MONETARYFUNDS",
        "交易性金融资产": ["TRADE_FINASSET_NOTFVTPL", "TRADE_FINASSET"],
        "资产总计": "TOTAL_ASSETS", "归母权益": "TOTAL_PARENT_EQUITY",
        "固定资产": "FIXED_ASSET", "应收账款": "ACCOUNTS_RECE", "存货": "INVENTORY",
        "应付账款": "ACCOUNTS_PAYABLE",
        "短期借款": "SHORT_LOAN", "长期借款": "LONG_LOAN", "应付债券": "BOND_PAYABLE",
        "一年内到期非流动负债": "NONCURRENT_LIAB_1YEAR",
    })
    b["有息负债"] = b[["短期借款", "长期借款", "应付债券", "一年内到期非流动负债"]].sum(axis=1)
    c = at_year_end(cf, {
        "经营现金流": "NETCASH_OPERATE", "资本开支": "CONSTRUCT_LONG_ASSET",
        "固定资产折旧": "FA_IR_DEPR", "无形资产摊销": "IA_AMORTIZE",
        "长期待摊摊销": "LPE_AMORTIZE", "使用权资产摊销": "USERIGHT_ASSET_AMORTIZE",
    })
    c["折旧摊销"] = c[["固定资产折旧", "无形资产摊销", "长期待摊摊销", "使用权资产摊销"]].sum(axis=1)
    out = out.join(b, how="left").join(c[["经营现金流", "资本开支", "折旧摊销"]], how="left").fillna(0.0)
    return derive(out)


def derive(out: pd.DataFrame) -> pd.DataFrame:
    """由原始报表科目（万元）计算衍生指标。在线数据与 PDF 解析共用。"""
    out = out.copy()
    out["营收增速%"] = out["营业总收入"].pct_change(fill_method=None) * 100
    out["毛利率%"] = (out["营业收入"] - out["营业成本"]) / out["营业收入"] * 100
    out["核心经营利润"] = out["营业总收入"] - out["营业总成本"]
    out["核心经营利润率%"] = out["核心经营利润"] / out["营业总收入"] * 100
    out["投资收益及其他"] = out["利润总额"] - out["核心经营利润"]
    out["有效税率%"] = np.where(out["利润总额"] != 0, out["所得税"] / out["利润总额"] * 100, 0)
    out["少数股东占比%"] = np.where(out["净利润"] != 0,
                              (1 - out["归母净利润"] / out["净利润"]) * 100, 0)
    out["非经常性损益"] = out["归母净利润"] - out["扣非归母净利润"]
    out["研发费用率%"] = out["研发费用"] / out["营业总收入"] * 100
    out["折旧摊销/营收%"] = out["折旧摊销"] / out["营业总收入"] * 100
    out["资本开支/营收%"] = out["资本开支"] / out["营业总收入"] * 100
    out["营运资本"] = out["应收账款"] + out["存货"] - out["应付账款"]
    out["营运资本/营收%"] = out["营运资本"] / out["营业总收入"] * 100
    out["金融资产占总资产%"] = (out["货币资金"] + out["交易性金融资产"]) / out["资产总计"] * 100
    return out


def build_annual_long(st: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """全部年报的营业总收入与营业总成本，用于按年度同比估计波动率。"""
    pl = st["pl"]
    pa = pl[pl["REPORT_TYPE"].astype(str).str.contains("年报")].sort_values("REPORT_DATE")
    out = pd.DataFrame({"营业总收入": _num(pa, "TOTAL_OPERATE_INCOME").values / WAN,
                        "营业总成本": _num(pa, "TOTAL_OPERATE_COST").values / WAN},
                       index=pa["REPORT_DATE"].dt.year.values)
    out.index.name = "年度"
    return out[~out.index.duplicated(keep="last")]


def build_latest_bs(st: dict[str, pd.DataFrame]) -> dict:
    bs = st["bs"].sort_values("REPORT_DATE")
    r = bs.tail(1)
    f = lambda *c: float(_first(r, *c).iloc[0]) / WAN
    debt = sum(f(c) for c in ["SHORT_LOAN", "LONG_LOAN", "BOND_PAYABLE", "NONCURRENT_LIAB_1YEAR"])
    return {"报告期": r["REPORT_DATE"].iloc[0].strftime("%Y-%m-%d"),
            "货币资金": f("MONETARYFUNDS"),
            "交易性金融资产": f("TRADE_FINASSET_NOTFVTPL", "TRADE_FINASSET"),
            "有息负债": debt, "资产总计": f("TOTAL_ASSETS"),
            "归母权益": f("TOTAL_PARENT_EQUITY")}


def build_quarterly(st: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """由累计报表（一季报、中报、三季报、年报）逐季相减得到单季数据。
    与东方财富单季利润表逐项一致，但少请求一个接口（该接口偶尔无响应）。"""
    p = st["pl"].sort_values("REPORT_DATE").drop_duplicates("REPORT_DATE", keep="last")
    p = p[p["REPORT_DATE"].dt.month.isin([3, 6, 9, 12])].reset_index(drop=True)
    yr, mo = p["REPORT_DATE"].dt.year.values, p["REPORT_DATE"].dt.month.values
    cols = {"营业总收入": "TOTAL_OPERATE_INCOME", "营业总成本": "TOTAL_OPERATE_COST",
            "归母净利润": "PARENT_NETPROFIT"}
    df = pd.DataFrame({"季度": p["REPORT_DATE"].map(_qlabel).values, "日期": p["REPORT_DATE"].values})
    for name, col in cols.items():
        cum = _num(p, col).values / WAN
        single = np.full(len(cum), np.nan)
        for i in range(len(cum)):
            if mo[i] == 3:
                single[i] = cum[i]
            else:
                prev = np.where((yr == yr[i]) & (mo == mo[i] - 3))[0]
                if len(prev):
                    single[i] = cum[i] - cum[prev[0]]
        df[name] = single
    df = df.dropna().reset_index(drop=True)
    # 只保留最近一段连续季度
    d = pd.to_datetime(df["日期"])
    months = d.dt.year * 12 + d.dt.month
    gap = months.diff().fillna(3) != 3
    start = gap[gap].index.max() if gap.any() else df.index.min()
    return df.loc[start:].reset_index(drop=True)


def build_interim(st: dict[str, pd.DataFrame], last_annual: int) -> dict | None:
    pl = st["pl"].sort_values("REPORT_DATE")
    latest = pl.iloc[-1]
    d = latest["REPORT_DATE"]
    if d.year <= last_annual:
        return None
    prev = pl[pl["REPORT_DATE"] == d - pd.DateOffset(years=1)]
    rev = float(latest["TOTAL_OPERATE_INCOME"]) / WAN
    out = {"年度": int(d.year), "季度数": int(d.month // 3), "报告": str(latest["REPORT_TYPE"]),
           "累计营收": rev, "累计归母": float(latest["PARENT_NETPROFIT"]) / WAN,
           "累计扣非": float(latest.get("DEDUCT_PARENT_NETPROFIT", 0) or 0) / WAN,
           "累计营业总成本": float(latest.get("TOTAL_OPERATE_COST", 0) or 0) / WAN,
           "累计利润总额": float(latest.get("TOTAL_PROFIT", 0) or 0) / WAN}
    out["累计投资收益及其他"] = out["累计利润总额"] - (rev - out["累计营业总成本"])
    if not prev.empty:
        pr = float(prev["TOTAL_OPERATE_INCOME"].iloc[0]) / WAN
        pn = float(prev["PARENT_NETPROFIT"].iloc[0]) / WAN
        out["营收同比%"] = (rev / pr - 1) * 100 if pr else None
        out["归母同比%"] = (out["累计归母"] / pn - 1) * 100 if pn else None
    return out


def weekly_beta(px: pd.Series, ix: pd.Series, weeks: int = 100) -> tuple[float, float, int]:
    a = px.resample("W-FRI").last().pct_change()
    b = ix.resample("W-FRI").last().pct_change()
    j = pd.concat([a, b], axis=1, join="inner").dropna().tail(weeks)
    if len(j) < 30:
        raise RuntimeError("周线样本不足 30 周")
    cov = np.cov(j.iloc[:, 0], j.iloc[:, 1])
    beta = cov[0, 1] / cov[1, 1]
    r2 = cov[0, 1] ** 2 / (cov[0, 0] * cov[1, 1])
    return float(beta), float(r2), len(j)


# ─────────────────────────── 总入口
def load_market(code: str) -> dict:
    """只取市场数据：实时行情、日线、贝塔、10 年国债。任何一项失败都记录在 status 中。"""
    status: dict[str, str] = {}
    m: dict = {}
    try:
        m["quote"] = fetch_quote(code); status["实时行情"] = "ok"
    except Exception as e:  # noqa: BLE001
        status["实时行情"] = f"失败：{e}"; m["quote"] = None
    try:
        m["prices"] = fetch_prices(code); status["个股行情"] = "ok"
    except Exception as e:  # noqa: BLE001
        m["prices"] = None; status["个股行情"] = f"失败：{e}"
    try:
        ix = fetch_index(); status["沪深300"] = "ok"
    except Exception as e:  # noqa: BLE001
        ix = None; status["沪深300"] = f"失败：{e}"
    m["beta"] = None
    if m["prices"] is not None and ix is not None:
        try:
            b, r2, n = weekly_beta(m["prices"], ix)
            m["beta"] = {"beta": b, "r2": r2, "weeks": n}; status["贝塔"] = "ok"
        except Exception as e:  # noqa: BLE001
            status["贝塔"] = f"失败：{e}"
    try:
        m["rf"] = fetch_rf(); status["10年国债"] = "ok"
    except Exception as e:  # noqa: BLE001
        m["rf"] = None; status["10年国债"] = f"失败：{e}"
    m["status"] = status
    return m


def load_company(code: str) -> dict:
    """抓取全部数据。任何一项失败都不会中断，失败项记录在 status 中。"""
    try:
        st = fetch_statements(code)
    except Exception as e:
        raise RuntimeError(f"财务报表抓取失败，无法继续：{e}")
    m = load_market(code)
    cd: dict = {"code": code, "quote": m["quote"], "prices": m["prices"], "beta": m["beta"], "rf": m["rf"]}
    status = {"三张报表": "ok", **m["status"]}

    cd["annual"] = build_annual(st)
    cd["annual_long"] = build_annual_long(st)
    cd["bs_latest"] = build_latest_bs(st)
    cd["quarterly"] = build_quarterly(st)
    cd["interim"] = build_interim(st, int(cd["annual"].index.max()))

    # 若行情失败，用报表兜底
    if cd["quote"] is None:
        shares = float(_num(st["bs"].sort_values("REPORT_DATE").tail(1), "SHARE_CAPITAL").iloc[0])
        price = float(cd["prices"].iloc[-1]) if cd["prices"] is not None else float("nan")
        cd["quote"] = {"code": code, "name": code, "price": price, "shares": shares,
                       "mcap_yi": price * shares / 1e8, "industry": "", "pb": float("nan"),
                       "chg_pct": 0.0}
    cd["status"] = status
    cd["asof"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    return cd


# ─────────────────────────── 演示快照（离线可用）
def save_snapshot(cd: dict, path: str) -> None:
    def ser(v):
        if isinstance(v, pd.DataFrame):
            return {"__df__": v.reset_index().to_json(orient="split", date_format="iso",
                                                    force_ascii=False),
                    "index": v.index.name, "attrs": v.attrs}
        if isinstance(v, pd.Series):
            return {"__s__": v.to_json(orient="split", date_format="iso")}
        return v
    json.dump({k: ser(v) for k, v in cd.items()}, open(path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)


def load_snapshot(path: str) -> dict:
    raw = json.load(open(path, encoding="utf-8"))
    out = {}
    for k, v in raw.items():
        if isinstance(v, dict) and "__df__" in v:
            df = pd.read_json(io.StringIO(v["__df__"]), orient="split")
            if v.get("index") and v["index"] in df.columns:
                df = df.set_index(v["index"])
            elif "index" in df.columns:
                df = df.set_index("index")
            df.attrs = v.get("attrs") or {}
            out[k] = df
        elif isinstance(v, dict) and "__s__" in v:
            s = pd.read_json(io.StringIO(v["__s__"]), orient="split", typ="series")
            s.index = pd.to_datetime(s.index)
            out[k] = s
        else:
            out[k] = v
    return out


def demo_codes() -> list[str]:
    if not os.path.isdir(DEMO_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(DEMO_DIR) if f.endswith(".json") and f[:-5].isdigit())
