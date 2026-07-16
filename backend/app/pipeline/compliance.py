"""合规校验：扫描设定文档里的真实国家/城市/品牌，给出替换指令。

思路：
  1. 关键词词典（真实地名、人名、品牌）
  2. 扫描函数返回"issues"：[(原文, 类别, 建议替换)]
  3. 重写 prompt 模板：把 issues 塞回 LLM，让它就地替换
"""
import re
from typing import Dict, List, Tuple

# 真实地理 / 政治实体 - 不区分大小写
GEO_TERMS: List[Tuple[str, str]] = [
    # 真实国名（注意保留朝代/历史国名作为虚构没关系）
    ("中国", "real_country"),
    ("中华人民共和国", "real_country"),
    ("中华民国", "real_sensitive"),
    ("PRC", "real_country"),
    ("CHINA", "real_country"),
    # 中国省份 / 直辖市 / 特别行政区（重点敏感）
    ("北京市", "real_city"),
    ("上海", "real_city"),
    ("上海市", "real_city"),
    ("天津", "real_city"),
    ("重庆市", "real_city"),
    ("广州", "real_city"),
    ("深圳", "real_city"),
    ("杭州", "real_city"),
    ("南京", "real_city"),
    ("武汉", "real_city"),
    ("成都", "real_city"),
    ("西安", "real_city"),
    ("哈尔滨", "real_city"),
    ("长春", "real_city"),
    ("沈阳", "real_city"),
    ("大连", "real_city"),
    ("青岛", "real_city"),
    ("厦门", "real_city"),
    ("苏州", "real_city"),
    ("郑州", "real_city"),
    ("长沙", "real_city"),
    ("济南", "real_city"),
    ("合肥", "real_city"),
    ("福州", "real_city"),
    ("南昌", "real_city"),
    ("昆明", "real_city"),
    ("南宁", "real_city"),
    ("贵阳", "real_city"),
    ("兰州", "real_city"),
    ("西宁", "real_city"),
    ("银川", "real_city"),
    ("乌鲁木齐", "real_city"),
    ("拉萨", "real_sensitive"),
    ("呼和浩特", "real_city"),
    ("太原", "real_city"),
    ("石家庄", "real_city"),
    ("香港", "real_sensitive"),
    ("Hong Kong", "real_sensitive"),
    ("澳门", "real_sensitive"),
    ("台湾", "real_sensitive"),
    ("Taiwan", "real_sensitive"),
    ("台北", "real_sensitive"),
    ("藏南", "real_sensitive"),
    ("新疆", "real_sensitive"),
    ("西藏", "real_sensitive"),
    ("内蒙古", "real_sensitive"),
    ("黄浦江", "real_geo"),
    ("长江", "real_geo"),
    ("黄河", "real_geo"),
    ("珠江", "real_geo"),
    ("华山", "real_geo"),
    ("泰山", "real_geo"),
    # 真实国家（其他国家，简单列重点）
    ("United States", "real_country"),
    ("America", "real_country"),
    ("USA", "real_country"),
    ("美国", "real_country"),
    ("Russia", "real_country"),
    ("Russia", "real_country"),
    ("俄罗斯", "real_country"),
    ("Japan", "real_country"),
    ("日本", "real_country"),
    ("Korea", "real_country"),
    ("韩国", "real_country"),
    ("朝鲜", "real_country"),
    ("Vietnam", "real_country"),
    ("越南", "real_country"),
    ("Thailand", "real_country"),
    ("泰国", "real_country"),
    ("Singapore", "real_country"),
    ("新加坡", "real_country"),
    ("Malaysia", "real_country"),
    ("马来西亚", "real_country"),
    ("Indonesia", "real_country"),
    ("印度尼西亚", "real_country"),
    ("India", "real_country"),
    ("印度", "real_country"),
    ("Pakistan", "real_country"),
    ("巴基斯坦", "real_country"),
    ("Iran", "real_country"),
    ("伊朗", "real_country"),
    ("Iraq", "real_country"),
    ("伊拉克", "real_country"),
    ("Israel", "real_country"),
    ("以色列", "real_country"),
    ("Palestine", "real_sensitive"),
    ("巴勒斯坦", "real_sensitive"),
    ("Ukraine", "real_country"),
    ("乌克兰", "real_country"),
    ("Syria", "real_country"),
    ("叙利亚", "real_country"),
]

# 真实品牌名（高频）
BRAND_TERMS: List[Tuple[str, str]] = [
    ("阿里巴巴", "real_brand"),
    ("Alibaba", "real_brand"),
    ("腾讯", "real_brand"),
    ("Tencent", "real_brand"),
    ("微信", "real_brand"),
    ("WeChat", "real_brand"),
    ("华为", "real_brand"),
    ("Huawei", "real_brand"),
    ("字节跳动", "real_brand"),
    ("ByteDance", "real_brand"),
    ("抖音", "real_brand"),
    ("TikTok", "real_brand"),
    ("百度", "real_brand"),
    ("Baidu", "real_brand"),
    ("京东", "real_brand"),
    ("美团", "real_brand"),
    ("Apple", "real_brand"),
    ("苹果公司", "real_brand"),
    ("Google", "real_brand"),
    ("谷歌", "real_brand"),
    ("Microsoft", "real_brand"),
    ("微软", "real_brand"),
    ("Meta", "real_brand"),
    ("Facebook", "real_brand"),
    ("Amazon", "real_brand"),
    ("亚马逊", "real_brand"),
    ("Tesla", "real_brand"),
    ("特斯拉", "real_brand"),
    ("Nvidia", "real_brand"),
    ("英伟达", "real_brand"),
    ("Samsung", "real_brand"),
    ("三星", "real_brand"),
]


# 强敏感词（即使出现在小说 context 里也直接报）
HARD_SENSITIVE: List[Tuple[str, str]] = [
    ("习近平", "real_person"),
    ("Xi Jinping", "real_person"),
    ("毛泽东", "real_person"),
    ("邓小平", "real_person"),
    ("蒋介石", "real_person"),
    ("胡锦涛", "real_person"),
    ("温家宝", "real_person"),
    ("李克强", "real_person"),
    ("习近平思想", "real_political"),
    ("习近平新时代中国特色社会主义", "real_political"),
    ("六四", "real_sensitive_event"),
    ("Tiananmen", "real_sensitive_event"),
    ("天安门事件", "real_sensitive_event"),
    ("法轮功", "real_sensitive_org"),
    ("Falun Gong", "real_sensitive_org"),
]


def scan_text(text: str) -> List[Dict]:
    """扫描文本，返回 issues 列表。

    返回格式: [{"term": "中国", "category": "real_country", "positions": [0, 5]}, ...]
    """
    issues: List[Dict] = []
    if not text:
        return issues

    seen_terms = set()

    all_terms = HARD_SENSITIVE + GEO_TERMS + BRAND_TERMS
    for term, category in all_terms:
        # 用单词边界保护，避免误伤（中文无需）
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        positions = [m.start() for m in pattern.finditer(text)]
        if positions:
            key = (term, category)
            if key not in seen_terms:
                issues.append({
                    "term": term,
                    "category": category,
                    "count": len(positions),
                })
                seen_terms.add(key)

    return issues


def scan_result(result: dict) -> List[Dict]:
    """扫描 worldbuilding agent 返回的整个 result。"""
    parts: List[str] = []

    # setting_document
    doc = result.get("setting_document", "")
    if isinstance(doc, str):
        parts.append(doc)

    # constraints
    constraints = result.get("constraints", {})
    if isinstance(constraints, dict):
        for k in ("hard", "soft"):
            v = constraints.get(k, [])
            if isinstance(v, list):
                parts.extend(str(x) for x in v)

    # conflict_seeds
    seeds = result.get("conflict_seeds", [])
    if isinstance(seeds, list):
        for seed in seeds:
            if isinstance(seed, dict):
                parts.append(str(seed.get("name", "")))
                parts.append(str(seed.get("description", "")))
                parts.append(str(seed.get("stake", "")))

    all_issues = []
    for p in parts:
        all_issues.extend(scan_text(p))

    # 去重（同一 term 多次出现合并）
    dedup = {}
    for i in all_issues:
        key = i["term"]
        if key not in dedup:
            dedup[key] = {"term": i["term"], "category": i["category"], "count": 0}
        dedup[key]["count"] += i["count"]
    return list(dedup.values())


def build_rewrite_prompt(issues: List[Dict]) -> str:
    """构造重写 prompt：把 issues 列表告诉 LLM，让它就地替换。"""
    if not issues:
        return ""

    lines = ["你刚才生成的世界观中包含以下不合规内容：", ""]
    for i in issues:
        lines.append(f"- 「{i['term']}」（分类: {i['category']}，出现 {i['count']} 次）")
    lines.append("")
    lines.append("请在不破坏整体设定结构的前提下，把上述真实名称全部替换为虚构等价物：")
    lines.append("- 真实国家 → 虚构国家名")
    lines.append("- 真实城市/省份/地区 → 虚构或重新命名")
    lines.append("- 真实品牌 → 完全去除或换成虚构")
    lines.append("- 真实人物 → 完全去除或换成虚构")
    lines.append("")
    lines.append("替换原则：")
    lines.append("- 整体语义尽量保持一致（如果原文写『中国沿海发达城市』，可改写为『某个虚构东方国度的沿海发达城市』）")
    lines.append("- 设定文档 / constraints / conflict_seeds 三个字段都要改")
    lines.append("- 仍然只输出 JSON，不要任何额外说明")
    return "\n".join(lines)


def is_compliant(result: dict) -> bool:
    """判定一个生成结果是否完全合规（无 issues）。"""
    return len(scan_result(result)) == 0
