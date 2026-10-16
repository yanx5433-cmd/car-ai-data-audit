"""汽车之家口碑页字段批量实测 v3。

模式：
  python 复算_汽车之家字段实测.py ids [品牌数]      # 采集车系 ID -> ids.json
  python 复算_汽车之家字段实测.py probe [数量]      # 从 ids.json 取未跑的跑，增量写 raw_字段实测.json
  python 复算_汽车之家字段实测.py report            # 只从 raw json 重算并打印三张表
"""
import subprocess, re, sys, json, time, os, tempfile

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
IDS = os.path.join(DATA, "series_ids.json")
RAW = os.path.join(DATA, "raw_catalog128.json")
HOT = os.path.join(DATA, "raw_hot34.json")
PRICE = "https://www.autohome.com.cn/price"
SEEN_URLS = [PRICE, PRICE + "/x-x-x-x-x-x-x-x-x-x-x"]


def dom(url, budget="6000"):
    p = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
                        "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "autohome-crawl-profile"),
                        "--virtual-time-budget=" + budget, "--dump-dom", url],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=150)
    return p.stdout or ""


def to_text(h):
    h = re.sub(r"(?is)<script.*?</script>", " ", h)
    h = re.sub(r"(?is)<style.*?</style>", " ", h)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", h).replace("&nbsp;", " "))


def after(t, label, n=40):
    i = t.find(label)
    return t[i + len(label):i + len(label) + n].strip() if i >= 0 else ""


def load(p, d):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d


def save(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# ---------- ids ----------
def cmd_ids(nbrand):
    h = dom(PRICE, "9000")
    brands = []
    for m in re.finditer(r'/price/brandid_(\d+)', h):
        if m.group(1) not in brands:
            brands.append(m.group(1))
    print("发现品牌页 %d 个，取前 %d 个" % (len(brands), nbrand), file=sys.stderr)
    ids = []
    for u in SEEN_URLS:
        for m in re.finditer(r'https://www\.autohome\.com\.cn/(\d{2,5})/?["#]', dom(u, "9000")):
            if m.group(1) not in ids:
                ids.append(m.group(1))
    for b in brands[:nbrand]:
        hh = dom("https://www.autohome.com.cn/price/brandid_%s" % b, "9000")
        got = re.findall(r'https://www\.autohome\.com\.cn/(\d{2,5})/?["#]', hh)
        new = [i for i in got if i not in ids]
        ids.extend(new)
        print("  brand %s -> +%d (累计 %d)" % (b, len(new), len(ids)), file=sys.stderr)
    save(IDS, ids)
    print("车系 ID 共 %d 个，已写入 ids.json" % len(ids))


# ---------- probe ----------
def probe(cid):
    h = dom("https://k.autohome.com.cn/%s/" % cid)
    if len(h) < 20000:
        return None
    t = to_text(h)
    name = (re.search(r"【(.+?)】", h) or [None, "?"])[1].replace("怎么样", "").strip()
    price_s = after(t, "厂商指导价", 24)
    pm = re.search(r"([\d.]+)-([\d.]+)万", price_s)
    used_s = after(t, "二手车价格", 20)
    um = re.search(r"([\d.]+)-([\d.]+)万", used_s)
    dim = after(t, "维度评价", 60)
    if not dim or re.match(r"^(热门对比|同级别|车系名称)", dim):
        dim_state = "无该区块"
    elif "--" in dim[:40]:
        dim_state = "空值(--)"
    elif re.search(r"空间\s*[\d.]+\d", dim):
        dim_state = "有分值"
    else:
        dim_state = "其他"
    tag = after(t, "询底价", 90)
    return {"id": cid, "name": name, "price_raw": price_s.split("选车")[0].strip(),
            "new_lo": float(pm.group(1)) if pm else None,
            "new_hi": float(pm.group(2)) if pm else None,
            "hot": (re.search(r"选车热度\s*(\d+)", t) or [None, None])[1],
            "score": (re.search(r"口碑评分\s*([\d.]+)", t) or [None, None])[1],
            "fault": (re.search(r"百车故障数\s*(\d{2,3})", t) or [None, None])[1],
            "ppl": (re.search(r"查看\s*(\d+)\s*人质量评价", t) or [None, None])[1],
            "used_raw": used_s.split("询")[0].strip(),
            "used_lo": float(um.group(1)) if um else None,
            "used_hi": float(um.group(2)) if um else None,
            "dim_state": dim_state, "has_tags": bool(tag) and not tag.startswith("维度评价")}


def cmd_probe(limit):
    ids = load(IDS, [])
    if not ids:
        print("先跑 ids 模式"); return
    done = {r["id"] for r in load(RAW, [])}
    todo = [i for i in ids if i not in done][:limit]
    rows = load(RAW, [])
    print("已跑 %d，本轮 %d 个，开始 %s" % (len(done), len(todo), time.strftime("%H:%M:%S")), file=sys.stderr)
    for k, cid in enumerate(todo, 1):
        try:
            r = probe(cid)
            if r:
                rows.append(r)
        except Exception as e:
            print("fail %s %s" % (cid, e), file=sys.stderr)
        if k % 10 == 0:
            save(RAW, rows)
            print("  %d/%d 累计 %d 成功 %s" % (k, len(todo), len(rows), time.strftime("%H:%M:%S")), file=sys.stderr)
    save(RAW, rows)
    print("本轮结束，累计 %d 条" % len(rows))


# ---------- report ----------
def cmd_report():
    rows = load(RAW, [])
    n = len(rows)
    if not n:
        print("没有数据"); return
    def c(p): return sum(1 for r in rows if p(r))
    print("\n## 覆盖率（n=%d，无头 Chrome 执行 JS 后实测）\n" % n)
    print("| 字段 | 有可用值 | 覆盖率 |")
    print("|---|---|---|")
    for lab, p in [("厂商指导价（可解析区间）", lambda r: r["new_lo"]),
                   ("口碑评分", lambda r: r["score"]),
                   ("选车热度", lambda r: r["hot"]),
                   ("二手车价格（可解析区间）", lambda r: r["used_lo"]),
                   ("百车故障数", lambda r: r["fault"]),
                   ("质量评价参与人数", lambda r: r["ppl"]),
                   ("优缺点标签云", lambda r: r["has_tags"]),
                   ("维度评价有分值", lambda r: r["dim_state"] == "有分值")]:
        k = c(p); print("| %s | %d/%d | %.0f%% |" % (lab, k, n, 100.0 * k / n))

    sc = sorted(float(r["score"]) for r in rows if r["score"])
    if sc:
        import statistics as st
        print("\n## 口碑评分区分度\n")
        print("min %.2f / 中位 %.2f / max %.2f / **标准差 %.3f**；落在 [%.2f, %.2f] 的有 %d/%d（%.0f%%）" % (
            sc[0], st.median(sc), sc[-1], st.pstdev(sc), st.median(sc) - st.pstdev(sc),
            st.median(sc) + st.pstdev(sc),
            sum(1 for s in sc if st.median(sc) - st.pstdev(sc) <= s <= st.median(sc) + st.pstdev(sc)), n,
            100.0 * sum(1 for s in sc if st.median(sc) - st.pstdev(sc) <= s <= st.median(sc) + st.pstdev(sc)) / n))
        print("满分/异常高值：%s" % [(r["name"], r["score"]) for r in rows if r["score"] and float(r["score"]) >= 4.8])

    f_yes = sorted(int(r["ppl"]) for r in rows if r["fault"] and r["ppl"])
    f_no = sorted(int(r["ppl"]) for r in rows if not r["fault"] and r["ppl"])
    print("\n## 百车故障数门槛\n")
    print("- 有故障数且有参与人数的车系 %d 个，参与人数：%s" % (len(f_yes), f_yes))
    print("- 无故障数但有参与人数的车系 %d 个，参与人数：%s" % (len(f_no), f_no))
    if f_yes and f_no:
        print("- **有数据最低 %d 人 / 无数据最高 %d 人 → 门槛区间 [%d, %d]**" % (f_yes[0], f_no[-1], f_no[-1] + 1, f_yes[0] - 1))
        print("- 无故障数且连参与人数也没有的：%d 个" % c(lambda r: not r["fault"] and not r["ppl"]))

    u = [r for r in rows if r["used_lo"] and r["new_lo"]]
    bad = [r for r in u if r["used_lo"] < r["new_lo"] * 0.4]
    print("\n## 二手车价格口径荒谬度（n=%d 可对比）\n" % len(u))
    print("下界 < 新车起售价 40%% 的：%d 个（**%.0f%%**）\n" % (len(bad), 100.0 * len(bad) / len(u) if u else 0))
    print("| 车系 | 新车指导价 | 页面二手车区间 | 下界/新车 |")
    print("|---|---|---|---|")
    for r in sorted(bad, key=lambda x: x["used_lo"] / x["new_lo"])[:18]:
        print("| %s | %s | %s | %.0f%% |" % (r["name"], r["price_raw"], r["used_raw"], 100.0 * r["used_lo"] / r["new_lo"]))

    print("\n## 其他\n")
    print("- 无标签云：%s" % [r["name"] for r in rows if not r["has_tags"]])
    print("- 指导价不可解析：%s" % [r["name"] for r in rows if not r["new_lo"]])
    print("- 维度评价状态分布：%s" % {k: sum(1 for r in rows if r["dim_state"] == k) for k in set(r["dim_state"] for r in rows)})
    print("- 同时缺标签云与指导价：%s" % [r["name"] for r in rows if not r["has_tags"] and not r["new_lo"]])


def cmd_compare():
    """对比"我挑的热门 34 个" vs "全目录系统抽样 128 个"的字段覆盖率。
    如果全目录显著低于热门，说明数据覆盖与车型热度强相关 —— AI 在长尾上更容易翻车。"""
    hot = load(HOT, [])
    cat = load(RAW, [])
    if not hot or not cat:
        print("需要 raw_热门34.json 和 raw_字段实测.json 都有数据"); return
    fields = [("厂商指导价", lambda r: r["new_lo"]), ("口碑评分", lambda r: r["score"]),
              ("选车热度", lambda r: r["hot"]), ("二手车价格", lambda r: r["used_lo"]),
              ("百车故障数", lambda r: r["fault"]), ("质量评价参与人数", lambda r: r["ppl"]),
              ("优缺点标签云", lambda r: r["has_tags"]),
              ("维度评价有分值", lambda r: r["dim_state"] == "有分值")]
    print("\n## 覆盖率对比：我挑的热门车 vs 全目录系统抽样\n")
    print("| 字段 | 热门组 n=%d | 全目录组 n=%d | 差值 |" % (len(hot), len(cat)))
    print("|---|---|---|---|")
    for lab, p in fields:
        a = 100.0 * sum(1 for r in hot if p(r)) / len(hot)
        b = 100.0 * sum(1 for r in cat if p(r)) / len(cat)
        print("| %s | %.0f%% | %.0f%% | **%+.0fpp** |" % (lab, a, b, b - a))

    def bad(rows):
        u = [r for r in rows if r["used_lo"] and r["new_lo"]]
        return (sum(1 for r in u if r["used_lo"] < r["new_lo"] * 0.4), len(u))
    hb, hn = bad(hot); cb, cn = bad(cat)
    print("\n## 二手车价格口径荒谬率（下界 < 新车起售价 40%%）\n")
    print("| 组 | 荒谬/可对比 | 比例 |")
    print("|---|---|---|")
    print("| 热门组 | %d/%d | %.0f%% |" % (hb, hn, 100.0 * hb / hn if hn else 0))
    print("| 全目录组 | %d/%d | %.0f%% |" % (cb, cn, 100.0 * cb / cn if cn else 0))

    def thr(rows):
        yes = sorted(int(r["ppl"]) for r in rows if r["fault"] and r["ppl"])
        no = sorted(int(r["ppl"]) for r in rows if not r["fault"] and r["ppl"])
        return yes, no
    hy, hn2 = thr(hot); cy, cn2 = thr(cat)
    print("\n## 百车故障数门槛复验（全目录组是否有同样的 30 人分界）\n")
    print("- 全目录组 有故障数的参与人数：%s" % cy[:20])
    print("- 全目录组 无故障数但有参与人数：%s" % cn2[:20])
    if cy and cn2:
        print("- **有数据最低 %d / 无数据最高 %d → 门槛区间 [%d, %d]**" % (cy[0], cn2[-1], cn2[-1] + 1, cy[0] - 1))
        ok = cn2[-1] < cy[0]
        print("- 热门组门槛 [%d, %d]；两组%s" % (hn2[-1] + 1 if hn2 else 0, hy[0] - 1 if hy else 0,
                                            "一致，门槛结论可复现" if ok else "不一致，需说明"))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "report"
    arg = int(sys.argv[2]) if len(sys.argv) > 2 else (12 if mode == "ids" else 40)
    {"ids": cmd_ids, "probe": cmd_probe,
     "report": lambda *_: cmd_report(), "compare": lambda *_: cmd_compare()}[mode](arg)
