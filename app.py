# -*- coding: utf-8 -*-
"""估值工作台 Valuation Workbench —— 输入 A 股代码，自动拉取财务数据，用折现法与蒙特卡洛模拟做估值。

运行：streamlit run app.py
"""
from __future__ import annotations

import hashlib
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data
import export
import model as M
import pdf_parser
import template
from i18n import T, TL, is_en, tr_msg

st.set_page_config(page_title="估值工作台 · Valuation Workbench", layout="wide",
                   initial_sidebar_state="expanded")

# ─────────────────────────── 主题：按浏览器/系统的深浅色自动配色（深色模式下深灰线条会“消失”）
try:
    DARK_MODE = st.context.theme.type == "dark"
except Exception:  # noqa: BLE001
    DARK_MODE = False
if DARK_MODE:
    GREY, DARK, LIGHT, RED, GREEN = "#a8a8a8", "#ececec", "#5c5c5c", "#ff6b6b", "#4cd28a"
    C = dict(label="#bdbdbd", note="#a9a9a9", box="rgba(255,255,255,0.07)", hi="rgba(255,255,255,0.16)",
             hist="rgba(255,255,255,0.05)", inp="#7fb2ff", ovr="rgba(255,196,0,0.28)", grid="rgba(255,255,255,0.12)",
             inpbg="rgba(127,178,255,0.10)")
else:
    GREY, DARK, LIGHT, RED, GREEN = "#8c8c8c", "#262626", "#d9d9d9", "#c00000", "#008000"
    C = dict(label="#555", note="#666", box="#f6f6f6", hi="#e6e6e6", hist="#f4f4f4", inp="#0b57d0",
             ovr="#fff2b3", grid="#e9e9e9", inpbg="rgba(11,87,208,0.06)")
LAYOUT = dict(template="plotly_dark" if DARK_MODE else "simple_white", height=320,
              margin=dict(l=10, r=10, t=40, b=10), font=dict(size=12), legend=dict(orientation="h", y=-0.2),
              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")

st.markdown(f"""
<style>
  .block-container {{padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1400px;}}
  [data-testid="stMetricValue"] {{font-size: 1.55rem;}}
  [data-testid="stMetricLabel"] p {{font-size: 0.85rem; color: {C['label']};}}
  .note {{font-size: 0.82rem; color: {C['note']}; line-height: 1.6;}}
  .formula {{font-family: ui-monospace, Menlo, monospace; font-size: 0.86rem;
            background: {C['box']}; padding: 0.6rem 0.8rem; border-radius: 4px; line-height: 1.8;}}
  .hdr-px {{font-size: 1.05rem; font-weight: 600; margin-left: 0.6rem;}}
  .hdr-sub {{font-size: 0.9rem; color: {C['note']};}}
  .legend-chip {{display:inline-block; padding:0 0.45rem; border-radius:3px; margin-right:0.6rem; font-size:0.8rem;}}
  .chk-grid {{display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:0.4rem 0.8rem; margin:0.2rem 0 1rem;}}
  .chk {{font-size:0.86rem; padding:0.35rem 0.6rem; border:1px solid {C['grid']}; border-radius:4px;}}
  .chk-d {{display:block; color:{GREY}; font-size:0.78rem; margin-left:1.1rem;}}
  .verdict {{background:{C['box']}; border-left:3px solid {GREY}; padding:0.8rem 1rem; border-radius:4px; line-height:1.9;}}
  h3 {{margin-top: 0.6rem;}}
</style>
""", unsafe_allow_html=True)

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


@st.cache_data(show_spinner=False, max_entries=64)
def parse_pdf(data_: bytes, name: str) -> dict:
    return pdf_parser.parse_report(data_, name)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_market(code: str) -> dict:
    return data.load_market(code)


def fetch_demo(code: str) -> dict:
    return data.load_snapshot(os.path.join(data.DEMO_DIR, f"{code}.json"))


NA = -987654321.123   # 占位：st.dataframe 会把真实空值显示成 "None"，先填占位数再格式化为 "—"（占位数过大时前端会报错）


def na_fmt(f):
    return lambda v: "—" if (v is None or v != v or v == NA) else f(v)


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


def value_hist(v: np.ndarray, pct: dict, price: float, p_above: float, height: int = 330) -> go.Figure:
    f = go.Figure(go.Histogram(x=v, nbinsx=70, marker_color=LIGHT, marker_line=dict(color=GREY, width=0.3)))
    for p_, dash, pos in PCT_LINES:
        f.add_vline(x=pct[p_], line_dash=dash, line_color=DARK, annotation_text=p_, annotation_position=pos)
    f.add_vline(x=price, line_dash="dash", line_color=RED,
                annotation_text=T("现价 {p:.2f}（高于现价概率 {b:.1%}）", p=price, b=p_above),
                annotation_position="top left" if price > pct["P50"] else "top right",
                annotation_font_color=RED)
    lo_, hi_ = np.percentile(v, 0.5), np.percentile(v, 99.5)
    f.update_layout(**{**LAYOUT, "height": height}, title=T("折现法每股价值分布（元）"), showlegend=False,
                    xaxis=dict(range=[min(lo_, price) * 0.9, max(hi_, price) * 1.08]))
    return f


def tornado_fig(tor: pd.DataFrame, height: int = 330) -> go.Figure:
    base = tor.attrs["基准"]
    f = go.Figure()
    lab = [f"{T(r['因素'])}  {r['变动幅度']}" for _, r in tor.iterrows()]
    f.add_trace(go.Bar(y=lab, x=tor["低"] - base, base=base, orientation="h", marker_color=GREY,
                       name=T("不利方向"), hovertemplate="%{y}: %{x:+.2f}<extra></extra>"))
    f.add_trace(go.Bar(y=lab, x=tor["高"] - base, base=base, orientation="h", marker_color=DARK,
                       name=T("有利方向"), hovertemplate="%{y}: %{x:+.2f}<extra></extra>"))
    f.add_vline(x=base, line_color=DARK, line_width=1,
                annotation_text=T("基准 {v:.2f}", v=base), annotation_position="top")
    f.update_layout(**{**LAYOUT, "height": height, "legend": dict(orientation="h", y=-0.15)}, barmode="overlay",
                    title=T("单因素敏感性（元/股）"), yaxis=dict(autorange="reversed"))
    return f


# ─────────────────────────── 由数据推出默认假设
def _fin(x, fallback: float = 0.0) -> float:
    """非有限值（营收为 0 时的除零、缺数据时的空值）换成兜底值，避免滑块报错。"""
    x = float(x) if x is not None else float("nan")
    return x if np.isfinite(x) else fallback


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
    g1 = float(np.clip(_fin(g1), -30, 60))
    m1 = _fin(ttm["TTM核心经营利润率%"].iloc[-1], np.nan) if not ttm.empty else np.nan
    if not np.isfinite(m1):
        m1 = _fin(L["核心经营利润率%"])
    m1 = float(np.clip(m1, -1000, 100))
    if it and "累计投资收益及其他" in it and it["季度数"]:
        other1 = it["累计投资收益及其他"] * 4 / it["季度数"]
    else:
        other1 = float(L["投资收益及其他"])
    fmed = lambda c: _fin(last3[c].replace([np.inf, -np.inf], np.nan).median())
    da = float(np.clip(fmed("折旧摊销/营收%"), 0, 20))
    capex = float(np.clip(max(fmed("资本开支/营收%"), da), 0, 300))
    nwc = float(np.clip(fmed("营运资本/营收%"), 0, 60))
    mcap = cd["quote"]["mcap_yi"]
    stub = (4 - it["季度数"]) / 4 if it and it.get("季度数") else 1.0
    return M.Assumptions(
        g_first=round(g1, 1), g_last=round(float(np.clip(g1 * 0.4, 3, 10)), 1),
        m_first=round(m1, 1), m_last=round(m1, 1),
        other_first=round(_fin(other1), 0), other_change=-15.0, other_in_fcf=0.0,
        tax=round(float(np.clip(_fin(L["有效税率%"], 25.0), 0, 30)), 2),
        minority=round(float(np.clip(_fin(L["少数股东占比%"]), 0, 60)), 2),
        da_pct=round(da, 2), capex_pct=round(capex, 2), nwc_pct=round(nwc, 2), capex_ty=round(da, 2),
        rf=round(cd["rf"], 2) if cd.get("rf") else 1.7,
        beta=round(cd["beta"]["beta"], 2) if cd.get("beta") else 1.2,
        erp=5.5, size_prem=1.0 if mcap < 100 else (0.5 if mcap < 300 else 0.0),
        kd=3.5, g_term=2.5, add_cash=True, add_fin=True, mid_year=True, stub=float(stub),
    )


FIELDS = list(M.Assumptions().to_dict().keys())


def reset_state(a: M.Assumptions):
    for k, v in a.to_dict().items():
        st.session_state[f"a_{k}"] = v
    clear_overrides()


def clear_overrides():
    """清空计算表里逐年假设的手动修改（换公司、恢复默认值时调用）。"""
    st.session_state["ovr"] = {}
    st.session_state["ovr_ver"] = st.session_state.get("ovr_ver", 0) + 1


# 计算表中可逐年修改的假设
DRV_ROWS = [("g", "营收增速（%）"), ("m", "核心经营利润率（%）"), ("other", "投资收益及其他（万元）"),
            ("capex", "资本开支 / 营收（%）"), ("da", "折旧摊销 / 营收（%）")]


def sheet_grid(rows: pd.DataFrame, key: str, hcols: list, fcols: list, meta: dict, height: int | None = None):
    """可直接在格子里修改的报表（AgGrid）。
    rows：行 = 项目（中文原名），列 = 历史列 + 预测列；
    meta[行名] = {"pct": 百分比行, "dec": 小数位, "bold": 加粗, "fedit": 预测列可改时对应的逐年假设名,
                 "hedit": 历史列可改时对应的年报科目（仅上传年报时）}。
    修改通过回调写入 session_state 的 ovr（逐年假设）或 pdf_ovr（年报科目），回调在重算之前执行，整页随即按新值重算。"""
    from st_aggrid import AgGrid, JsCode
    ovr_now = st.session_state.get("ovr", {})
    pdf_now = st.session_state.get("pdf_ovr", {})
    recs = []
    for r_ in rows.index:
        m = meta.get(r_, {})
        fk, hk = m.get("fedit", ""), m.get("hedit", "")
        rec = {"_key": r_, "_lab": T(r_), "_pct": bool(m.get("pct")), "_dec": int(m.get("dec", 2)),
               "_bold": bool(m.get("bold")), "_fedit": fk, "_hedit": hk,
               "_ovr": ",".join(fcols[i] for i in ovr_now.get(fk, {}) if i < len(fcols)) if fk else "",
               "_hovr": ",".join(f"{y}A" for (y, f) in pdf_now if f == hk) if hk else ""}
        for c_ in hcols + fcols:
            v = rows.loc[r_, c_]
            rec[c_] = None if (v is None or v != v) else float(v)
        recs.append(rec)
    df = pd.DataFrame(recs)
    fmt_js = JsCode("""function(p){ if (p.value === null || p.value === undefined || isNaN(p.value)) return '—';
        const v = Number(p.value);
        if (p.data._pct) return v.toFixed(2) + '%';
        return v.toLocaleString('en-US', {minimumFractionDigits: p.data._dec, maximumFractionDigits: p.data._dec}); }""")
    parse_js = JsCode(r"""function(p){ const s = String(p.newValue === null || p.newValue === undefined ? '' : p.newValue)
        .replace(/[,%\s]/g, '');
        if (s === '') return null; const v = Number(s); return isNaN(v) ? p.oldValue : v; }""")
    hist_style = JsCode(f"""function(p){{ const s = {{textAlign: 'right', backgroundColor: '{C["hist"]}'}};
        if (p.data._hedit) {{ s.color = '{C["inp"]}'; s.fontWeight = '600';
            if ((p.data._hovr || '').split(',').includes(p.colDef.field)) s.backgroundColor = '{C["ovr"]}'; }}
        return s; }}""")
    fc_style = JsCode(f"""function(p){{ const s = {{textAlign: 'right'}};
        if (p.data._fedit) {{ s.color = '{C["inp"]}'; s.fontWeight = '600'; s.backgroundColor = '{C["inpbg"]}';
            if ((p.data._ovr || '').split(',').includes(p.colDef.field)) s.backgroundColor = '{C["ovr"]}'; }}
        return s; }}""")
    cols = [{"field": "_lab", "headerName": T("项目"), "pinned": "left", "minWidth": 150, "flex": 1.5}]
    cols += [{"field": c_, "headerName": c_, "valueFormatter": fmt_js, "valueParser": parse_js, "cellStyle": hist_style,
              "editable": JsCode("function(p){ return !!p.data._hedit; }"), "minWidth": 78, "flex": 1}
             for c_ in hcols]
    cols += [{"field": c_, "headerName": c_, "valueFormatter": fmt_js, "valueParser": parse_js, "cellStyle": fc_style,
              "editable": JsCode("function(p){ return !!p.data._fedit; }"), "minWidth": 78, "flex": 1}
             for c_ in fcols]
    cols += [{"field": c_, "hide": True} for c_ in ["_key", "_pct", "_dec", "_bold", "_fedit", "_hedit", "_ovr", "_hovr"]]
    opts = {"columnDefs": cols, "singleClickEdit": True, "stopEditingWhenCellsLoseFocus": True,
            "suppressMovableColumns": True, "rowHeight": 30, "headerHeight": 32,
            "getRowStyle": JsCode("function(p){ return p.data._bold ? {fontWeight: 700} : null; }")}

    def on_edit(resp):
        ev = resp.event_data or {}
        if ev.get("type") != "cellValueChanged":
            return
        row, col = ev.get("data") or {}, (ev.get("colDef") or {}).get("field")
        v = ev.get("newValue")
        try:
            v = None if v is None or v == "" else float(v)
        except (TypeError, ValueError):
            return
        if v is not None and v != v:
            v = None
        if col in fcols and row.get("_fedit"):
            cells = st.session_state.setdefault("ovr", {}).setdefault(row["_fedit"], {})
            i_ = fcols.index(col)
            if v is None:
                cells.pop(i_, None)
            else:
                cells[i_] = v
        elif col in hcols and row.get("_hedit"):
            st.session_state.setdefault("pdf_ovr", {})[(int(col.rstrip("A")), row["_hedit"])] = \
                float("nan") if v is None else v

    # 修改记录变化时换一个 key 让表格重新挂载，保证黄底等样式按最新修改重新计算
    ver = hashlib.md5(repr((sorted((k, sorted(v.items())) for k, v in ovr_now.items()),
                            sorted(pdf_now.items()))).encode()).hexdigest()[:8]
    AgGrid(df, gridOptions=opts, height=height or 32 + 30 * len(df) + 6, allow_unsafe_jscode=True,
           update_on=["cellValueChanged"], key=f"{key}_{ver}", callback=on_edit, server_sync_strategy="server_wins",
           show_toolbar=False, show_search=False, show_download_button=False, theme="streamlit")


def current_assumptions() -> M.Assumptions:
    return M.Assumptions(**{k: st.session_state[f"a_{k}"] for k in FIELDS
                            if f"a_{k}" in st.session_state})


# ─────────────────────────── 侧边栏：语言与公司选择
with st.sidebar:
    st.radio("Language", ["中文", "English"], horizontal=True, key="lang",
             label_visibility="collapsed")
    st.markdown("## " + T("估值工作台"))
    st.caption(T("输入 A 股代码，自动拉取财报；左侧所有假设可调，结果即时重算。"))
    MODES = {"live": "实时数据", "demo": "演示数据（离线）", "pdf": "上传年报 PDF"}
    to_live = st.session_state.pop("_to_live", None)   # 上一轮在演示模式里输入了没有快照的代码 → 改为实时获取
    if to_live:
        st.session_state["mode"] = "live"
    mode = st.radio(T("数据来源"), list(MODES), index=1 if ON_CLOUD else 0, key="mode",
                    format_func=lambda m: T(MODES[m]), help=T("MODE_HELP"))
    if mode == "pdf":
        ups = st.file_uploader(T("上传年度报告 PDF（可多份）"), type="pdf", accept_multiple_files=True,
                               key="pdf_files", help=T("PDF_UP_HELP"))
        use_mkt = st.checkbox(T("识别到股票代码时，获取实时股价与贝塔"), True, key="pdf_mkt")
        price_in = st.number_input(T("每股价格（元，0 = 自动）"), min_value=0.0, value=0.0, step=0.1,
                                   key="pdf_price", help=T("PRICE_HELP"))
        shares_in = st.number_input(T("总股本（万股，0 = 取年报）"), min_value=0.0, value=0.0, step=100.0,
                                    key="pdf_shares", help=T("SHARES_HELP"))
        code_in, go_btn = st.session_state.get("code", ""), False
    else:
        with st.form("pick"):
            code_in = st.text_input(T("股票代码"), value=st.session_state.get("code", "688230") or "688230",
                                    max_chars=6)
            go_btn = st.form_submit_button(T("加载"), width="stretch")
        if mode == "demo" and data.demo_codes():
            st.caption(T("可用演示代码：") + "、".join(data.demo_codes()) + T("；输入其他代码会自动改为实时获取"))

code = str(code_in).strip()
demo_list = data.demo_codes()
if mode == "demo" and demo_list and code not in demo_list:
    if go_btn:      # 演示快照里没有这个代码：切到实时数据去取，而不是报「找不到文件」
        st.session_state.update(code=code, _to_live=code)
        st.rerun()
    code = demo_list[0]
TOP = st.empty()     # 固定占位：进度条、加载提示、回退警告都放这里，避免页签位置变化导致选中的页签被重置
if mode == "pdf":
    if not ups:
        st.markdown("### " + T("上传年报 PDF，自动抽取报表并估值"))
        st.markdown(T("PDF_INTRO"))
        st.stop()
    key = "pdf|" + "|".join(sorted(pdf_parser.file_key(f.getvalue()) for f in ups)) + f"|{use_mkt}"
    if st.session_state.get("key") != key:
        reps = []
        bar = TOP.progress(0.0)
        for i, f in enumerate(ups):
            bar.progress(i / len(ups), text=T("正在解析 {n}（{i}/{k}）……", n=f.name, i=i + 1, k=len(ups)))
            reps.append(parse_pdf(f.getvalue(), f.name))
        TOP.empty()
        bad = [r["文件"] for r in reps if not r.get("年度")]
        reps = sorted([r for r in reps if r.get("年度")], key=lambda r: r["年度"])
        if bad:
            TOP.warning(T("以下文件未识别为年度报告，已跳过：{f}", f="、".join(bad)))
        if not reps:
            st.error(T("没有可用的年度报告。")); st.stop()
        raw, src = pdf_parser.merge_reports(reps)
        code = reps[-1].get("公司代码") or ""
        market = None
        if use_mkt and code:
            with TOP.container(), st.spinner(T("识别到股票代码 {c}，正在获取实时股价与贝塔……", c=code)):
                try:
                    market = fetch_market(code)
                except Exception:  # noqa: BLE001
                    market = None
        st.session_state.update(pdf_reports=reps, pdf_raw=raw, pdf_src=src, pdf_market=market,
                                key=key, code=code)
        st.session_state["pdf_ovr"] = {}
        st.session_state["pdf_ver"] = st.session_state.get("pdf_ver", 0) + 1
        cd = pdf_parser.build_company(raw, reps, market, price_in or None)
        st.session_state["cd"] = cd
        if cd["quote"]["price"] == cd["quote"]["price"]:
            reset_state(defaults_from(cd))
elif go_btn or "cd" not in st.session_state or st.session_state.get("key") != f"{mode}|{code}":
    key = f"{mode}|{code}"
    try:
        if mode == "demo":
            cd = fetch_demo(code)
        else:
            with TOP.container(), st.spinner(T("正在从东方财富、腾讯、新浪拉取数据（首次约 30–60 秒，之后一小时内有缓存）……")):
                cd = fetch_live(code)
    except Exception as e:  # noqa: BLE001
        if os.path.exists(os.path.join(data.DEMO_DIR, f"{code}.json")):
            TOP.warning(T("实时数据获取失败，已改用演示快照。原因：{e}", e=tr_msg(str(e))))
            cd = fetch_demo(code)
        elif isinstance(e, ValueError):     # 代码不合法或公司类型不适用：直接说明原因
            st.warning(tr_msg(str(e)))
            st.stop()
        else:
            st.error(T("数据获取失败：{e}", e=tr_msg(str(e))))
            st.stop()
    st.session_state.update(cd=cd, key=key, code=code)
    reset_state(defaults_from(cd))
    if to_live:
        TOP.info(T("演示数据只有 {d}，已切换到「实时数据」获取 {c}。", d="、".join(demo_list), c=code))

if mode == "pdf":
    # 解析结果可在「计算表」页签修改；修改记录在 pdf_ovr 中，这里先应用，保证整套估值用的是修改后的数据
    reps, raw0 = st.session_state["pdf_reports"], st.session_state["pdf_raw"]
    raw_ed = raw0.apply(pd.to_numeric, errors="coerce").astype(float).copy()
    for (y_, f_), v_ in st.session_state.get("pdf_ovr", {}).items():
        if y_ in raw_ed.index:
            raw_ed.loc[y_, f_] = v_
    if shares_in:
        raw_ed.loc[raw_ed.index.max(), "股本（万股）"] = shares_in
    cd = pdf_parser.build_company(raw_ed, reps, st.session_state.get("pdf_market"), price_in or None)
    if cd["quote"]["price"] != cd["quote"]["price"]:
        st.warning(T("未取得股价：请在左侧填写每股价格（非上市公司可填最近一轮融资价格）后继续。"))
        st.stop()
    if cd["quote"]["shares"] != cd["quote"]["shares"]:
        st.warning(T("年报中未找到股本，无法计算每股价值。请在左侧填写总股本。"))
        st.stop()
    if "a_g_first" not in st.session_state:
        reset_state(defaults_from(cd))
    st.session_state["cd"] = cd

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
if not rev0 > 0:
    st.warning(T("NO_REVENUE", y=base_year)); st.stop()
shares_wan = q["shares"] / 1e4
mcap_wan = q["mcap_yi"] * 1e4
dflt = defaults_from(cd)
# 滑块上限随数据放宽（如高毛利公司核心经营利润率可超过 60%）
m_hi = float(max(60.0, np.ceil((max(dflt.m_first, dflt.m_last) + 15) / 5) * 5))
m_lo = float(max(-1000.0, min(-10.0, np.floor((min(dflt.m_first, dflt.m_last) - 15) / 5) * 5)))
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
        st.slider(T("第1年核心经营利润率（%）"), m_lo, m_hi, key="a_m_first", step=0.1,
                  help=T("默认值：{v}%，取最新滚动 TTM；定义为（营业总收入−营业总成本）÷ 营业总收入",
                         v=dflt.m_first))
        st.slider(T("第5年核心经营利润率（%）"), m_lo, m_hi, key="a_m_last", step=0.1)
        st.number_input(T("第1年投资收益及其他（万元）"), key="a_other_first", step=100.0,
                        help=T("= 利润总额 − 核心经营利润，含理财收益、政府补助、公允价值变动等"))
        st.slider(T("投资收益及其他年变化（%）"), -50.0, 50.0, key="a_other_change", step=1.0)
        st.slider(T("其中计入经营现金流的比例（%）"), 0.0, 100.0, key="a_other_in_fcf", step=5.0,
                  help=T("默认 0：折现法只对核心主业定价，金融资产在净现金中加回。若补助、退税属经常性，可调高"))
        st.slider(T("有效税率（%）"), 0.0, 30.0, key="a_tax", step=0.1)

    with st.expander(T("资本开支与营运资金")):
        st.slider(T("折旧摊销 / 营收（%）"), 0.0, 20.0, key="a_da_pct", step=0.1)
        st.slider(T("第1年资本开支 / 营收（%）"), 0.0, cx_hi, key="a_capex_pct", step=0.1,
                  help=T("默认取近三年中位数与折旧率的较大者，即长期至少覆盖折旧"))
        st.slider(T("第5年及终值年资本开支 / 营收（%）"), 0.0, cx_hi, key="a_capex_ty", step=0.1,
                  help=T("CAPEX_TY_HELP", da=dflt.da_pct))
        st.slider(T("营运资金增加 / 营收增量（%）"), 0.0, 60.0, key="a_nwc_pct", step=0.5)
        st.slider(T("分红率（%）"), 0.0, 100.0, key="a_payout", step=5.0,
                  help=T("只影响计算表中预测资产负债表的净现金与权益，不影响折现法"))

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
        st.checkbox(T("年中折现"), key="a_mid_year", help=T("MID_HELP"))
        st.caption(T("估值基准日 {d}（最新报表日）；第 1 年计入基准日之后 {s:.0%} 的现金流。",
                     d=bs["报告期"], s=st.session_state.get("a_stub", 1.0)))


A = current_assumptions()

# ─────────────────────────── 计算（逐年假设 = 侧栏插值 + 计算表中的手动修改）
wc = M.wacc(A, bs["有息负债"], mcap_wan)
W = wc["WACC"]
OVR = st.session_state.get("ovr", {})
drv = M.drivers(A, OVR)
fc = M.forecast(rev0, base_year, A, drv)
st.session_state["fc_cols"] = list(fc["年份"])
ncd = M.net_cash(bs, A)
try:
    D = M.dcf(fc, W, A.g_term, ncd["净现金"], shares_wan)
    sens = M.sensitivity(fc, ncd["净现金"], shares_wan, W, A.g_term)
    sens_m = M.sensitivity_multiples(fc, ncd["净现金"], shares_wan, W, A.g_term)
except ValueError as e:
    st.error(tr_msg(str(e))); st.stop()
ttm = M.rolling_ttm(cd["quarterly"])
it = cd.get("interim")
y1_scale = (4 - it["季度数"]) / 4 if it else 1.0
ttm_np = float(cd["quarterly"]["归母净利润"].tail(4).sum()) if len(cd["quarterly"]) >= 4 \
    else float(an.loc[base_year, "归母净利润"])            # 无季度数据（如 PDF 模式）时用最近年度
pe_ttm = mcap_wan / ttm_np if ttm_np > 0 else np.nan
px = cd.get("prices")
hi52 = lo52 = np.nan
if px is not None and len(px):
    last = px[px.index >= px.index[-1] - pd.Timedelta(days=365)]
    hi52, lo52 = float(last.max()), float(last.min())
iw = M.implied_wacc(fc, A.g_term, ncd["净现金"], shares_wan, q["price"])
mult = M.implied_multiples(D, fc, an.loc[base_year], base_year, mcap_wan)
ts = M.three_statements(an, fc, A)
TY = D["终值年"]


def model_checks() -> list[tuple[str, str, str]]:
    """模型检查面板：(检查项, 状态 ok / warn / fail, 说明)。"""
    rc_ = M.regression_check(an.loc[base_year])
    tol = max(1.0, abs(rc_["披露归母"]) * 0.005)
    gap = abs(float(ts["资产负债表"].loc["平衡检查", ts["预测列"]].abs().max()))
    out = [
        (T("预测资产负债表平衡"), "ok" if gap < 0.5 else "fail", T("最大差额 {v} 万元", v=fmt(gap))),
        (T("历史利润表勾稽（{y}A）", y=base_year), "ok" if abs(rc_["偏差"]) <= tol else "warn",
         T("模型还原 {m} vs 披露 {d} 万元", m=fmt(rc_["模型归母"]), d=fmt(rc_["披露归母"]))),
        (T("折现率高于永续增长率 3 个百分点以上"), "ok" if W - A.g_term >= 3 else ("warn" if W > A.g_term else "fail"),
         T("相差 {d:.2f} 个百分点", d=W - A.g_term)),
        (T("终值年自由现金流为正"), "ok" if TY["FCFF"] > 0 else "fail", T("{v} 万元", v=fmt(TY["FCFF"]))),
        (T("终值年资本开支不低于折旧摊销"), "ok" if TY["资本开支"] >= TY["折旧摊销"] * 0.999 else "warn",
         T("资本开支 {c} vs 折旧摊销 {d} 万元", c=fmt(TY["资本开支"]), d=fmt(TY["折旧摊销"]))),
        (T("终值占企业价值不超过 85%"), "ok" if D["终值占比%"] <= 85 else "warn", f"{D['终值占比%']:.1f}%"),
    ]
    return out


CHECKS = model_checks()
mx = lambda v: f"{v:.1f}x" if v == v else "n.m."     # 倍数显示；分母不为正时无意义
n_pass = sum(s_ == "ok" for _, s_, _ in CHECKS)
IS_BASE = not OVR and all(abs(float(getattr(A, k_)) - float(getattr(dflt, k_))) < 1e-9
                          for k_ in FIELDS if isinstance(getattr(A, k_), (int, float)))

# ─────────────────────────── 页眉
chg = q.get("chg_pct", 0) or 0
chg_color = (RED if chg > 0 else GREEN if chg < 0 else GREY) if not is_en() else \
            (GREEN if chg > 0 else RED if chg < 0 else GREY)
src_txt = {"demo": T("演示快照"), "live": T("实时"), "pdf": T("年报 PDF")}[mode]
st.markdown(
    f"### {q['name']}（{q['code']}）"
    f"<span class='hdr-px'>{fmt(q['price'])}</span>"
    f"<span class='hdr-px' style='color:{chg_color}'>{chg:+.2f}%</span>　"
    f"<span class='hdr-sub'>{T(q.get('industry', ''))}　·　{T('数据时间')} {cd.get('asof', '')}　·　{src_txt}</span>",
    unsafe_allow_html=True)

tabs = st.tabs(TL(["首页", "计算表", "历史财务", "敏感性分析", "导出 Excel"]))

# ═══════════════ 敏感性分析（蒙特卡洛）——首页要用，先算
with tabs[3]:
    with st.expander(T("蒙特卡洛在做什么？"), expanded=False):
        st.markdown(T("MC_EXPLAIN"))

    obs_ttm = M.ttm_series(ttm) if not ttm.empty else pd.DataFrame()
    al = cd.get("annual_long")
    if al is None or len(al) < len(an):
        al = an[["营业总收入", "营业总成本"]]
    obs_ann = M.annual_series(al)

    # ── 1. 不确定性参数
    st.markdown("#### " + T("不确定性参数"))
    methods = []
    if len(obs_ttm) >= 6:
        methods.append("ttm")
    if len(obs_ann) >= 4:
        methods.append("annual")
    methods.append("manual")
    default_m = "annual" if len(obs_ann) >= 10 else methods[0]
    labels = {"ttm": T("单季滚动 TTM"), "annual": T("年度同比"), "manual": T("手动输入")}
    c1, c2 = st.columns([2, 1])
    src = c1.radio(T("经营变量的参数来源"), methods, index=methods.index(default_m), horizontal=True,
                   key="mc_src", format_func=lambda m: labels[m], help=T("MC_SRC_HELP"))
    sims = c2.select_slider(T("模拟次数"), [5000, 10000, 20000, 50000], 20000, key="mc_sims")

    obs, obs_all = None, None
    if src == "manual":
        base_e = M.series_params(obs_ttm) if len(obs_ttm) >= 3 else \
            {"增速标准差": 10.0, "利润率标准差": 2.0, "相关系数": 0.3}
        k = st.columns(3)
        sg_ = k[0].number_input(T("营收增速标准差（pp）"), 0.0, 100.0, round(base_e["增速标准差"], 2), 0.5)
        sm_ = k[1].number_input(T("核心经营利润率标准差（pp）"), 0.0, 30.0, round(base_e["利润率标准差"], 2), 0.1)
        rho_ = k[2].number_input(T("相关系数"), -1.0, 1.0, round(base_e["相关系数"], 3), 0.05)
        emp = {"增速标准差": sg_, "利润率标准差": sm_, "相关系数": rho_, "观测数": 0, "区间": T("手动输入")}
    else:
        obs_all = obs_ttm if src == "ttm" else obs_ann
        n_all = len(obs_all)
        lo_n = min(6 if src == "ttm" else 4, n_all)
        n_obs = st.slider(T("使用最近 N 个观测"), lo_n, n_all, n_all, key=f"mc_n_{src}",
                          help=T("相关系数对样本窗口敏感，可拖动观察变化")) if n_all > lo_n else n_all
        emp = M.series_params(obs_all, n_obs)
        obs = obs_all.tail(n_obs)
    emp["方法"] = labels[src]

    bt_ = cd.get("beta") or {}
    beta_se = (abs(bt_["beta"]) * np.sqrt((1 - bt_["r2"]) / (bt_["r2"] * (bt_["weeks"] - 2)))
               if bt_ and 0 < bt_.get("r2", 0) < 1 else np.nan)
    sw_default = round(float(beta_se * A.erp), 2) if beta_se == beta_se else 1.5
    k = st.columns(4)
    k[0].metric(T("营收增速σ"), f"{emp['增速标准差']:.2f} pp")
    k[0].caption(emp["区间"])
    k[1].metric(T("核心经营利润率σ"), f"{emp['利润率标准差']:.2f} pp")
    k[1].caption(T("两者相关系数 {r:+.3f}", r=emp["相关系数"]))
    sig_w = k[2].number_input(T("折现率σ（pp）"), 0.0, 10.0, sw_default, 0.1, key=f"mc_sw_{code}",
                              help=T("SW_HELP", se=beta_se if beta_se == beta_se else 0.0, erp=A.erp, v=sw_default))
    sig_gt = k[3].number_input(T("永续增长率σ（pp）"), 0.0, 3.0, 0.5, 0.1, key=f"mc_sgt_{code}",
                               help=T("永续增长率的不确定性，默认 0.5 个百分点"))

    MC = M.monte_carlo(rev0, A, W, ncd["净现金"], shares_wan, emp["增速标准差"],
                       emp["利润率标准差"], emp["相关系数"], y1_scale, n=sims, sig_w=sig_w, sig_gt=sig_gt, drv=drv)
    ps_pct = M.pct_table(MC["每股价值"])
    np_pct = M.pct_table(MC["第1年归母净利润"])
    p_above = float((MC["每股价值"] > q["price"]).mean())
    share = M.uncertainty_share(MC["抽样"], MC["每股价值"])
    tor = M.tornado(A, rev0, base_year, bs, mcap_wan, shares_wan, emp["增速标准差"], emp["利润率标准差"],
                    max(sig_w, 0.5), max(sig_gt, 0.25), drv=drv)

    # ── 2. 模拟结果
    st.markdown("#### " + T("模拟结果：每股价值的分布"))
    h1, h2 = st.columns([3, 2])
    h1.plotly_chart(value_hist(MC["每股价值"], ps_pct, q["price"], p_above), width="stretch")
    with h2:
        tbl = pd.DataFrame({T("分位数"): list(ps_pct),
                            T("每股价值（元）"): [fmt(ps_pct[k_]) for k_ in ps_pct],
                            T("{y}年归母净利润（万元）", y=base_year + 1): [fmt(np_pct[k_]) for k_ in ps_pct]})
        st.dataframe(tbl, hide_index=True, width="stretch")
        st.markdown("<div class='note'>" + T(
            "每股价值高于现价的概率：{b:.1%}；{y1}年归母净利润低于{y0}年实际值的概率：{a:.1%}。",
            y1=base_year + 1, y0=base_year, b=p_above,
            a=(MC["第1年归母净利润"] < an.loc[base_year, "归母净利润"]).mean()) + "</div>",
            unsafe_allow_html=True)
        st.markdown("<div class='note'>" + T(
            "每次模拟同时随机抽取：未来5年的营收增速与核心经营利润率（按上方相关系数联动），以及折现率、永续增长率。"
            "均值取左侧假设；第1年已披露 {nq} 个季度，增速波动按剩余 {rest:.0%} 缩小；远期波动逐年放大。",
            nq=it["季度数"] if it else 0, rest=y1_scale) + "</div>", unsafe_allow_html=True)

    # ── 3. 龙卷风图 + 不确定性贡献
    st.markdown("#### " + T("哪些假设最影响估值"))
    t1, t2 = st.columns([3, 2])
    t1.plotly_chart(tornado_fig(tor), width="stretch")
    with t2:
        sh_ = share.copy()
        sh_.index = TL(sh_.index)
        fsh = go.Figure(go.Bar(x=sh_["贡献%"], y=sh_.index, orientation="h", marker_color=GREY,
                               text=[f"{v:.0f}%" for v in sh_["贡献%"]], textposition="outside"))
        fsh.update_layout(**{**LAYOUT, "height": 300}, title=T("蒙特卡洛：估值波动来自哪里"),
                          yaxis=dict(autorange="reversed"), xaxis=dict(range=[0, 110], title="%"))
        st.plotly_chart(fsh, width="stretch")
    st.markdown(f"<div class='note'>{T('TORNADO_NOTE')}</div>", unsafe_allow_html=True)

    # ── 4. 双因素网格
    st.markdown("#### " + T("折现率 × 永续增长率：每股价值（元）"))
    base_r, base_c = f"{W:.2f}%", f"{A.g_term:.1f}%"
    sens_show = sens.copy()
    sens_show.index.name = T("折现率 \\ 永续增长率")
    st.dataframe(sens_show.fillna(NA).style.format(na_fmt(lambda v: f"{v:.2f}")).apply(
        lambda s: [f"background-color:{C['hi']};font-weight:600" if (s.name == base_r and c_ == base_c)
                   else "" for c_ in s.index], axis=1), width="stretch")
    sm1, sm2 = st.columns(2)
    for col_, key_, ttl_ in ((sm1, "终值隐含EV/EBITDA", T("同一网格：终值隐含 EV/EBITDA（倍）")),
                             (sm2, "隐含市盈率", T("同一网格：{y} 隐含市盈率（倍）", y=fc["年份"].iloc[0]))):
        with col_:
            st.markdown("**" + ttl_ + "**")
            t_ = sens_m[key_].copy()
            t_.index.name = T("折现率 \\ 永续增长率")
            st.dataframe(t_.fillna(NA).style.format(na_fmt(lambda v: f"{v:.1f}x")).apply(
                lambda s: [f"background-color:{C['hi']};font-weight:600" if (s.name == base_r and c_ == base_c)
                           else "" for c_ in s.index], axis=1), width="stretch")
    st.markdown(f"<div class='note'>{T('SENS_MULT_NOTE')}</div>", unsafe_allow_html=True)

    # ── 5. 参数估计细节
    with st.expander(T("参数估计细节：历史观测与稳健性检查")):
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
        if obs is not None and len(obs) > 2:
            rows = []
            steps = [n_ for n_ in (4, 6, 8, 10, 12, 14, 16, 20, 25) if n_ < len(obs_all)] + [len(obs_all)]
            for n_ in sorted(set(steps)):
                if n_ >= 3:
                    e_ = M.series_params(obs_all, n_)
                    rows.append({T("最近观测数"): n_, T("区间"): e_["区间"], T("增速σ"): round(e_["增速标准差"], 2),
                                 T("利润率σ"): round(e_["利润率标准差"], 2), T("相关系数"): round(e_["相关系数"], 3)})
            st.markdown("**" + T("相关系数随样本窗口的变化") + "**")
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
        f3 = go.Figure(go.Histogram(x=MC["第1年归母净利润"] / 1e4, nbinsx=70, marker_color=LIGHT,
                                    marker_line=dict(color=GREY, width=0.3)))
        for p_, dash, pos in PCT_LINES:
            f3.add_vline(x=np_pct[p_] / 1e4, line_dash=dash, line_color=DARK,
                         annotation_text=p_, annotation_position=pos)
        f3.add_vline(x=an.loc[base_year, "归母净利润"] / 1e4, line_dash="dash", line_color=GREY,
                     annotation_text=T("{y}年实际", y=base_year), annotation_position="bottom right")
        f3.update_layout(**LAYOUT, title=T("{y}年归母净利润分布（亿元）", y=base_year + 1), showlegend=False)
        st.plotly_chart(f3, width="stretch")
        st.markdown("<div class='note'>" + T("各年增速σ：{sg}；利润率σ：{sm}（单位：个百分点）。",
                                             sg=", ".join(f"{x:.1f}" for x in MC["增速σ"]),
                                             sm=", ".join(f"{x:.2f}" for x in MC["利润率σ"])) + "</div>",
                    unsafe_allow_html=True)

# ═══════════════ 首页 Dashboard
with tabs[0]:
    top = st.columns([6, 1])
    if mode == "live":
        top[0].caption(T("行情获取时间：{t}（每 30 秒可刷新）", t=q.get("ts") or cd.get("asof", ""))
                       if q_live else T("实时行情刷新失败，显示加载时的报价"))
        if top[1].button(T("刷新行情"), width="stretch"):
            live_quote.clear(); st.rerun()
    elif mode == "pdf":
        mk_ = st.session_state.get("pdf_market") or {}
        top[0].caption(T("财务数据来自上传的 {n} 份年报（{y0}–{y1}）；股价{p}。",
                         n=len(st.session_state["pdf_reports"]), y0=int(an.index.min()), y1=base_year,
                         p=T("为手动输入") if price_in else (T("来自实时行情") if mk_.get("quote") else T("为手动输入"))))
    else:
        top[0].caption(T("演示快照，行情截至 {t}", t=cd.get("asof", "")))

    up = lambda v: T("{p:+.1%} vs 现价", p=v / q["price"] - 1)
    k = st.columns(5)
    k[0].metric(T("现价（元）"), fmt(q["price"]), f"{chg:+.2f}%",
                delta_color="normal" if is_en() else "inverse", border=True)
    k[1].metric(T("总市值（亿元）"), fmt(q["mcap_yi"]), border=True)
    k[2].metric(T("折现法（元/股）"), fmt(D["每股价值"]), up(D["每股价值"]), delta_color="off", border=True)
    k[3].metric(T("蒙特卡洛中位数（元/股）"), fmt(ps_pct["P50"]), border=True)
    k[3].caption(f"P5–P95  {ps_pct['P5']:.1f} – {ps_pct['P95']:.1f}")
    k[4].metric(T("现价隐含折现率"), f"{iw:.2f}%" if iw == iw else "—", border=True,
                help=T("IW_HELP"))
    k[4].caption(T("模型折现率 {w:.2f}%", w=W))

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
            fp.add_hline(y=D["每股价值"], line_dash="dash", line_color=GREY,
                         annotation_text=f"{T('折现法')} {D['每股价值']:.2f}", annotation_position="top left")
            fp.add_annotation(x=x1, y=ps_pct["P95"], text=T("蒙特卡洛 P5–P95"), showarrow=False,
                              xanchor="right", yanchor="bottom", font=dict(size=11, color=GREY))
        else:
            fp.add_annotation(text=T("无股价数据（非上市公司或行情获取失败）"), showarrow=False,
                              x=0.5, y=0.5, xref="paper", yref="paper", font=dict(color=GREY))
            fp.add_hline(y=D["每股价值"], line_dash="dash", line_color=GREY,
                         annotation_text=f"{T('折现法')} {D['每股价值']:.2f}", annotation_position="top left")
        fp.update_layout(**{**LAYOUT, "height": 360}, title=T("近一年股价与估值"), showlegend=False,
                         yaxis_title=T("元/股"))
        st.plotly_chart(fp, width="stretch")
    with right:
        st.markdown("#### " + T("关键指标"))
        kv = [(T("市盈率 TTM"), f"{fmt(pe_ttm, 1)}x"),
              (T("市净率"), f"{fmt(q.get('pb'), 2)}x"),
              (T("52周区间（元）"), f"{fmt(lo52)} – {fmt(hi52)}"),
              (T("贝塔（100周）"), fmt(cd["beta"]["beta"]) if cd.get("beta") else "—"),
              (T("10年国债"), f"{cd['rf']:.2f}%" if cd.get("rf") else "—"),
              (T("折现率 WACC"), f"{W:.2f}%"),
              (T("永续增长率"), f"{A.g_term:.2f}%"),
              (T("终值占企业价值"), f"{D['终值占比%']:.1f}%"),
              (T("每股净现金（元）"), fmt(ncd["净现金"] / shares_wan)),
              (T("现价隐含折现率"), f"{iw:.2f}%" if iw == iw else "—")]
        st.dataframe(pd.DataFrame(kv, columns=[T("指标"), T("数值")]), hide_index=True,
                     width="stretch", height=36 * (len(kv) + 1) + 3)

    # ── 估值的不确定性（蒙特卡洛）
    st.markdown("#### " + T("估值的不确定性（蒙特卡洛 {n:,} 次）", n=sims))
    u1, u2 = st.columns(2)
    u1.plotly_chart(value_hist(MC["每股价值"], ps_pct, q["price"], p_above, 320), width="stretch")
    u2.plotly_chart(tornado_fig(tor, 320), width="stretch")
    top_ = share.index[0]
    st.markdown("<div class='note'>" + T(
        "90% 的模拟结果落在 {p5:.2f}–{p95:.2f} 元，高于现价的概率 {b:.1%}。估值波动的 {s:.0f}% 来自{f}"
        "（蒙特卡洛秩相关分解，详见「敏感性分析」页签）。",
        p5=ps_pct["P5"], p95=ps_pct["P95"], b=p_above, s=share.loc[top_, "贡献%"], f=T(top_)) + "</div>",
        unsafe_allow_html=True)

    # ── 现价隐含了什么（反向拆解）
    st.markdown("#### " + T("现价隐含了什么"))
    brg = M.bridge(A, rev0, base_year, bs, mcap_wan, shares_wan, drv)
    imp = M.implied_single(A, rev0, base_year, bs, mcap_wan, shares_wan, q["price"], drv)
    b1, b2 = st.columns([3, 2])
    with b1:
        fb_ = go.Figure(go.Bar(
            y=TL(brg["步骤"]), x=brg["每股价值"], orientation="h",
            marker_color=[DARK if v >= q["price"] else GREY for v in brg["每股价值"]],
            text=[f"{v:.2f}（WACC {w:.1f}%）" for v, w in zip(brg["每股价值"], brg["折现率%"])],
            textposition="outside"))
        fb_.add_vline(x=q["price"], line_dash="dash", line_color=RED,
                      annotation_text=T("现价 {p:.2f}", p=q["price"]), annotation_position="top",
                      annotation_font_color=RED)
        fb_.update_layout(**{**LAYOUT, "height": 320}, title=T("逐步放宽假设后的每股价值（累积）"),
                          yaxis=dict(autorange="reversed"),
                          xaxis=dict(range=[0, max(brg["每股价值"].max(), q["price"]) * 1.35]))
        st.plotly_chart(fb_, width="stretch")
    with b2:
        st.markdown("**" + T("只调一个参数时，要达到现价需要：") + "**")
        imp_show = pd.DataFrame({
            T("参数"): TL(imp["参数"]),
            T("当前"): [fmt(v) for v in imp["当前"]],
            T("达到现价所需"): [fmt(v) if v == v else T("无解") for v in imp["达到现价所需"]]})
        st.dataframe(imp_show, hide_index=True, width="stretch")
        st.markdown(f"<div class='note'>{T('BRIDGE_NOTE')}</div>", unsafe_allow_html=True)

    # ── 隐含倍数交叉检验
    st.markdown("#### " + T("隐含倍数交叉检验"))
    m1_, m2_ = st.columns([3, 2])
    with m1_:
        st.dataframe(pd.DataFrame({T("倍数"): [T(x) if "（" not in x or x.startswith("终值") else
                                                x.replace("市盈率", T("市盈率")) for x in mult["倍数"]],
                                   T("折现法隐含"): [mx(v) for v in mult["折现法隐含"]],
                                   T("按现价"): [mx(v) if v == v else "—" for v in mult["按现价"]]}),
                     hide_index=True, width="stretch")
    with m2_:
        r1_ = mult.iloc[1]
        st.markdown("<div class='note'>" + T(
            "MULT_SUMMARY", y=fc["年份"].iloc[0], ev=mx(r1_["折现法隐含"]), evm=mx(r1_["按现价"]),
            pe=mx(mult.iloc[3]["折现法隐含"]), pem=mx(mult.iloc[3]["按现价"]), tv=mx(D["终值隐含EV/EBITDA"])) +
            "</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='note'>{T('MULT_NOTE')}</div>", unsafe_allow_html=True)

    l2, r2 = st.columns(2)
    with l2:
        bars = []
        if hi52 == hi52:
            bars.append((T("52周股价区间"), lo52, hi52))
        bars += [(T("折现法敏感性区间"), float(np.nanmin(sens.values)), float(np.nanmax(sens.values))),
                 (T("蒙特卡洛 P5–P95"), ps_pct["P5"], ps_pct["P95"])]
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
        "- **现价隐含折现率**：要让折现法结果等于现价 {px:.2f} 元，折现率需为 {iw}，模型用的是 {w:.2f}%。\n"
        "- **蒙特卡洛**：{n:,} 次模拟（参数来源：{src}），折现法每股价值中位数 {p50:.2f} 元，"
        "90% 的结果落在 {p5:.2f}–{p95:.2f} 元。",
        w=W, ke=wc["股权成本"], b=A.beta, g=A.g_term, v=D["每股价值"], tv=D["终值占比%"],
        nc=ncd["净现金"] / shares_wan, ncp=ncd["净现金"] / shares_wan / D["每股价值"],
        px=q["price"], iw=f"{iw:.2f}%" if iw == iw else T("无解（任何折现率都达不到）"), n=sims, src=emp["方法"], p50=ps_pct["P50"], p5=ps_pct["P5"], p95=ps_pct["P95"]))
    st.markdown(T("- **折现时点**：估值基准日 {d}，{conv}；第 1 年计入基准日之后 {s:.0%} 的现金流。终值按终值年（稳定状态）自由现金流计算。\n"
                  "- **模型检查**：{k}/{n} 项通过{extra}（详见「计算表」页签顶部）。",
                  d=bs["报告期"], conv=T("年中折现") if A.mid_year else T("年末折现"), s=A.stub, k=n_pass, n=len(CHECKS),
                  extra="" if n_pass == len(CHECKS) else T("，未通过：{x}",
                                                          x="、".join(c_ for c_, s_, _ in CHECKS if s_ != "ok"))))
    if TY["FCFF"] < 0:
        st.warning(T("FCFF_NEG", cx=A.capex_ty, da=fc["折旧摊销/营收%"].iloc[-1]))
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
    st.markdown(f"<div class='note'>{T('所有结果基于左侧假设，调整任一参数即时重算。数据来自东方财富、腾讯、新浪公开接口，仅供学习研究，不构成投资建议。')}</div>",
                unsafe_allow_html=True)
    with st.expander(T("数据获取状态")):
        st.dataframe(pd.DataFrame({T("数据项"): TL(cd["status"].keys()),
                                   T("状态"): [tr_msg(v) for v in cd["status"].values()]}),
                     hide_index=True, width="stretch")

# ═══════════════ 历史财务
with tabs[2]:
    show = ["营业总收入", "营收增速%", "毛利率%", "核心经营利润", "核心经营利润率%", "投资收益及其他",
            "利润总额", "有效税率%", "归母净利润", "扣非归母净利润", "非经常性损益", "研发费用率%",
            "经营现金流", "货币资金", "交易性金融资产", "有息负债", "金融资产占总资产%"]
    t = tr_index(an[show].T.astype(float))
    t.columns = [f"{c}A" for c in t.columns]
    st.markdown("#### " + T("主要财务数据（万元 / %）"))
    st.dataframe(t.fillna(NA).style.format(na_fmt(fmt)), width="stretch", height=36 * (len(t) + 1) + 3)

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
    st.dataframe(tr_index(du.T.astype(float)).fillna(NA).style.format(na_fmt(lambda v: fmt(v, 2))), width="stretch")
    st.markdown(f"<div class='note'>{T('DUPONT_NOTE')}</div>", unsafe_allow_html=True)

# ═══════════════ 计算表：逐年假设 → 三张表 → 自由现金流 → 估值结论
PCT_ROWS = {"营收增速%", "核心经营利润率%", "有效税率%", "营运资本/营收%", "资本开支/营收%", "折旧摊销/营收%"}
INPUT_ROWS = {"营收增速%": "g", "核心经营利润率%": "m", "投资收益及其他": "other",
              "资本开支/营收%": "capex", "折旧摊销/营收%": "da"}
BOLD_ROWS = {"营业总收入", "利润总额", "归母净利润", "经营活动现金流", "自由现金流", "归母权益", "FCFF", "现值"}


def style_stmt(df: pd.DataFrame, hcols: list, fcols: list):
    """三张表的样式：历史列灰底；预测列中由假设驱动的行蓝字；手动修改过的格黄底；合计行加粗。"""
    def css(_):
        out = pd.DataFrame("", index=df.index, columns=df.columns)
        for r_ in df.index:
            for c_ in df.columns:
                st_ = []
                if c_ in hcols:
                    st_.append(f"background-color:{C['hist']}")
                if r_ in BOLD_ROWS:
                    st_.append("font-weight:700")
                if c_ in fcols and r_ in INPUT_ROWS:
                    st_.append(f"color:{C['inp']};font-weight:600")
                    i_ = fcols.index(c_)
                    if i_ in OVR.get(INPUT_ROWS[r_], {}):
                        st_.append(f"background-color:{C['ovr']}")
                if r_ == "平衡检查":
                    st_.append(f"color:{GREY};font-style:italic")
                out.loc[r_, c_] = ";".join(st_)
        return out
    sty = df.astype(float).fillna(NA).style.apply(css, axis=None)
    for r_ in df.index:
        f_ = (lambda v: f"{v:.2f}%") if r_ in PCT_ROWS else \
             ((lambda v: f"{v:.4f}") if r_ == "折现因子" else
              ((lambda v: f"{v:.0%}") if r_ == "计入比例" else
               ((lambda v: f"{v:.2f}") if r_ == "折现年数" else (lambda v: fmt(v)))))
        sty = sty.format(na_fmt(f_), subset=pd.IndexSlice[[r_], :])
    return sty.format_index(lambda x: T(x), axis=0)


with tabs[1]:
    st.markdown("#### " + T("模型检查") + f"　<span class='hdr-sub'>{T('{k}/{n} 项通过', k=n_pass, n=len(CHECKS))}"
                + "　·　" + (T("基准情形（数据默认假设）") if IS_BASE else T("已调整假设")) + "</span>",
                unsafe_allow_html=True)
    ICON = {"ok": ("✓", "#2E8B57"), "warn": ("!", "#C98A00"), "fail": ("✗", "#C0392B")}
    chk_html = "".join(
        f"<div class='chk'><span style='color:{ICON[s_][1]};font-weight:700'>{ICON[s_][0]}</span> "
        f"<b>{lab_}</b><span class='chk-d'>{det_}</span></div>" for lab_, s_, det_ in CHECKS)
    st.markdown(f"<div class='chk-grid'>{chk_html}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<span class='legend-chip' style='color:{C['inp']};font-weight:600;border:1px solid {C['grid']}'>"
        f"{T('蓝字 = 可直接修改')}</span>"
        f"<span class='legend-chip' style='background:{C['ovr']}'>{T('黄底 = 手动修改过')}</span>"
        f"<span class='legend-chip' style='background:{C['hist']};border:1px solid {C['grid']}'>"
        f"{T('灰底 = 历史实际')}</span>", unsafe_allow_html=True)

    # ── 1. 逐年假设（汇总，可直接修改）
    st.markdown("#### " + T("关键假设（逐年，可直接修改）"))
    h_ = an.tail(4)
    hcols, fcols = [f"{y}A" for y in h_.index], list(fc["年份"])
    hist_v = {"g": h_["营收增速%"], "m": h_["核心经营利润率%"], "other": h_["投资收益及其他"],
              "capex": h_["资本开支/营收%"], "da": h_["折旧摊销/营收%"]}
    drv_rows = pd.DataFrame({lab_: {**dict(zip(hcols, [float(x) for x in hist_v[k_]])),
                                    **dict(zip(fcols, [float(x) for x in drv[k_]]))}
                             for k_, lab_ in DRV_ROWS}).T
    sheet_grid(drv_rows, "grid_drv", hcols, fcols,
               {lab_: {"pct": k_ != "other", "fedit": k_} for k_, lab_ in DRV_ROWS})
    n_ovr = sum(len(v_) for v_ in OVR.values())
    o1, o2 = st.columns([4, 1])
    if n_ovr:
        items_ = [f"{fcols[i_]} {T(dict(DRV_ROWS)[k_])}" for k_, cells in OVR.items() for i_ in sorted(cells)
                  if i_ < len(fcols)]
        o1.markdown("<div class='note'>" + T("已手动修改 {n} 格：{items}。其余年份仍按左侧首末年假设线性插值。",
                                            n=n_ovr, items="、".join(items_)) + "</div>", unsafe_allow_html=True)
        o2.button(T("撤销全部手动修改"), on_click=clear_overrides, width="stretch")
    else:
        o1.markdown(f"<div class='note'>{T('CALC_EDIT_NOTE')}</div>", unsafe_allow_html=True)
    st.markdown("<div class='note'>" + T(
        "其余假设在左侧调整：有效税率 {tax:.1f}%、营运资本 / 营收增量 {nwc:.1f}%、投资收益计入现金流比例 {of:.0f}%、"
        "分红率 {po:.0f}%（只影响预测资产负债表）。",
        tax=A.tax, nwc=A.nwc_pct, of=A.other_in_fcf, po=A.payout) + "</div>", unsafe_allow_html=True)

    v1, v2 = st.columns(2)
    xs_ = hcols + fcols
    fg = go.Figure()
    fg.add_trace(go.Bar(x=xs_, y=list(h_["营业总收入"] / 1e4) + list(fc["营业总收入"] / 1e4),
                        marker_color=[GREY] * len(hcols) + [LIGHT] * len(fcols),
                        marker_line=dict(color=DARK, width=0.5), name=T("营业总收入（亿元）")))
    fg.add_trace(go.Scatter(x=xs_, y=list(h_["营收增速%"]) + list(drv["g"]), yaxis="y2", mode="lines+markers",
                            line=dict(color=DARK), name=T("营收增速（%，右轴）")))
    fg.update_layout(**{**LAYOUT, "height": 300}, title=T("营收与增速：历史与预测"),
                     yaxis2=dict(overlaying="y", side="right", showgrid=False))
    v1.plotly_chart(fg, width="stretch")
    fm_ = go.Figure()
    for k_, col_, nm_, dash_ in (("m", "核心经营利润率%", "核心经营利润率", "solid"),
                                 ("capex", "资本开支/营收%", "资本开支 / 营收", "dot"),
                                 ("da", "折旧摊销/营收%", "折旧摊销 / 营收", "dash")):
        fm_.add_trace(go.Scatter(x=xs_, y=list(h_[col_]) + list(drv[k_]), mode="lines+markers",
                                 line=dict(color=DARK if k_ == "m" else GREY, dash=dash_), name=T(nm_)))
    fm_.add_vrect(x0=fcols[0], x1=fcols[-1], fillcolor=C["hist"], opacity=0.6, line_width=0, layer="below")
    fm_.update_layout(**{**LAYOUT, "height": 300}, title=T("利润率与资本开支（%）"))
    v2.plotly_chart(fm_, width="stretch")

    # ── 2. 三张表（蓝色格子可直接修改；上传年报时历史科目也可修改）
    st.markdown("#### " + T("三张表（万元）"))
    st.markdown(f"<div class='note'>{T('STMT_EDIT_NOTE_PDF' if mode == 'pdf' else 'STMT_EDIT_NOTE')}</div>",
                unsafe_allow_html=True)
    pdf_ = mode == "pdf"
    META = {
        "利润表": {"营业总收入": {"bold": True, "hedit": "营业总收入" if pdf_ else ""},
                  "营收增速%": {"pct": True, "fedit": "g"},
                  "营业总成本": {"hedit": "营业总成本" if pdf_ else ""},
                  "核心经营利润率%": {"pct": True, "fedit": "m"},
                  "投资收益及其他": {"fedit": "other"},
                  "利润总额": {"bold": True, "hedit": "利润总额" if pdf_ else ""},
                  "所得税": {"hedit": "所得税" if pdf_ else ""}, "有效税率%": {"pct": True},
                  "净利润": {"hedit": "净利润" if pdf_ else ""},
                  "归母净利润": {"bold": True, "hedit": "归母净利润" if pdf_ else ""}},
        "现金流量表": {"归母净利润": {"bold": True}, "折旧摊销": {"hedit": "折旧摊销" if pdf_ else ""},
                    "经营活动现金流": {"bold": True, "hedit": "经营现金流" if pdf_ else ""},
                    "资本开支": {"hedit": "资本开支" if pdf_ else ""}, "自由现金流": {"bold": True},
                    "资本开支/营收%": {"pct": True, "fedit": "capex"},
                    "折旧摊销/营收%": {"pct": True, "fedit": "da"}},
        "资产负债表": {"归母权益": {"bold": True}, "营运资本/营收%": {"pct": True}},
    }
    s1, s2, s3 = st.tabs(TL(["利润表", "现金流量表", "资产负债表（经营视角）"]))
    for tab_, key_ in ((s1, "利润表"), (s2, "现金流量表"), (s3, "资产负债表")):
        with tab_:
            sheet_grid(ts[key_], f"grid_{key_}", ts["历史列"], ts["预测列"], META[key_])
            st.markdown(f"<div class='note'>{T('STMT_NOTE_' + key_)}</div>", unsafe_allow_html=True)

    # ── 3. 上传年报：全部原始科目（可修改）
    if mode == "pdf":
        with st.expander(T("年报原始科目（全部年份，可修改）")):
            raw_show = raw_ed.drop(columns=[c_ for c_ in raw_ed.columns if c_ not in pdf_parser.SHOW],
                                   errors="ignore")
            rgrid = raw_show.T.astype(float)
            rgrid.columns = [f"{y}A" for y in rgrid.columns]
            sheet_grid(rgrid, "grid_pdf_raw", list(rgrid.columns), [], {f: {"hedit": f} for f in rgrid.index})
            rows_ = []
            for r in st.session_state["pdf_reports"]:
                pg = r["来源"]
                rows_.append({T("文件"): r["文件"], T("报告年度"): r["年度"],
                              T("公司"): f"{r['公司简称']} {r['公司代码']}",
                              T("资产负债表页码"): pg.get("货币资金", "—"), T("利润表页码"): pg.get("营业总收入", "—"),
                              T("现金流量表页码"): pg.get("经营现金流", "—"),
                              T("补充资料页码"): pg.get("固定资产折旧", "—"),
                              T("提示"): "；".join(tr_msg(x) for x in r["提示"]) or "—"})
            st.dataframe(pd.DataFrame(rows_), hide_index=True, width="stretch")
            st.markdown(f"<div class='note'>{T('PDF_MERGE_NOTE')}</div>", unsafe_allow_html=True)

    # ── 4. 自由现金流与折现
    st.markdown("#### " + T("自由现金流与折现（万元）"))
    fcf_t = fc.set_index("年份")[["NOPAT", "折旧摊销", "资本开支", "营运资金增加", "FCFF"]].T
    fcf_t.loc["计入比例"] = D["计入比例"]
    fcf_t.loc["折现年数"] = D["折现年数"]
    fcf_t.loc["折现因子"] = D["折现因子"]
    fcf_t.loc["现值"] = D["现值"]
    fcf_t[T("终值年")] = [TY["NOPAT"], TY["折旧摊销"], TY["资本开支"], TY["营运资金增加"], TY["FCFF"],
                        np.nan, np.nan, np.nan, np.nan]
    st.dataframe(style_stmt(fcf_t.astype(float), [], []), width="stretch", height=36 * (len(fcf_t) + 1) + 3)
    st.markdown(f"<div class='note'>{T('FCFF_NOTE')}</div>", unsafe_allow_html=True)
    l, r = st.columns([1, 1])
    with l:
        st.markdown("**" + T("折现率") + "**")
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
        st.markdown("**" + T("估值桥") + "**")
        st.markdown("<div class='formula'>" + T(
            "预测期现值合计　{pv}<br>"
            "终值 = 终值年 FCFF {f} ÷ ({w:.2f}% − {g:.2f}%) = {tv}<br>"
            "终值现值 = {tv} × {df:.4f} = {tpv}<br>"
            "企业价值 = {ev}　（终值占比 {tvp:.1f}%）<br>"
            "＋ 货币资金 {cash}　＋ 交易性金融资产 {fin}　− 有息负债 {debt}<br>"
            "股权价值 = {eq}　÷ 总股本 {sh} 万股<br>"
            "<b>每股价值 = {ps:.2f} 元</b>",
            pv=fmt(D["预测期现值合计"]), f=fmt(TY["FCFF"]), g=A.g_term, w=W, tv=fmt(D["终值"]),
            df=D["折现因子"][-1], tpv=fmt(D["终值现值"]), ev=fmt(D["企业价值"]), tvp=D["终值占比%"],
            cash=fmt(ncd["货币资金"]), fin=fmt(ncd["交易性金融资产"]), debt=fmt(ncd["有息负债"]),
            eq=fmt(D["股权价值"]), sh=fmt(shares_wan), ps=D["每股价值"]) + "</div>", unsafe_allow_html=True)
        st.caption(T("金额单位：万元；净现金取 {d} 资产负债表", d=bs["报告期"]))

    # ── 5. 估值结论
    st.markdown("#### " + T("估值结论"))
    kk = st.columns(4)
    kk[0].metric(T("每股内在价值（元）"), fmt(D["每股价值"]), T("{p:+.1%} vs 现价", p=D["每股价值"] / q["price"] - 1),
                 delta_color="off", border=True)
    kk[1].metric(T("蒙特卡洛 90% 区间（元）"), f"{ps_pct['P5']:.1f} – {ps_pct['P95']:.1f}", border=True)
    kk[2].metric(T("价值高于现价的概率"), f"{p_above:.1%}", border=True)
    kk[3].metric(T("现价隐含折现率"), f"{iw:.2f}%" if iw == iw else "—", T("模型 {w:.2f}%", w=W),
                 delta_color="off", border=True)
    t0 = tor.iloc[0]
    lines_ = [T("VERDICT_1", name=q["name"], v=D["每股价值"], px=q["price"],
                dir=T("高于") if D["每股价值"] >= q["price"] else T("低于"),
                x=abs(D["每股价值"] / q["price"] - 1), p5=ps_pct["P5"], p95=ps_pct["P95"], pa=p_above),
              T("VERDICT_2", tv=D["终值占比%"], nc=ncd["净现金"] / shares_wan,
                ncp=ncd["净现金"] / shares_wan / D["每股价值"] if D["每股价值"] else float("nan")),
              T("VERDICT_3", f=T(t0["因素"]), r=t0["变动幅度"], lo=t0["低"], hi=t0["高"]),
              (T("VERDICT_4", iw=iw, w=W) if iw == iw else T("VERDICT_4N")),
              T("VERDICT_5", y=fc["年份"].iloc[0], pe=mx(mult.iloc[3]["折现法隐含"]), pem=mx(mult.iloc[3]["按现价"]),
                tv=mx(D["终值隐含EV/EBITDA"]))]
    if n_ovr:
        lines_.append(T("其中 {n} 个逐年假设为手动修改（见上方黄底单元格）。", n=n_ovr))
    st.markdown("<div class='verdict'>" + "<br>".join("· " + x for x in lines_) + "</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='note'>{T('VERDICT_NOTE')}</div>", unsafe_allow_html=True)

# ═══════════════ 导出
with tabs[4]:
    st.markdown("#### " + T("导出估值模型"))
    st.markdown(T("Excel 中的预测、折现法、敏感性均为**活公式**：蓝色为输入，改动「假设」表任一蓝色单元格，"
                  "全部结果自动重算。蒙特卡洛结果以数值形式附上。当前语言决定 Excel 的语言。"))
    xls = export.build_workbook({**cd, "quote": q}, A, dict(
        wacc=wc, dcf=D, mc_ps=ps_pct, sig_w=sig_w, sig_gt=sig_gt, drv=drv, mc_np=np_pct, emp=emp, y1_scale=y1_scale, sims=sims,
        mc_sg=MC["增速σ"], mc_sm=MC["利润率σ"]))
    st.download_button(T("下载 Excel 估值模型"), xls,
                       file_name=T("{n}_{c}_估值模型.xlsx", n=q["name"], c=q["code"]),
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width="stretch")
    st.markdown("#### " + T("Excel 模板"))
    st.markdown(T("TEMPLATE_NOTE"))
    t1_, t2_ = st.columns(2)
    t1_.download_button(T("下载已填入本公司数据的模板（中文）"),
                        template.build_template({"name": q["name"], "code": q["code"], "annual": an, "A": A,
                                                 "bs": bs, "quote": q, "drv": drv, "ovr": OVR}),
                        file_name=f"DCF估值模板_{q['name']}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        width="stretch", help=T("TEMPLATE_FILLED_HELP"))
    t2_.download_button(T("下载空白折现法模板（中文）"), template.build_template(),
                        file_name="DCF估值模板_空白.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        width="stretch")
    st.markdown("#### " + T("方法与数据说明"))
    st.markdown(T("METHOD_NOTES"))
