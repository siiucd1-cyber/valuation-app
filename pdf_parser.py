# -*- coding: utf-8 -*-
"""从 A 股年度报告 PDF 中抽取合并报表科目。

做法：
1. 按页找出「合并资产负债表 / 合并利润表 / 合并现金流量表」及其母公司报表的标题位置；
   每张表格归属于它上方最近的标题（跨页时沿用上一页的最后一个标题），只取合并报表。
2. 用表格结构（pdfplumber.find_tables）读取「科目 | 附注 | 本期 | 上期」，避免跨行科目打乱数字顺序。
3. 现金流量表补充资料取折旧摊销；「主要会计数据」取扣非归母净利润。
4. 每份年报给出本年与上年两期数据，多份年报合并时优先采用「本年」口径。
所有金额统一换算为万元，并记录来源页码，便于人工核对。
"""
from __future__ import annotations

import hashlib
import io
import re

import pandas as pd

TITLES = ["合并资产负债表", "母公司资产负债表", "合并利润表", "母公司利润表",
          "合并现金流量表", "母公司现金流量表", "合并所有者权益变动表", "母公司所有者权益变动表",
          "合并股东权益变动表", "母公司股东权益变动表"]
UNIT = {"元": 1e-4, "千元": 1e-1, "万元": 1.0, "百万元": 100.0}

# 字段 → (所属报表, 候选科目名（归一化后，按顺序匹配，完全相等）)
FIELDS = {
    # 利润表
    "营业总收入": ("PL", ["营业总收入"]),
    "营业收入": ("PL", ["营业收入"]),
    "营业总成本": ("PL", ["营业总成本"]),
    "营业成本": ("PL", ["营业成本"]),
    "税金及附加": ("PL", ["税金及附加", "营业税金及附加"]),
    "销售费用": ("PL", ["销售费用"]),
    "管理费用": ("PL", ["管理费用"]),
    "研发费用": ("PL", ["研发费用"]),
    "财务费用": ("PL", ["财务费用"]),
    "营业利润": ("PL", ["营业利润"]),
    "利润总额": ("PL", ["利润总额"]),
    "所得税": ("PL", ["所得税费用", "所得税"]),
    "净利润": ("PL", ["净利润"]),
    "归母净利润": ("PL", ["归属于母公司股东的净利润", "归属于母公司所有者的净利润", "归属于母公司的净利润"]),
    # 资产负债表
    "货币资金": ("BS", ["货币资金"]),
    "交易性金融资产": ("BS", ["交易性金融资产", "以公允价值计量且其变动计入当期损益的金融资产"]),
    "应收账款": ("BS", ["应收账款"]),
    "存货": ("BS", ["存货"]),
    "固定资产": ("BS", ["固定资产"]),
    "资产总计": ("BS", ["资产总计", "资产合计"]),
    "短期借款": ("BS", ["短期借款"]),
    "应付账款": ("BS", ["应付账款"]),
    "一年内到期非流动负债": ("BS", ["一年内到期的非流动负债"]),
    "长期借款": ("BS", ["长期借款"]),
    "应付债券": ("BS", ["应付债券"]),
    "归母权益": ("BS", ["归属于母公司所有者权益合计", "归属于母公司所有者权益（或股东权益）合计",
                      "归属于母公司股东权益合计", "归属于母公司所有者的权益合计"]),
    "股本": ("BS", ["实收资本（或股本）", "股本", "实收资本"]),
    # 现金流量表
    "经营现金流": ("CF", ["经营活动产生的现金流量净额"]),
    "资本开支": ("CF", ["购建固定资产、无形资产和其他长期资产支付的现金"]),
    # 补充资料
    "固定资产折旧": ("SUP", ["固定资产折旧、油气资产折耗、生产性生物资产折旧", "固定资产折旧"]),
    "使用权资产折旧": ("SUP", ["使用权资产折旧", "使用权资产摊销"]),
    "无形资产摊销": ("SUP", ["无形资产摊销"]),
    "长期待摊费用摊销": ("SUP", ["长期待摊费用摊销"]),
}
# 界面上展示、写入模板的字段顺序
SHOW = ["营业总收入", "营业收入", "营业成本", "营业总成本", "研发费用", "利润总额", "所得税", "净利润",
        "归母净利润", "扣非归母净利润", "折旧摊销", "资本开支", "经营现金流", "应收账款", "存货",
        "应付账款", "货币资金", "交易性金融资产", "短期借款", "一年内到期非流动负债", "长期借款",
        "应付债券", "资产总计", "归母权益", "股本（万股）"]

_NUM = re.compile(r"^\(?-?[\d,]+(\.\d+)?\)?$")


def _num(cell) -> float | None:
    if cell is None:
        return None
    t = str(cell).replace("\n", "").replace(" ", "").replace("，", ",")
    if t in ("", "—", "--"):
        return None
    if t in ("-", "–", "－"):
        return 0.0
    t = t.replace("－", "-").replace("–", "-")
    if not _NUM.match(t):
        return None
    neg = t.startswith("(") and t.endswith(")")
    v = float(t.strip("()").replace(",", ""))
    return -v if neg else v


def _norm(label) -> str:
    t = re.sub(r"\s+", "", str(label or ""))
    t = re.sub(r"[（(][^（）()]*(号填列|号列示)[^（）()]*[）)]", "", t)      # 去掉“（损失以“－”号填列）”
    t = re.sub(r"^[一二三四五六七八九十]+[、.．]", "", t)
    t = re.sub(r"^[（(][一二三四五六七八九十\d]+[）)]", "", t)
    t = re.sub(r"^\d+[、.．]", "", t)
    t = re.sub(r"^(其中|加|减)[:：]", "", t)
    return t.strip("：:")


def _unit_near(text: str) -> float:
    m = re.search(r"单位[:：]\s*(百万元|千元|万元|元)", text or "")
    return UNIT[m.group(1)] if m else 1e-4


def file_key(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def parse_report(data: bytes, name: str = "") -> dict:
    """解析一份年报。返回 {公司代码, 公司简称, 年度, 数据: {年: {字段: 值}}, 来源: {字段: 页码}, 提示: [..]}"""
    import pdfplumber

    out = {"文件": name, "公司代码": "", "公司简称": "", "年度": None, "数据": {}, "来源": {}, "提示": []}
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = pdf.pages
        head = "\n".join((pages[i].extract_text() or "") for i in range(min(3, len(pages))))
        m = re.search(r"(?:公司|证券|股票)代码[:：]?\s*(\d{6})", head)
        out["公司代码"] = m.group(1) if m else ""
        m = re.search(r"(?:公司|证券|股票)简称[:：]?\s*([^\s\d]{2,10})", head)
        out["公司简称"] = m.group(1) if m else ""
        m = re.search(r"(20\d{2})\s*年\s*年度报告", head)
        year = int(m.group(1)) if m else None
        out["年度"] = year
        if year is None:
            out["提示"].append("未能从封面识别报告年度")
            return out

        vals: dict[str, list] = {}          # 字段 → [本期, 上期, 页码]
        ctx, stmt_started, sup_done, key_done = None, False, False, False
        unit = 1e-4
        texts = {}
        for pi, page in enumerate(pages):
            txt = page.extract_text() or ""
            texts[pi] = txt
            # 主要会计数据：扣非归母净利润（在前 15 页）
            if not key_done and pi < 15 and "主要会计数据" in txt:
                for tb in page.extract_tables():
                    for row in tb:
                        lab = _norm(row[0]) if row else ""
                        if "扣除非经常性损益" in lab and "净利润" in lab and "归属于" in lab:
                            nums = [_num(c) for c in row[1:]]
                            nums = [x for x in nums if x is not None]
                            if len(nums) >= 2:
                                u = _unit_near(txt)
                                vals["扣非归母净利润"] = [nums[0] * u, nums[1] * u, pi + 1]
                                key_done = True
            # 标题定位（整行等于标题，排除目录）
            marks = []
            for t in TITLES:
                for hit in page.search(rf"(?m)^\s*{t}\s*$", regex=True, return_chars=False):
                    marks.append((hit["top"], t))
            marks.sort()
            if any(t == "合并资产负债表" for _, t in marks) and "项目" in txt:
                stmt_started = True
            if not stmt_started:
                continue
            if marks:
                unit = _unit_near(txt)
            tables = page.find_tables()
            for tb in tables:
                top = tb.bbox[1]
                above = [t for y, t in marks if y < top]
                cur = above[-1] if above else ctx
                if cur is None:
                    continue
                kind = {"合并资产负债表": "BS", "合并利润表": "PL", "合并现金流量表": "CF"}.get(cur)
                rows = tb.extract()
                if kind is None:
                    continue
                for row in rows:
                    if not row or len(row) < 3:
                        continue
                    lab = _norm(row[0])
                    # 报表最后两列固定为「本期 | 上期」，按位置读取，空格即为缺失
                    cur_v, prev_v = _num(row[-2]), _num(row[-1])
                    if cur_v is None and prev_v is None:
                        continue
                    for fld, (k, names) in FIELDS.items():
                        if k == kind and fld not in vals and lab in names:
                            vals[fld] = [None if cur_v is None else cur_v * unit,
                                         None if prev_v is None else prev_v * unit, pi + 1]
            if marks:
                ctx = marks[-1][1]
            # 补充资料（在报表之后的附注中，首次出现者为合并口径）
            if not sup_done and "现金流量表补充资料" in txt:
                sup_hit = False
                for tb in page.extract_tables():
                    for row in tb:
                        if not row or len(row) < 2:
                            continue
                        lab = _norm(row[0])
                        c_, p_ = _num(row[-2]), _num(row[-1])
                        for fld, (k, names) in FIELDS.items():
                            if k == "SUP" and fld not in vals and any(lab.startswith(n) for n in names):
                                u = _unit_near(txt)
                                vals[fld] = [(c_ or 0.0) * u, (p_ or 0.0) * u, pi + 1]
                                sup_hit = True
                # 折旧摊销各行通常在同一页；取到「长期待摊费用摊销」即视为完成（跨页时下一页继续补齐）
                if sup_hit and "长期待摊费用摊销" in vals:
                    sup_done = True
            if sup_done and all(f in vals for f in ("营业总收入", "货币资金", "经营现金流")):
                break

        # 营业总成本缺失时由分项加总
        if "营业总成本" not in vals and "营业成本" in vals:
            parts = ["营业成本", "税金及附加", "销售费用", "管理费用", "研发费用", "财务费用"]
            for j in (0, 1):
                s = sum((vals[p][j] or 0.0) for p in parts if p in vals)
                vals.setdefault("营业总成本", [None, None, vals["营业成本"][2]])[j] = s
            out["提示"].append("利润表无「营业总成本」行，已由营业成本与各项费用加总")
        if "营业总收入" not in vals and "营业收入" in vals:
            vals["营业总收入"] = list(vals["营业收入"])
        if "所得税" not in vals and "利润总额" in vals and "净利润" in vals:
            vals["所得税"] = [None if (a is None or b is None) else a - b
                            for a, b in zip(vals["利润总额"][:2], vals["净利润"][:2])] + [vals["净利润"][2]]
            out["提示"].append("利润表未单列所得税，按「利润总额 − 净利润」推算")

    for j, y in ((0, year), (1, year - 1)):
        d = {f: v[j] for f, v in vals.items() if v[j] is not None}
        dep = [d.get(k) for k in ("固定资产折旧", "使用权资产折旧", "无形资产摊销", "长期待摊费用摊销")]
        d["折旧摊销"] = sum(x for x in dep if x is not None) if any(x is not None for x in dep) else None
        if "股本" in d:
            d["股本（万股）"] = d.pop("股本")        # 股本以元计，×1e-4 后即为万股
        out["数据"][y] = d
    out["来源"] = {f: v[2] for f, v in vals.items()}
    miss = [f for f in ["营业总收入", "营业总成本", "利润总额", "所得税", "净利润", "归母净利润",
                        "货币资金", "资产总计", "经营现金流", "资本开支"] if f not in vals]
    if miss:
        out["提示"].append("未找到：" + "、".join(miss))
    return out


def merge_reports(reports: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """多份年报合并为「年度 × 字段」表（万元）。
    同一年度优先采用次年年报中的「上期」数（已按追溯调整重述，与后续年度口径一致），
    没有次年年报时用该年年报的「本期」数。第二个返回值标注每个数取自哪份报告。"""
    cur, prev = {}, {}
    for r in reports:
        y = r.get("年度")
        if not y:
            continue
        cur[y] = (r["数据"].get(y, {}), r["文件"])
        prev[y - 1] = (r["数据"].get(y - 1, {}), r["文件"])
    years = sorted(set(cur) | set(prev))
    rows, src = {}, {}
    for y in years:
        d, s_ = {}, {}
        for layer, tag in ((cur.get(y), "本期"), (prev.get(y), "上期（重述口径）")):
            if not layer:
                continue
            vals_, fname = layer
            for k, v in vals_.items():
                if v is not None:
                    d[k], s_[k] = v, f"{fname} {tag}"
        rows[y], src[y] = d, s_
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "年度"
    cols = [c for c in SHOW if c in df.columns] + [c for c in df.columns if c not in SHOW]
    return df.reindex(columns=cols), pd.DataFrame.from_dict(src, orient="index").reindex(columns=cols)


def to_annual(raw: pd.DataFrame) -> pd.DataFrame:
    """把解析结果整理成与在线数据相同的年度表（含衍生指标）。缺失科目按 0 处理。"""
    import data
    need = ["营业总收入", "营业收入", "营业成本", "营业总成本", "研发费用", "营业利润", "利润总额", "所得税",
            "净利润", "归母净利润", "扣非归母净利润", "货币资金", "交易性金融资产", "资产总计", "归母权益",
            "固定资产", "应收账款", "存货", "应付账款", "短期借款", "长期借款", "应付债券",
            "一年内到期非流动负债", "经营现金流", "资本开支", "折旧摊销"]
    out = pd.DataFrame(index=raw.index)
    for c in need:
        out[c] = pd.to_numeric(raw[c], errors="coerce") if c in raw.columns else float("nan")
    if out["扣非归母净利润"].isna().all():
        out["扣非归母净利润"] = out["归母净利润"]
    out = out.fillna(0.0)
    out["有息负债"] = out[["短期借款", "长期借款", "应付债券", "一年内到期非流动负债"]].sum(axis=1)
    return data.derive(out)


def build_company(raw: pd.DataFrame, reports: list[dict], market: dict | None, price: float | None) -> dict:
    """把解析结果组装成与在线数据同构的 cd 字典，供网页的全部估值功能直接使用。
    market 为 data.load_market 的结果（上市公司可取实时行情与贝塔）；price 为手动输入的每股价格。"""
    import datetime as dt
    annual = to_annual(raw)
    last = int(annual.index.max())
    r = annual.loc[last]
    latest = max((x for x in reports if x.get("年度")), key=lambda x: x["年度"])
    code, name = latest.get("公司代码") or "", latest.get("公司简称") or ""
    shares_wan = float(raw.loc[last, "股本（万股）"]) if "股本（万股）" in raw.columns and \
        raw.loc[last, "股本（万股）"] == raw.loc[last, "股本（万股）"] else float("nan")
    m = market or {}
    q = dict(m.get("quote") or {})
    if price:
        q["price"] = float(price)
    if not q.get("shares"):
        q["shares"] = shares_wan * 1e4
    q.setdefault("code", code or "—")
    q.setdefault("name", name or "上传年报")
    q.setdefault("industry", "")
    q.setdefault("chg_pct", 0.0)
    q.setdefault("pb", float("nan"))
    q.setdefault("price", float("nan"))
    q["mcap_yi"] = q["price"] * q["shares"] / 1e8
    status = {f"{x['年度']}年报": ("ok" if not x["提示"] else "；".join(x["提示"])) for x in reports}
    status.update(m.get("status", {}))
    return {
        "code": code, "quote": q, "annual": annual,
        "annual_long": annual[["营业总收入", "营业总成本"]],
        "bs_latest": {"报告期": f"{last}-12-31", "货币资金": float(r["货币资金"]),
                      "交易性金融资产": float(r["交易性金融资产"]), "有息负债": float(r["有息负债"]),
                      "资产总计": float(r["资产总计"]), "归母权益": float(r["归母权益"])},
        "quarterly": pd.DataFrame(columns=["季度", "日期", "营业总收入", "营业总成本", "归母净利润"]),
        "interim": None, "prices": m.get("prices"), "beta": m.get("beta"), "rf": m.get("rf"),
        "status": status, "asof": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "source": "pdf",
    }
