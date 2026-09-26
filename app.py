# -*- coding: utf-8 -*-
"""估值工作台 Valuation Workbench —— 输入 A 股代码，自动拉取财务数据，用折现法、市盈率法与蒙特卡洛模拟做估值。

运行：streamlit run app.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data
import export
import model as M
from i18n import T, TL, is_en, tr_msg

st.set_page_config(page_title="估值工作台 · Valuation Workbench", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
  .block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1400px;}
  [data-testid="stMetricValue"] {font-size: 1.55rem;}
  [data-testid="stMetricLabel"] p {font-size: 0.85rem; color: #555;}
  .note {font-size: 0.82rem; color: #666; line-height: 1.6;}
  .formula {font-family: ui-monospace, Menlo, monospace; font-size: 0.86rem;
            background: #f6f6f6; padding: 0.6rem 0.8rem; border-radius: 4px; line-height: 1.8;}
  .hdr-px {font-size: 1.05rem; font-weight: 600; margin-left: 0.6rem;}
  .hdr-sub {font-size: 0.9rem; color: #777;}
  h3 {margin-top: 0.6rem;}
</style>
""", unsafe_allow_html=True)

GREY, DARK, LIGHT = "#8c8c8c", "#262626", "#d9d9d9"
LAYOUT = dict(template="simple_white", height=320, margin=dict(l=10, r=10, t=40, b=10),
              font=dict(size=12), legend=dict(orientation="h", y=-0.2))
# 分位线标注：P5 在线左、P95 在线右，避免分布较窄时文字重叠（具体数值见下方表格）
PCT_LINES = (("P5", "dot", "top left"), ("P50", "solid", "top"), ("P95", "dot", "top right"))
ON_CLOUD = os.getcwd().startswith("/mount/src")  # Streamlit Community Cloud 默认打开演示数据


# ─────────────────────────── 数据加载
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_live(code: str) -> dict:
    return data.load_company(code)


@st.cache_data(ttl=30, show_spinner=False)
def live_quote(code: str) -> dict:
    return data.fetch_quote(code)


def fetch_demo(code: str) -> dict:
    return data.load_snapshot(os.path.join(data.DEMO_DIR, f"{code}.json"))


def fmt(x, d=2):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x:,.{d}f}"


def tr_index(df: pd.DataFrame, cols: bool = False) -> pd.DataFrame:
    df = df.copy()
    df.index = TL(df.index)
    if cols:
        df.columns = TL(df.columns)
    return df


# ─────────────────────────── 由数据推出默认假设
def defaults_from(cd: dict) -> M.Assumptions:
    a = cd["annual"]
    L = a.iloc[-1]
    last3 = a.tail(3)
    ttm = M.rolling_ttm(cd["quarterly"])
    it = cd.get("interim")

    if it and it.get("营收同比%") is not None:
        g1 = it["营收同比%"]
    elif not ttm.empty:
        g1 = ttm["TTM同比增速%"].iloc[-1]
    else:
        g1 = L["营收增速%"]
    g1 = float(np.clip(g1, -30, 60))
    m1 = float(ttm["TTM核心经营利润率%"].iloc[-1]) if not ttm.empty else float(L["核心经营利润率%"])
    if it and "累计投资收益及其他" in it and it["季度数"]:
        other1 = it["累计投资收益及其他"] * 4 / it["季度数"]
    else:
        other1 = float(L["投资收益及其他"])
    da = float(np.clip(last3["折旧摊销/营收%"].median(), 0, 20))
    capex = float(max(last3["资本开支/营收%"].median(), da))
    nwc = float(np.clip(last3["营运资本/营收%"].median(), 0, 60))
    mcap = cd["quote"]["mcap_yi"]
    pe = np.nan
    if cd.get("comps") is not None and len(cd["comps"]):
        pe = M.comps_stats(cd["comps"])["中位数"]
    return M.Assumptions(
        g_first=round(g1, 1), g_last=round(float(np.clip(g1 * 0.4, 3, 10)), 1),
        m_first=round(m1, 1), m_last=round(m1, 1),
        other_first=round(float(other1), 0), other_change=-15.0, other_in_fcf=0.0,
        tax=round(float(np.clip(L["有效税率%"], 0, 30)), 2),
        minority=round(float(np.clip(L["少数股东占比%"], 0, 60)), 2),
        da_pct=round(da, 2), capex_pct=round(capex, 2), nwc_pct=round(nwc, 2),
        rf=round(cd["rf"], 2) if cd.get("rf") else 1.7,
        beta=round(cd["beta"]["beta"], 2) if cd.get("beta") else 1.2,
        erp=5.5, size_prem=1.0 if mcap < 100 else (0.5 if mcap < 300 else 0.0),
        kd=3.5, g_term=2.5, add_cash=True, add_fin=True,
        target_pe=round(float(pe), 1) if pe == pe else 30.0,
    )


FIELDS = list(M.Assumptions().to_dict().keys())


def reset_state(a: M.Assumptions):
    for k, v in a.to_dict().items():
        st.session_state[f"a_{k}"] = v


def current_assumptions() -> M.Assumptions:
    return M.Assumptions(**{k: st.session_state[f"a_{k}"] for k in FIELDS
                            if f"a_{k}" in st.session_state})


# ─────────────────────────── 侧边栏：语言与公司选择
with st.sidebar:
    st.radio("Language", ["中文", "English"], horizontal=True, key="lang",
             label_visibility="collapsed")
    st.markdown("## " + T("估值工作台"))
    st.caption(T("输入 A 股代码，自动拉取财报；左侧所有假设可调，结果即时重算。"))
    mode = st.radio(T("数据来源"), ["live", "demo"], index=1 if ON_CLOUD else 0, horizontal=True,
                    key="mode", format_func=lambda m: T("实时数据") if m == "live" else T("演示数据（离线）"),
                    help=T("演示数据是预存的快照，无网络也能打开；实时数据从东方财富、新浪公开接口获取。"))
    with st.form("pick"):
        code_in = st.text_input(T("股票代码"), value=st.session_state.get("code", "688230"), max_chars=6)
        go_btn = st.form_submit_button(T("加载"), width="stretch")
    if mode == "demo" and data.demo_codes():
        st.caption(T("可用演示代码：") + "、".join(data.demo_codes()))

code = code_in.strip()
key = f"{mode}|{code}"
if go_btn or "cd" not in st.session_state or st.session_state.get("key") != key:
    try:
        if mode == "demo":
            cd = fetch_demo(code)
        else:
            with st.spinner(T("正在从东方财富、新浪拉取数据（首次约 30–60 秒，之后一小时内有缓存）……")):
                cd = fetch_live(code)
    except Exception as e:  # noqa: BLE001
        if os.path.exists(os.path.join(data.DEMO_DIR, f"{code}.json")):
            st.warning(T("实时数据获取失败，已改用演示快照。原因：{e}", e=tr_msg(str(e))))
            cd = fetch_demo(code)
        else:
            st.error(T("数据获取失败：{e}", e=tr_msg(str(e))))
            st.stop()
    st.session_state.update(cd=cd, key=key, code=code)
    reset_state(defaults_from(cd))

cd = st.session_state["cd"]
an, bs = cd["annual"], cd["bs_latest"]
q = dict(cd["quote"])
q_live = False
if mode == "live":
    try:
        q.update(live_quote(code)); q_live = True
    except Exception:  # noqa: BLE001  行情刷新失败时沿用加载时的报价
        pass
base_year = int(an.index.max())
rev0 = float(an.loc[base_year, "营业总收入"])
shares_wan = q["shares"] / 1e4
mcap_wan = q["mcap_yi"] * 1e4
dflt = defaults_from(cd)
# 滑块上限随数据放宽（如高毛利公司核心经营利润率可超过 60%）
m_hi = float(max(60.0, np.ceil((max(dflt.m_first, dflt.m_last) + 15) / 5) * 5))
cx_hi = float(max(30.0, np.ceil((dflt.capex_pct + 10) / 5) * 5))

# ─────────────────────────── 侧边栏：假设
with st.sidebar:
    if st.button(T("恢复数据默认值"), width="stretch"):
        reset_state(dflt); st.rerun()

    with st.expander(T("收入与利润"), expanded=True):
        st.slider(T("第1年营收增速（%）"), -30.0, 80.0, key="a_g_first", step=0.5,
                  help=T("默认值：{v}%，取最新一期累计营收同比或滚动 TTM 增速", v=dflt.g_first))
        st.slider(T("第5年营收增速（%）"), -10.0, 40.0, key="a_g_last", step=0.5,
                  help=T("中间年份按线性插值"))
        st.slider(T("第1年核心经营利润率（%）"), -10.0, m_hi, key="a_m_first", step=0.1,
                  help=T("默认值：{v}%，取最新滚动 TTM；定义为（营业总收入−营业总成本）÷ 营业总收入",
                         v=dflt.m_first))
        st.slider(T("第5年核心经营利润率（%）"), -10.0, m_hi, key="a_m_last", step=0.1)
        st.number_input(T("第1年投资收益及其他（万元）"), key="a_other_first", step=100.0,
                        help=T("= 利润总额 − 核心经营利润，含理财收益、政府补助、公允价值变动等"))
        st.slider(T("投资收益及其他年变化（%）"), -50.0, 50.0, key="a_other_change", step=1.0)
        st.slider(T("其中计入经营现金流的比例（%）"), 0.0, 100.0, key="a_other_in_fcf", step=5.0,
                  help=T("默认 0：折现法只对核心主业定价，金融资产在净现金中加回。若补助、退税属经常性，可调高"))
        st.slider(T("有效税率（%）"), 0.0, 30.0, key="a_tax", step=0.1)

    with st.expander(T("资本开支与营运资金")):
        st.slider(T("折旧摊销 / 营收（%）"), 0.0, 20.0, key="a_da_pct", step=0.1)
        st.slider(T("资本开支 / 营收（%）"), 0.0, cx_hi, key="a_capex_pct", step=0.1,
                  help=T("默认取近三年中位数与折旧率的较大者，即长期至少覆盖折旧"))
        st.slider(T("营运资金增加 / 营收增量（%）"), 0.0, 60.0, key="a_nwc_pct", step=0.5)

    with st.expander(T("折现率")):
        st.number_input(T("无风险利率（%）"), key="a_rf", step=0.05, format="%.2f",
                        help=T("默认取最新 10 年期国债收益率"))
        bt = cd.get("beta") or {}
        st.number_input(T("贝塔"), key="a_beta", step=0.05, format="%.2f",
                        help=T("默认由最近 100 周个股与沪深300周收益率回归计算") + (T(
                            "：原始值 {raw:.2f}（R² {r2:.2f}），Blume 调整后 {adj:.2f}（= 0.67 × 原始 + 0.33）",
                            raw=bt["beta"], r2=bt["r2"], adj=0.67 * bt["beta"] + 0.33) if bt else ""))
        st.number_input(T("市场风险溢价（%）"), key="a_erp", step=0.25, format="%.2f")
        st.number_input(T("规模溢价（%）"), key="a_size_prem", step=0.25, format="%.2f")
        st.number_input(T("税前债务成本（%）"), key="a_kd", step=0.25, format="%.2f")
        st.number_input(T("永续增长率（%）"), key="a_g_term", step=0.25, format="%.2f")
        st.checkbox(T("货币资金计入净现金"), key="a_add_cash")
        st.checkbox(T("交易性金融资产计入净现金"), key="a_add_fin")

    with st.expander(T("市盈率法")):
        st.number_input(T("目标市盈率（倍）"), key="a_target_pe", step=1.0, format="%.1f",
                        help=T("默认取可比公司市盈率(TTM)中位数：{v} 倍", v=dflt.target_pe))

A = current_assumptions()

# ─────────────────────────── 计算
wc = M.wacc(A, bs["有息负债"], mcap_wan)
W = wc["WACC"]
fc = M.forecast(rev0, base_year, A)
ncd = M.net_cash(bs, A)
try:
    D = M.dcf(fc, W, A.g_term, ncd["净现金"], shares_wan)
    sens = M.sensitivity(fc, ncd["净现金"], shares_wan, W, A.g_term)
except ValueError as e:
    st.error(tr_msg(str(e))); st.stop()
P = M.pe_valuation(fc, shares_wan, A.target_pe)
ttm = M.rolling_ttm(cd["quarterly"])
it = cd.get("interim")
y1_scale = (4 - it["季度数"]) / 4 if it else 1.0
ttm_np = float(cd["quarterly"]["归母净利润"].tail(4).sum())
pe_ttm = mcap_wan / ttm_np if ttm_np > 0 else np.nan
px = cd.get("prices")
hi52 = lo52 = np.nan
if px is not None and len(px):
    last = px[px.index >= px.index[-1] - pd.Timedelta(days=365)]
    hi52, lo52 = float(last.max()), float(last.min())
comps_med = M.comps_stats(cd["comps"])["中位数"] if cd.get("comps") is not None and len(cd["comps"]) else np.nan

# ─────────────────────────── 页眉
chg = q.get("chg_pct", 0) or 0
chg_color = ("#c00000" if chg > 0 else "#008000" if chg < 0 else "#555") if not is_en() else \
            ("#008000" if chg > 0 else "#c00000" if chg < 0 else "#555")
src_txt = T("演示快照") if mode == "demo" else T("实时")
st.markdown(
    f"### {q['name']}（{q['code']}）"
    f"<span class='hdr-px'>{fmt(q['price'])}</span>"
    f"<span class='hdr-px' style='color:{chg_color}'>{chg:+.2f}%</span>　"
    f"<span class='hdr-sub'>{T(q.get('industry', ''))}　·　{T('数据时间')} {cd.get('asof', '')}　·　{src_txt}</span>",
    unsafe_allow_html=True)

tabs = st.tabs(TL(["首页", "历史财务", "盈利预测与折现法", "市盈率法", "蒙特卡洛模拟", "导出 Excel"]))

# ═══════════════ 蒙特卡洛（首页要用，先算）
with tabs[4]:
    with st.expander(T("蒙特卡洛在做什么？"), expanded=False):
        st.markdown(T("MC_EXPLAIN"))

    obs_ttm = M.ttm_series(ttm) if not ttm.empty else pd.DataFrame()
    al = cd.get("annual_long")
    if al is None or len(al) < len(an):
        al = an[["营业总收入", "营业总成本"]]
    obs_ann = M.annual_series(al)

    st.markdown("#### " + T("分布参数"))
    methods = []
    if len(obs_ttm) >= 6:
        methods.append("ttm")
    if len(obs_ann) >= 4:
        methods.append("annual")
    methods.append("manual")
    default_m = "annual" if len(obs_ann) >= 10 else methods[0]
    labels = {"ttm": T("单季滚动 TTM"), "annual": T("年度同比"), "manual": T("手动输入")}
    c1, c2 = st.columns([2, 1])
    src = c1.radio(T("参数来源"), methods, index=methods.index(default_m), horizontal=True,
                   key="mc_src", format_func=lambda m: labels[m],
                   help=T("MC_SRC_HELP"))
    sims = c2.select_slider(T("模拟次数"), [5000, 10000, 20000, 50000], 20000, key="mc_sims")

    # 两种实测口径并排，方便比较
    cmp_rows = []
    for m_, o_ in (("ttm", obs_ttm), ("annual", obs_ann)):
        if len(o_) >= 3:
            e_ = M.series_params(o_)
            cmp_rows.append({T("口径"): labels[m_], T("观测数"): e_["观测数"], T("区间"): e_["区间"],
                             T("增速σ"): round(e_["增速标准差"], 2), T("利润率σ"): round(e_["利润率标准差"], 2),
                             T("相关系数"): round(e_["相关系数"], 3),
                             T("等效独立样本"): round(e_["观测数"] / 4, 1) if m_ == "ttm" else e_["观测数"]})
    if cmp_rows:
        st.dataframe(pd.DataFrame(cmp_rows), hide_index=True, width="stretch")
        st.markdown(f"<div class='note'>{T('MC_CMP_NOTE')}</div>", unsafe_allow_html=True)

    obs = None
    if src == "manual":
        base_e = M.series_params(obs_ttm) if len(obs_ttm) >= 3 else \
            {"增速标准差": 10.0, "利润率标准差": 2.0, "相关系数": 0.3}
        k = st.columns(3)
        sg_ = k[0].number_input(T("营收增速标准差（pp）"), 0.0, 100.0, round(base_e["增速标准差"], 2), 0.5)
        sm_ = k[1].number_input(T("核心经营利润率标准差（pp）"), 0.0, 30.0, round(base_e["利润率标准差"], 2), 0.1)
        rho_ = k[2].number_input(T("相关系数"), -1.0, 1.0, round(base_e["相关系数"], 3), 0.05)
        emp = {"增速标准差": sg_, "利润率标准差": sm_, "相关系数": rho_, "观测数": 0,
               "区间": T("手动输入")}
    else:
        obs_all = obs_ttm if src == "ttm" else obs_ann
        n_all = len(obs_all)
        lo_n = min(6 if src == "ttm" else 4, n_all)
        n_obs = st.slider(T("使用最近 N 个观测"), lo_n, n_all, n_all, key=f"mc_n_{src}",
                          help=T("相关系数对样本窗口敏感，可拖动观察变化")) if n_all > lo_n else n_all
        emp = M.series_params(obs_all, n_obs)
        obs = obs_all.tail(n_obs)
    emp["方法"] = labels[src]

    MC = M.monte_carlo(rev0, A, W, ncd["净现金"], shares_wan, emp["增速标准差"],
                       emp["利润率标准差"], emp["相关系数"], y1_scale, n=sims)
    ps_pct = M.pct_table(MC["每股价值"])
    np_pct = M.pct_table(MC["第1年归母净利润"])

    k = st.columns(4)
    k[0].metric(T("观测数"), T("{n} 个", n=emp["观测数"]) if emp["观测数"] else "—")
    k[0].caption(emp["区间"])
    k[1].metric(T("营收增速标准差"), f"{emp['增速标准差']:.2f} pp")
    k[2].metric(T("核心经营利润率标准差"), f"{emp['利润率标准差']:.2f} pp")
    k[3].metric(T("两者相关系数"), f"{emp['相关系数']:+.3f}")

    if obs is not None and len(obs) > 2:
        rows = []
        steps = [n_ for n_ in (4, 6, 8, 10, 12, 14, 16, 20, 25) if n_ < len(obs_all)] + [len(obs_all)]
        for n_ in sorted(set(steps)):
            if n_ >= 3:
                e_ = M.series_params(obs_all, n_)
                rows.append({T("最近观测数"): n_, T("区间"): e_["区间"], T("增速σ"): round(e_["增速标准差"], 2),
                             T("利润率σ"): round(e_["利润率标准差"], 2), T("相关系数"): round(e_["相关系数"], 3)})
        with st.expander(T("相关系数随样本窗口的变化（稳健性检查）")):
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            st.markdown(f"<div class='note'>{T('若相关系数随窗口大幅变化甚至变号，说明两者关系不稳定，解读模拟结果时应更谨慎。')}</div>",
                        unsafe_allow_html=True)

        g1, g2 = st.columns(2)
        f1 = go.Figure()
        f1.add_trace(go.Scatter(x=obs["期间"], y=obs["增速%"], mode="lines+markers",
                                line=dict(color=DARK), name=T("营收同比")))
        f1.add_hline(y=emp.get("增速均值%", 0), line_dash="dash", line_color=GREY)
        f1.update_layout(**LAYOUT, title=T("营收同比增速（%）") + f" · {labels[src]}")
        g1.plotly_chart(f1, width="stretch")
        f2 = go.Figure()
        f2.add_trace(go.Scatter(x=obs["增速%"], y=obs["利润率%"], mode="markers",
                                marker=dict(color=DARK, size=8), text=obs["期间"], name=T("观测")))
        k_, b_ = np.polyfit(obs["增速%"].astype(float), obs["利润率%"].astype(float), 1)
        xs = np.linspace(obs["增速%"].min(), obs["增速%"].max(), 20)
        f2.add_trace(go.Scatter(x=xs, y=k_ * xs + b_, mode="lines", line=dict(color=GREY),
                                name=f"ρ = {emp['相关系数']:+.3f}"))
        f2.update_layout(**{**LAYOUT, "legend": dict(orientation="h", y=1.0, x=1, xanchor="right")},
                         title=T("营收增速与核心经营利润率"),
                         xaxis_title=T("营收同比（%）"), yaxis_title=T("核心经营利润率（%）"))
        g2.plotly_chart(f2, width="stretch")

    st.markdown("#### " + T("模拟设定"))
    st.markdown(
        "<div class='note'>" + T(
            "每年独立抽取营收增速与核心经营利润率的冲击，二者相关系数取上方参数。均值取左侧假设，标准差取上方参数；"
            "第1年已披露 {nq} 个季度，增速波动按剩余 {rest:.0%} 缩小；远期波动逐年放大。"
            "各年增速σ：{sg}；利润率σ：{sm}（单位：个百分点）。",
            nq=it["季度数"] if it else 0, rest=y1_scale,
            sg=", ".join(f"{x:.1f}" for x in MC["增速σ"]),
            sm=", ".join(f"{x:.2f}" for x in MC["利润率σ"])) + "</div>",
        unsafe_allow_html=True)

    h1, h2 = st.columns(2)
    f3 = go.Figure(go.Histogram(x=MC["第1年归母净利润"] / 1e4, nbinsx=70, marker_color=LIGHT,
                                marker_line=dict(color=GREY, width=0.3)))
    for p_, dash, pos in PCT_LINES:
        f3.add_vline(x=np_pct[p_] / 1e4, line_dash=dash, line_color=DARK,
                     annotation_text=p_, annotation_position=pos)
    f3.add_vline(x=an.loc[base_year, "归母净利润"] / 1e4, line_dash="dash", line_color=GREY,
                 annotation_text=T("{y}年实际", y=base_year), annotation_position="bottom right")
    f3.update_layout(**LAYOUT, title=T("{y}年归母净利润分布（亿元）", y=base_year + 1), showlegend=False)
    h1.plotly_chart(f3, width="stretch")
    f4 = go.Figure(go.Histogram(x=MC["每股价值"], nbinsx=70, marker_color=LIGHT,
                                marker_line=dict(color=GREY, width=0.3)))
    for p_, dash, pos in PCT_LINES:
        f4.add_vline(x=ps_pct[p_], line_dash=dash, line_color=DARK,
                     annotation_text=p_, annotation_position=pos)
    f4.add_vline(x=q["price"], line_dash="dash", line_color=GREY,
                 annotation_text=T("现价 {p:.2f}", p=q["price"]), annotation_position="bottom right")
    f4.update_layout(**LAYOUT, title=T("折现法每股价值分布（元）"), showlegend=False)
    h2.plotly_chart(f4, width="stretch")
    tbl = pd.DataFrame({
        T("指标"): [T("{y}年归母净利润（万元）", y=base_year + 1), T("折现法每股价值（元）")],
        **{k: [fmt(np_pct[k]), fmt(ps_pct[k])] for k in ps_pct}})
    st.dataframe(tbl, hide_index=True, width="stretch")
    st.markdown("<div class='note'>" + T(
        "{y1}年归母净利润低于{y0}年实际值的概率：{a:.1%}；每股价值高于现价的概率：{b:.1%}。",
        y1=base_year + 1, y0=base_year,
        a=(MC["第1年归母净利润"] < an.loc[base_year, "归母净利润"]).mean(),
        b=(MC["每股价值"] > q["price"]).mean()) + "</div>", unsafe_allow_html=True)

# ═══════════════ 首页 Dashboard
with tabs[0]:
    top = st.columns([6, 1])
    if mode == "live":
        top[0].caption(T("行情获取时间：{t}（每 30 秒可刷新）", t=q.get("ts") or cd.get("asof", ""))
                       if q_live else T("实时行情刷新失败，显示加载时的报价"))
        if top[1].button(T("刷新行情"), width="stretch"):
            live_quote.clear(); st.rerun()
    else:
        top[0].caption(T("演示快照，行情截至 {t}", t=cd.get("asof", "")))

    up = lambda v: T("{p:+.1%} vs 现价", p=v / q["price"] - 1)
    k = st.columns(5)
    k[0].metric(T("现价（元）"), fmt(q["price"]), f"{chg:+.2f}%",
                delta_color="normal" if is_en() else "inverse", border=True)
    k[1].metric(T("总市值（亿元）"), fmt(q["mcap_yi"]), border=True)
    k[2].metric(T("折现法（元/股）"), fmt(D["每股价值"]), up(D["每股价值"]), delta_color="off", border=True)
    k[3].metric(T("市盈率法（元/股）"), fmt(P["每股价值"]), up(P["每股价值"]), delta_color="off", border=True)
    k[4].metric(T("蒙特卡洛中位数（元/股）"), fmt(ps_pct["P50"]), border=True)
    k[4].caption(f"P5–P95  {ps_pct['P5']:.1f} – {ps_pct['P95']:.1f}")

    left, right = st.columns([2, 1])
    with left:
        fp = go.Figure()
        if px is not None and len(px):
            p1 = px[px.index >= px.index[-1] - pd.Timedelta(days=365)]
            fp.add_trace(go.Scatter(x=p1.index, y=p1.values, mode="lines", line=dict(color=DARK, width=1.6),
                                    name=T("收盘价"), hovertemplate="%{x|%Y-%m-%d}  %{y:.2f}<extra></extra>"))
            x0, x1 = p1.index[0], p1.index[-1]
            fp.add_shape(type="rect", x0=x0, x1=x1, y0=ps_pct["P5"], y1=ps_pct["P95"],
                         fillcolor=LIGHT, opacity=0.45, line_width=0, layer="below")
            for v_, lab_, dash_ in ((D["每股价值"], T("折现法"), "dash"),
                                    (P["每股价值"], T("市盈率法"), "dot")):
                fp.add_hline(y=v_, line_dash=dash_, line_color=GREY,
                             annotation_text=f"{lab_} {v_:.2f}", annotation_position="top left")
            fp.add_annotation(x=x1, y=ps_pct["P95"], text=T("蒙特卡洛 P5–P95"), showarrow=False,
                              xanchor="right", yanchor="bottom", font=dict(size=11, color=GREY))
        fp.update_layout(**{**LAYOUT, "height": 360}, title=T("近一年股价与估值"), showlegend=False,
                         yaxis_title=T("元/股"))
        st.plotly_chart(fp, width="stretch")
    with right:
        st.markdown("#### " + T("关键指标"))
        kv = [(T("市盈率 TTM"), f"{fmt(pe_ttm, 1)}x"),
              (T("可比公司市盈率中位数"), f"{fmt(comps_med, 1)}x"),
              (T("市净率"), f"{fmt(q.get('pb'), 2)}x"),
              (T("52周区间（元）"), f"{fmt(lo52)} – {fmt(hi52)}"),
              (T("贝塔（100周）"), fmt(cd["beta"]["beta"]) if cd.get("beta") else "—"),
              (T("10年国债"), f"{cd['rf']:.2f}%" if cd.get("rf") else "—"),
              (T("折现率 WACC"), f"{W:.2f}%"),
              (T("永续增长率"), f"{A.g_term:.2f}%"),
              (T("终值占企业价值"), f"{D['终值占比%']:.1f}%"),
              (T("每股净现金（元）"), fmt(ncd["净现金"] / shares_wan)),
              (T("目标市盈率"), f"{A.target_pe:.1f}x")]
        st.dataframe(pd.DataFrame(kv, columns=[T("指标"), T("数值")]), hide_index=True,
                     width="stretch", height=36 * (len(kv) + 1) + 3)

    l2, r2 = st.columns(2)
    with l2:
        bars = []
        if hi52 == hi52:
            bars.append((T("52周股价区间"), lo52, hi52))
        bars += [(T("折现法敏感性区间"), float(np.nanmin(sens.values)), float(np.nanmax(sens.values))),
                 (T("蒙特卡洛 P5–P95"), ps_pct["P5"], ps_pct["P95"]),
                 (T("市盈率法（目标倍数±20%）"), float(P["网格"]["对应每股（元）"].min()),
                  float(P["网格"]["对应每股（元）"].max()))]
        ff = go.Figure()
        for i, (lab, lo, hi) in enumerate(bars):
            ff.add_trace(go.Bar(y=[lab], x=[hi - lo], base=[lo], orientation="h",
                                marker_color=LIGHT if i else GREY, marker_line=dict(color=DARK, width=0.8),
                                text=f"{lo:.1f} – {hi:.1f}", textposition="outside", showlegend=False,
                                hovertemplate=f"{lab}: {lo:.2f} – {hi:.2f}<extra></extra>"))
        ff.add_vline(x=q["price"], line_dash="dash", line_color=DARK,
                     annotation_text=T("现价 {p:.2f}", p=q["price"]), annotation_position="top")
        ff.update_layout(**{**LAYOUT, "height": 330}, title=T("估值区间汇总（元/股）"),
                         xaxis_title=T("元/股"), yaxis=dict(autorange="reversed"),
                         xaxis=dict(range=[min([b[1] for b in bars] + [q["price"]]) * 0.85,
                                           max([b[2] for b in bars] + [q["price"]]) * 1.32]))
        st.plotly_chart(ff, width="stretch")
    with r2:
        hist_y = [f"{y}A" for y in an.index[-4:]]
        fc_y = [str(y) for y in fc["年份"]]
        fr = go.Figure()
        fr.add_trace(go.Bar(x=hist_y + fc_y, y=list(an["营业总收入"].iloc[-4:] / 1e4) + list(fc["营业总收入"] / 1e4),
                            marker_color=[GREY] * len(hist_y) + [LIGHT] * len(fc_y),
                            marker_line=dict(color=DARK, width=0.5), name=T("营业总收入（亿元）")))
        fr.add_trace(go.Scatter(x=hist_y + fc_y,
                                y=list(an["归母净利润"].iloc[-4:] / 1e4) + list(fc["归母净利润"] / 1e4),
                                mode="lines+markers", line=dict(color=DARK), name=T("归母净利润（亿元）")))
        fr.update_layout(**{**LAYOUT, "height": 330}, title=T("营收与利润：历史与预测（亿元）"))
        st.plotly_chart(fr, width="stretch")

    st.markdown("#### " + T("结果说明"))
    st.markdown(T(
        "- **折现法**：折现率 {w:.2f}%（股权成本 {ke:.2f}%，贝塔 {b:.2f}），永续增长率 {g:.2f}%，"
        "得到每股 {v:.2f} 元；终值占企业价值 {tv:.1f}%。其中净现金贡献 {nc:.2f} 元/股，占每股价值的 {ncp:.0%}。\n"
        "- **市盈率法**：{y}年预测归母净利润 {np_:.2f} 亿元、每股收益 {eps:.2f} 元，给予 {pe:.1f} 倍，得到每股 {pv:.2f} 元。\n"
        "- **蒙特卡洛**：{n:,} 次模拟（参数来源：{src}），折现法每股价值中位数 {p50:.2f} 元，"
        "90% 的结果落在 {p5:.2f}–{p95:.2f} 元。",
        w=W, ke=wc["股权成本"], b=A.beta, g=A.g_term, v=D["每股价值"], tv=D["终值占比%"],
        nc=ncd["净现金"] / shares_wan, ncp=ncd["净现金"] / shares_wan / D["每股价值"],
        y=base_year + 1, np_=P["预测归母净利润"] / 1e4, npm=P["预测归母净利润"] / 100, eps=P["预测每股收益"], pe=A.target_pe,
        pv=P["每股价值"], n=sims, src=emp["方法"], p50=ps_pct["P50"], p5=ps_pct["P5"], p95=ps_pct["P95"]))
    if W - A.g_term < 4:
        st.warning(T("折现率 {w:.2f}% 与永续增长率 {g:.2f}% 只差 {d:.2f} 个百分点，终值被大幅放大，折现法结果不可靠。",
                     w=W, g=A.g_term, d=W - A.g_term))
    elif D["终值占比%"] > 75:
        st.warning(T("终值占企业价值 {v:.0f}%，估值高度依赖永续假设，结果稳健性有限。", v=D["终值占比%"]))
    bt = cd.get("beta") or {}
    if bt and bt.get("r2", 1) < 0.1:
        st.warning(T("贝塔回归的 R² 仅 {r2:.2f}，个股与大盘几乎不相关，回归贝塔 {b:.2f} 统计上不可靠。"
                     "可在左侧「折现率」中改用 Blume 调整后贝塔 {adj:.2f} 或行业贝塔。",
                     r2=bt["r2"], b=bt["beta"], adj=0.67 * bt["beta"] + 0.33))
    st.markdown(f"<div class='note'>{T('所有结果基于左侧假设，调整任一参数即时重算。数据来自东方财富、新浪公开接口，仅供学习研究，不构成投资建议。')}</div>",
                unsafe_allow_html=True)
    with st.expander(T("数据获取状态")):
        st.dataframe(pd.DataFrame({T("数据项"): TL(cd["status"].keys()),
                                   T("状态"): [tr_msg(v) for v in cd["status"].values()]}),
                     hide_index=True, width="stretch")

# ═══════════════ 历史财务
with tabs[1]:
    show = ["营业总收入", "营收增速%", "毛利率%", "核心经营利润", "核心经营利润率%", "投资收益及其他",
            "利润总额", "有效税率%", "归母净利润", "扣非归母净利润", "非经常性损益", "研发费用率%",
            "经营现金流", "货币资金", "交易性金融资产", "有息负债", "金融资产占总资产%"]
    t = tr_index(an[show].T.astype(float))
    t.columns = [f"{c}A" for c in t.columns]
    st.markdown("#### " + T("主要财务数据（万元 / %）"))
    st.dataframe(t.style.format(lambda v: fmt(v), na_rep="—"), width="stretch", height=36 * (len(t) + 1) + 3)

    rc = M.regression_check(an.loc[base_year])
    st.markdown("#### " + T("模型结构回归检验"))
    st.markdown("<div class='formula'>" + T(
        "{y} 年：营业总收入 {rev} × 核心经营利润率 {m:.2f}% = 核心经营利润 {core}<br>"
        "核心经营利润 + 投资收益及其他 {oth} = 利润总额 {pt}<br>"
        "利润总额 × (1 − 有效税率 {tax:.2f}%) × (1 − 少数股东 {mi:.2f}%) = 归母净利润 {np_}<br>"
        "披露值 {dis}，偏差 <b>{dev:+.2f} 万元</b>",
        y=base_year, rev=fmt(an.loc[base_year, "营业总收入"]), m=an.loc[base_year, "核心经营利润率%"],
        core=fmt(rc["核心经营利润"]), oth=fmt(an.loc[base_year, "投资收益及其他"]), pt=fmt(rc["利润总额"]),
        tax=an.loc[base_year, "有效税率%"], mi=an.loc[base_year, "少数股东占比%"], np_=fmt(rc["模型归母"]),
        dis=fmt(rc["披露归母"]), dev=rc["偏差"]) + "</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='note'>{T('预测模型沿用同一结构，保证与披露科目一一对应、不设轧差项。')}</div>",
                unsafe_allow_html=True)

    x = [f"{y}A" for y in an.index]
    r1, r2 = st.columns(2)
    fa = go.Figure()
    fa.add_trace(go.Bar(x=x, y=an["营业总收入"] / 1e4, marker_color=LIGHT,
                        marker_line=dict(color=GREY, width=0.6), name=T("营业总收入（亿元）")))
    fa.add_trace(go.Scatter(x=x, y=an["营收增速%"], yaxis="y2", mode="lines+markers",
                            line=dict(color=DARK), name=T("同比（%，右轴）")))
    fa.update_layout(**LAYOUT, title=T("营业总收入与增速"), yaxis2=dict(overlaying="y", side="right"))
    r1.plotly_chart(fa, width="stretch")
    fb = go.Figure()
    fb.add_trace(go.Scatter(x=x, y=an["毛利率%"], mode="lines+markers", line=dict(color=GREY),
                            name=T("毛利率")))
    fb.add_trace(go.Scatter(x=x, y=an["核心经营利润率%"], mode="lines+markers",
                            line=dict(color=DARK), name=T("核心经营利润率")))
    fb.update_layout(**LAYOUT, title=T("利润率（%）"))
    r2.plotly_chart(fb, width="stretch")
    r3, r4 = st.columns(2)
    fc_ = go.Figure()
    fc_.add_trace(go.Bar(x=x, y=an["扣非归母净利润"] / 1e4, marker_color=DARK, name=T("扣非归母净利润")))
    fc_.add_trace(go.Bar(x=x, y=an["非经常性损益"] / 1e4, marker_color=LIGHT,
                         marker_line=dict(color=GREY, width=0.6), name=T("非经常性损益")))
    fc_.update_layout(**LAYOUT, barmode="relative", title=T("归母净利润构成（亿元）"))
    r3.plotly_chart(fc_, width="stretch")
    fd = go.Figure()
    fd.add_trace(go.Bar(x=x, y=an["交易性金融资产"] / 1e4, marker_color=LIGHT,
                        marker_line=dict(color=GREY, width=0.6), name=T("交易性金融资产")))
    fd.add_trace(go.Bar(x=x, y=an["货币资金"] / 1e4, marker_color=GREY, name=T("货币资金")))
    fd.add_trace(go.Bar(x=x, y=(an["资产总计"] - an["交易性金融资产"] - an["货币资金"]) / 1e4,
                        marker_color=DARK, name=T("其他资产")))
    fd.update_layout(**LAYOUT, barmode="stack", title=T("资产结构（亿元）"))
    r4.plotly_chart(fd, width="stretch")

    st.markdown("#### " + T("杜邦拆解"))
    du = M.dupont(an)
    du.index = [f"{i}A" for i in du.index]
    st.dataframe(tr_index(du.T.astype(float)).style.format(lambda v: fmt(v, 2), na_rep="—"), width="stretch")
    st.markdown(f"<div class='note'>{T('DUPONT_NOTE')}</div>", unsafe_allow_html=True)

# ═══════════════ 盈利预测与折现法
with tabs[2]:
    l, r = st.columns([1, 1])
    with l:
        st.markdown("#### " + T("折现率"))
        st.dataframe(pd.DataFrame({
            T("项目"): TL(["无风险利率", "贝塔", "市场风险溢价", "规模溢价", "股权成本",
                         "税后债务成本", "债务权重", "折现率 WACC"]),
            T("数值"): [f"{A.rf:.2f}%", f"{A.beta:.2f}", f"{A.erp:.2f}%", f"{A.size_prem:.2f}%",
                      f"{wc['股权成本']:.2f}%", f"{wc['税后债务成本']:.2f}%", f"{wc['债务权重']:.2f}%",
                      f"{W:.2f}%"],
            T("说明"): TL(["10年期国债", "100周回归" if cd.get("beta") else "手动", "", "",
                         "Rf + β×ERP + 规模溢价", "Kd × (1 − 税率)", "有息负债 ÷（有息负债 + 市值）", ""])}),
            hide_index=True, width="stretch")
    with r:
        st.markdown("#### " + T("估值桥"))
        st.markdown("<div class='formula'>" + T(
            "预测期现值合计　{pv}<br>"
            "终值 = {f} × (1 + {g:.2f}%) ÷ ({w:.2f}% − {g:.2f}%) = {tv}<br>"
            "终值现值 = {tv} × {df:.4f} = {tpv}<br>"
            "企业价值 = {ev}　（终值占比 {tvp:.1f}%）<br>"
            "＋ 货币资金 {cash}　＋ 交易性金融资产 {fin}　− 有息负债 {debt}<br>"
            "股权价值 = {eq}　÷ 总股本 {sh} 万股<br>"
            "<b>每股价值 = {ps:.2f} 元</b>",
            pv=fmt(D["预测期现值合计"]), f=fmt(fc["FCFF"].iloc[-1]), g=A.g_term, w=W, tv=fmt(D["终值"]),
            df=D["折现因子"][-1], tpv=fmt(D["终值现值"]), ev=fmt(D["企业价值"]), tvp=D["终值占比%"],
            cash=fmt(ncd["货币资金"]), fin=fmt(ncd["交易性金融资产"]), debt=fmt(ncd["有息负债"]),
            eq=fmt(D["股权价值"]), sh=fmt(shares_wan), ps=D["每股价值"]) + "</div>", unsafe_allow_html=True)
        st.caption(T("金额单位：万元；净现金取 {d} 资产负债表", d=bs["报告期"]))

    st.markdown("#### " + T("盈利预测与自由现金流（万元）"))
    ft = fc.set_index("年份").T
    base_col = pd.Series({
        "营收增速%": an.loc[base_year, "营收增速%"], "营业总收入": rev0,
        "核心经营利润率%": an.loc[base_year, "核心经营利润率%"],
        "核心经营利润": an.loc[base_year, "核心经营利润"],
        "投资收益及其他": an.loc[base_year, "投资收益及其他"],
        "利润总额": an.loc[base_year, "利润总额"], "归母净利润": an.loc[base_year, "归母净利润"]})
    ft.insert(0, f"{base_year}A", base_col)
    ft.loc["折现因子"] = [np.nan] + list(D["折现因子"])
    ft.loc["现值"] = [np.nan] + list(D["现值"])
    ft = tr_index(ft.astype(float))
    st.dataframe(ft.style.format(lambda v: fmt(v, 4) if abs(v) < 1.5 and v != 0 else fmt(v), na_rep="—"),
                 width="stretch", height=36 * (len(ft) + 1) + 3)
    st.markdown(f"<div class='note'>{T('FCFF_NOTE')}</div>", unsafe_allow_html=True)

    st.markdown("#### " + T("敏感性：每股价值（元）"))
    base_r, base_c = f"{W:.2f}%", f"{A.g_term:.1f}%"
    sens_show = sens.copy()
    sens_show.index.name = T("折现率 \\ 永续增长率")
    st.dataframe(sens_show.style.format("{:.2f}", na_rep="—").apply(
        lambda s: ["background-color:#e6e6e6;font-weight:600" if (s.name == base_r and c_ == base_c)
                   else "" for c_ in s.index], axis=1), width="stretch")

# ═══════════════ 市盈率法
with tabs[3]:
    st.markdown("#### " + T("可比公司"))
    st.caption(T("来源：{s}。勾选「纳入」决定是否参与统计；市盈率(TTM) 不在 0–200 倍区间的样本自动剔除。",
                 s=tr_msg(cd.get("peer_source") or "手动输入")))
    comps = cd.get("comps")
    if mode == "live":
        codes_txt = st.text_input(T("可比公司代码（逗号分隔，可增删后点刷新）"),
                                  value=",".join(cd.get("peers") or []), key="peer_codes")
        if st.button(T("刷新可比公司")):
            try:
                comps = data.fetch_peer_quotes([c_.strip() for c_ in codes_txt.split(",")])
                cd["comps"], cd["peers"] = comps, [c_.strip() for c_ in codes_txt.split(",")]
                cd["peer_source"] = "手动输入"
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(T("获取失败：{e}", e=tr_msg(str(e))))
    if comps is not None and len(comps):
        ed = comps.copy()
        ed.insert(0, "纳入", True)
        ed = st.data_editor(ed, hide_index=True, width="stretch", key="comps_editor",
                            disabled=[c_ for c_ in ed.columns if c_ != "纳入"],
                            column_config={c_: st.column_config.Column(T(c_)) for c_ in ed.columns} |
                            {"总市值(亿元)": st.column_config.NumberColumn(T("总市值(亿元)"), format="%.1f")})
        stats = M.comps_stats(ed[ed["纳入"]])
        s1, s2, s3 = st.columns(3)
        s1.metric(T("市盈率(TTM) 中位数"), T("{v:.1f} 倍", v=stats["中位数"]))
        s2.metric(T("平均数"), T("{v:.1f} 倍", v=stats["平均数"]))
        s3.metric(T("有效样本"), T("{n} 家", n=stats["有效样本"]))
        s3.caption(T("剔除 {n} 家", n=stats["剔除"]))
        st.markdown("<div class='note'>" + T(
            "本公司市盈率 TTM {pe:.1f} 倍，较可比中位数 {d:+.0%}。目标市盈率在左侧「市盈率法」中设置，默认取中位数。",
            pe=pe_ttm, d=pe_ttm / stats["中位数"] - 1) + "</div>", unsafe_allow_html=True)
    else:
        st.info(T("暂无可比公司数据，请在左侧手动设定目标市盈率。"))

    st.markdown("#### " + T("测算"))
    st.markdown("<div class='formula'>" + T(
        "{y}年预测归母净利润　{np_} 万元<br>"
        "÷ 总股本 {sh} 万股 = 每股收益 {eps:.4f} 元<br>"
        "× 目标市盈率 {pe:.1f} 倍 = <b>每股价值 {v:.2f} 元</b>",
        y=base_year + 1, np_=fmt(P["预测归母净利润"]), sh=fmt(shares_wan), eps=P["预测每股收益"],
        pe=A.target_pe, v=P["每股价值"]) + "</div>", unsafe_allow_html=True)
    g = P["网格"].copy()
    g["较现价"] = g["对应每股（元）"] / q["price"] - 1
    fmts = {"给予市盈率（倍）": "{:.1f}", "对应市值（亿元）": "{:.2f}", "对应每股（元）": "{:.2f}", "较现价": "{:+.1%}"}
    g.columns = TL(g.columns)
    st.dataframe(g.style.format({T(k_): v_ for k_, v_ in fmts.items()}), hide_index=True, width="stretch")

# ═══════════════ 导出
with tabs[5]:
    st.markdown("#### " + T("导出估值模型"))
    st.markdown(T("Excel 中的预测、折现法、敏感性、市盈率法均为**活公式**：蓝色为输入，改动「假设」表任一蓝色单元格，"
                  "全部结果自动重算。蒙特卡洛结果以数值形式附上。当前语言决定 Excel 的语言。"))
    xls = export.build_workbook({**cd, "quote": q}, A, dict(
        wacc=wc, dcf=D, pe=P, mc_ps=ps_pct, mc_np=np_pct, emp=emp, y1_scale=y1_scale, sims=sims,
        mc_sg=MC["增速σ"], mc_sm=MC["利润率σ"]))
    st.download_button(T("下载 Excel 估值模型"), xls,
                       file_name=T("{n}_{c}_估值模型.xlsx", n=q["name"], c=q["code"]),
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width="stretch")
    st.markdown("#### " + T("方法与数据说明"))
    st.markdown(T("METHOD_NOTES"))
