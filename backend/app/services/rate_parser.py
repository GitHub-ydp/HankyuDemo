"""运价文件解析引擎 — 支持 KMTC Excel / NVO FAK Excel
v2: 表头关键字动态匹配，消除硬编码列号/行号依赖
"""
import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.models import Port, Carrier, FreightRate, UploadLog, UploadStatus, SourceType, RateStatus


# ============================================================
# 港口名 → UN/LOCODE 映射（模糊匹配用）
# ============================================================
PORT_ALIAS_MAP: dict[str, str] = {
    # 韩国
    "busan": "KRPUS", "釜山": "KRPUS",
    "kwangyang": "KRKWA", "光阳": "KRKWA",
    "ulsan": "KRULS", "蔚山": "KRULS",
    "pohang": "KRPOH", "浦项": "KRPOH",
    "inchon": "KRINC", "仁川": "KRINC", "incheon": "KRINC",
    "gunsan": "KRKAN", "群山": "KRKAN",
    # 香港/台湾
    "hong kong": "HKHKG", "hongkong": "HKHKG", "香港": "HKHKG",
    "kaohsiung": "TWKHH", "高雄": "TWKHH",
    "keelung": "TWKEL", "基隆": "TWKEL",
    "taichung": "TWTXG", "台中": "TWTXG",
    "taipei": "TWTPE", "台北": "TWTPE", "桃园": "TWTPE",
    # 越南
    "haiphong": "VNHPH", "海防": "VNHPH", "hai phong": "VNHPH",
    "ho chi minh": "VNSGN", "hochiminh": "VNSGN", "胡志明": "VNSGN",
    "cat lai": "VNSGN", "卡莱": "VNSGN", "胡志明卡莱": "VNSGN",
    "vict": "VNSGN", "盖美": "VNSGN",
    "phnom penh": "KHPNH", "金边": "KHPNH",
    "sihanoukville": "KHSHV", "西哈努克": "KHSHV",
    # 泰国
    "bangkok": "THBKK", "曼谷": "THBKK", "bkk": "THBKK",
    "laem chabang": "THLCH", "林查班": "THLCH",
    "lat krabang": "THLKR", "拉卡帮": "THLKR",
    # 新加坡
    "singapore": "SGSIN", "新加坡": "SGSIN",
    # 马来西亚
    "pasir gudang": "MYPGU", "巴西古荡": "MYPGU",
    "penang": "MYPEN", "槟城": "MYPEN",
    "port kelang": "MYPKG", "巴生": "MYPKG", "port klang": "MYPKG",
    "巴生西": "MYPKG", "巴生北港": "MYPKG", "北港": "MYPKG",
    "tpp": "MYPGU",  # 柔佛 TPP = Tanjung Pelepas ≈ Pasir Gudang area
    "tanjung pelepas": "MYTPP",
    "kuantan": "MYKUA", "关丹": "MYKUA",
    "bintulu": "MYBTU", "名都鲁": "MYBTU",
    # 印度尼西亚
    "jakarta": "IDJKT", "雅加达": "IDJKT",
    "semarang": "IDSMG", "三宝垄": "IDSMG",
    "surabaya": "IDSUB", "泗水": "IDSUB",
    "belawan": "IDBLW", "勿拉湾": "IDBLW",
    "panjang": "IDPNJ", "潘姜": "IDPNJ",
    "palembang": "IDPLM", "巨港": "IDPLM",
    "pontianak": "IDPTK", "坤甸": "IDPTK",
    "batam": "IDBTM", "巴淡": "IDBTM",
    "banjarmasin": "IDBJM", "banjarmaisen": "IDBJM", "马辰": "IDBJM",
    "cikarang": "IDJKT", "西卡朗": "IDJKT",  # 西卡朗是雅加达内陆点
    # 印度
    "nhava sheva": "INNSA", "nhave sheva": "INNSA", "那瓦什瓦": "INNSA",
    "navi mumbai": "INNSA", "mumbai": "INNSA",
    "mundra": "INMUN", "蒙德拉": "INMUN",
    "hazira": "INHAZ", "哈兹拉": "INHAZ",
    "chennai": "INMAA", "钦奈": "INMAA",
    "kattupalli": "INKTP", "卡图帕利": "INKTP",
    "visakhapatnam": "INVTZ", "vizag": "INVTZ", "维沙卡": "INVTZ",
    "tuticorin": "INTUT", "图蒂戈林": "INTUT",
    "ahmedabad": "INAMD", "艾哈迈达巴德": "INAMD",
    "icd ahmedabad": "INAMD",
    # 巴基斯坦
    "karachi": "PKKHI", "卡拉奇": "PKKHI",
    # 中东
    "jebel ali": "AEJEA", "杰贝阿里": "AEJEA",
    "sohar": "OMSOH", "苏哈尔": "OMSOH",
    "abu dhabi": "AEAUH", "阿布扎比": "AEAUH",
    "kuwait": "KWKWI", "科威特": "KWKWI",
    "umm qasr": "IQUQR", "umm qasar": "IQUQR",
    "khalifa": "BHKBS", "khalifa bin salman": "BHKBS", "khalifabin salman": "BHKBS",
    "khalifabin salman port": "BHKBS", "khalifa bin salman port": "BHKBS", "哈里发港": "BHKBS",
    # 红海
    "jeddah": "SAJED", "吉达": "SAJED",
    "sokhna": "EGSOK", "苏赫纳": "EGSOK",
    "aqaba": "JOAQJ", "亚喀巴": "JOAQJ",
    # 非洲
    "mombasa": "KEMBA", "蒙巴萨": "KEMBA",
    "dar es salaam": "TZDAR", "达累斯萨拉姆": "TZDAR",
    # 墨西哥
    "manzanillo": "MXMAN", "曼萨尼约": "MXMAN",
    # 中国
    "shanghai": "CNSHA", "上海": "CNSHA",
    "ningbo": "CNNGB", "宁波": "CNNGB",
    "qingdao": "CNTAO", "青岛": "CNTAO",
    "xiamen": "CNXMN", "厦门": "CNXMN",
    "yantian": "CNYTN", "盐田": "CNYTN",
    "shenzhen": "CNYTN", "深圳": "CNYTN",
    # 美国 — 港口
    "los angeles": "USLAX", "洛杉矶": "USLAX", "long beach": "USLGB", "长滩": "USLGB",
    "oakland": "USOAK", "seattle": "USSEA", "tacoma": "USTAC",
    "new york": "USNYC", "纽约": "USNYC", "savannah": "USSAV",
    "houston": "USHOU", "charleston": "USCHS",
    "norfolk": "USNOR", "boston": "USBOS",
    "baltimore": "USBAL", "miami": "USMIA",
    "jacksonville": "USJAX",
    "honolulu": "USHNL",
    "portland": "USPDX",
    # 美国 — 内陆城市（IPI）
    "chicago": "USCHI", "atlanta": "USATL", "dallas": "USDAL",
    "memphis": "USMEM", "detroit": "USDET", "minneapolis": "USMIN",
    "charlotte": "USCLT", "columbus": "USCMH", "nashville": "USBNA",
    "kansas city": "USMKC", "st louis": "USSTL", "st. louis": "USSTL",
    "denver": "USDEN", "salt lake city": "USSLC",
    "mobile": "USMOB", "new orleans": "USMSY",
    "san antonio": "USSAT", "el paso": "USELP",
    "phoenix": "USPHX", "reno": "USRNO",
    "cincinnati": "USCVG", "cleveland": "USCLV",
    "pittsburgh": "USPIT", "buffalo": "USBUF",
    "louisville": "USLUI", "indianapolis": "USIND",
    "harrisburg": "USMDT", "richmond": "USRIC",
    "huntsville": "USHSV",
    # 加拿大
    "vancouver": "CAVAN", "toronto": "CATOR", "montreal": "CAMTR",
    "halifax": "CAHAL", "calgary": "CACAL", "edmonton": "CAEDM",
    "winnipeg": "CAWNP", "saskatoon": "CASAS",
}

# NVO FAK 中的 Origin code → UN/LOCODE
ORIGIN_CODE_MAP: dict[str, str] = {
    "SGSIN": "SGSIN", "KRPUS": "KRPUS", "VNSGN": "VNSGN",
    "VNCMP": "VNSGN", "HKHKG": "HKHKG", "TWKHH": "TWKHH",
    "THLCH": "THLCH", "CNNGB": "CNNGB", "CNTAO": "CNTAO",
    "CNSHA": "CNSHA", "CNXMN": "CNXMN", "CNYTN": "CNYTN",
    "TWTPE": "TWTPE", "KRKAN": "KRKAN",
}

# 泰国码头别名（BKK-BMT, BKK-SCT 等）
_TERMINAL_SUFFIXES = [
    " PAT", " UNITHAI", " TCTB", " BMT", " SCT",
    " LCB1", " LCB2", " LCMT", " SRIRACHA",
]
_TERMINAL_CONNECTORS = ["-", " - ", "–"]


def _resolve_port(name_raw: str, db: Session) -> Port | None:
    """将港口名/代码解析为 Port 对象，4 级策略"""
    if not name_raw or not name_raw.strip():
        return None

    name = name_raw.strip()

    # 1. 精确匹配 UN/LOCODE（5位大写字母）
    if len(name) == 5 and name.isalpha() and name.isupper():
        port = db.query(Port).filter(Port.un_locode == name).first()
        if port:
            return port

    # 2. 去除 "City, STATE" 后缀（如 "Mobile, AL" → "Mobile"）
    name_no_state = re.sub(r",\s*[A-Z]{2}$", "", name).strip()
    if name_no_state != name:
        # 递归尝试匹配去掉州代码后的名字
        result = _resolve_port(name_no_state, db)
        if result:
            return result

    # 3. 提取英文名部分（如 "BUSAN/釜山" → "busan"）
    clean = name.split("/")[0].strip()
    # 去掉括号内容
    clean = re.sub(r"[（(].*?[）)]", "", clean).strip()

    # 去掉终端名后缀（PAT, UNITHAI, TCTB, BMT, SCT 等）
    for suffix in _TERMINAL_SUFFIXES:
        if clean.upper().endswith(suffix):
            clean = clean[: -len(suffix)].strip()
            break

    # 处理连字符连接的终端名（如 BKK-BMT, BKK-SCT）
    for conn in _TERMINAL_CONNECTORS:
        if conn in clean:
            parts = clean.split(conn)
            # 取第一段作为城市名
            clean = parts[0].strip()
            break

    key = clean.lower()
    if key in PORT_ALIAS_MAP:
        locode = PORT_ALIAS_MAP[key]
        return db.query(Port).filter(Port.un_locode == locode).first()

    # 3. 中文名匹配
    cn_part = name.split("/")[-1].strip() if "/" in name else ""
    cn_clean = re.sub(r"[（(].*?[）)]", "", cn_part).strip()
    if cn_clean and cn_clean in PORT_ALIAS_MAP:
        locode = PORT_ALIAS_MAP[cn_clean]
        return db.query(Port).filter(Port.un_locode == locode).first()

    # 4. 模糊匹配 — 数据库 LIKE（英文和中文）
    port = db.query(Port).filter(Port.name_en.ilike(f"%{clean}%")).first()
    if port:
        return port
    if cn_clean:
        port = db.query(Port).filter(Port.name_cn.ilike(f"%{cn_clean}%")).first()
    return port


def _safe_decimal(val: Any) -> Decimal | None:
    """安全转换为 Decimal"""
    if val is None or val == "" or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, str):
        val = val.strip()
        if val in ("含", "-", "N/A", "", "—", "n/a", "inc", "incl"):
            return None
        val = val.replace(",", "")
        # 处理公式引用（=F6 等）
        if val.startswith("="):
            return None
    try:
        d = Decimal(str(val))
        if d < 0:
            return None
        return d
    except (InvalidOperation, ValueError):
        return None


def _parse_transit_days(remark: str) -> tuple[int | None, bool]:
    """从备注中提取航行天数和是否直达"""
    if not remark:
        return None, True
    is_direct = "直达" in remark
    m = re.search(r"(\d+)\s*天", remark)
    if m:
        return int(m.group(1)), is_direct
    if "中转" in remark:
        is_direct = False
    return None, is_direct


def _is_numeric(val: Any) -> bool:
    """判断一个值是否是数字（用于区分数据行和标题行）"""
    if isinstance(val, (int, float)):
        return not pd.isna(val)
    if isinstance(val, str):
        try:
            float(val.replace(",", ""))
            return True
        except ValueError:
            return False
    return False


# ============================================================
# KMTC Excel 解析器 (v2: 动态表头匹配)
# ============================================================
def parse_kmtc_excel(file_path: str, db: Session) -> dict:
    """
    解析 KMTC 运价表 Excel — 通过表头关键字动态定位列
    """
    batch_id = f"KMTC-{uuid.uuid4().hex[:8]}"
    df = pd.read_excel(file_path, header=None)

    # --- 第1步：找到表头行 ---
    main_header_row = None
    sub_header_row = None
    for i in range(min(15, len(df))):
        row_vals = [str(v).strip() for v in df.iloc[i] if pd.notna(v)]
        row_text = " ".join(row_vals).lower()
        if "港口" in row_text or ("o/f" in row_text and ("baf" in row_text or "lss" in row_text)):
            main_header_row = i
        if main_header_row is not None and i > main_header_row:
            if any("20" in str(v) for v in df.iloc[i] if pd.notna(v)):
                sub_header_row = i
                break

    if main_header_row is None or sub_header_row is None:
        return {"batch_id": batch_id, "parsed_rows": [],
                "warnings": ["无法识别 KMTC 表头行，请检查文件格式"]}

    # --- 第2步：从 2 行合并表头建立列映射 ---
    main_cells = [str(v).strip() if pd.notna(v) else "" for v in df.iloc[main_header_row]]
    sub_cells = [str(v).strip() if pd.notna(v) else "" for v in df.iloc[sub_header_row]]

    # 识别主表头中的分组起始列
    col_map = {
        "port": None,       # 港口
        "schedule": None,   # 船期
        "company": None,    # 船公司
        "route": None,      # 航线
        "of_start": None,   # O/F 分组起始列
        "baf_start": None,  # BAF 分组起始列
        "lss_start": None,  # LSS 分组起始列
        "date": None,       # 生效日
        "remark": None,     # 备注
    }

    for ci, cell in enumerate(main_cells):
        cl = cell.lower()
        if "港口" in cl or "port" in cl:
            col_map["port"] = ci
        elif "船期" in cl or "schedule" in cl:
            col_map["schedule"] = ci
        elif "船公司" in cl or "carrier" in cl:
            col_map["company"] = ci
        elif "航线" in cl or "route" in cl or "service" in cl:
            col_map["route"] = ci
        elif "o/f" in cl or "ocean" in cl:
            col_map["of_start"] = ci
        elif "baf" in cl or "wrs" in cl:
            col_map["baf_start"] = ci
        elif "lss" in cl:
            col_map["lss_start"] = ci
        elif "生效" in cl or "effective" in cl:
            col_map["date"] = ci
        elif "備考" in cl or "备注" in cl or "remark" in cl:
            col_map["remark"] = ci

    # 从子表头精确定位各柜型列
    # O/F 组: of_start 开始的连续列含 20GP, 40GP, 40HQ
    of_20, of_40, of_hq = None, None, None
    baf_20, baf_40 = None, None
    lss_20, lss_40 = None, None

    # 遍历子表头，按从左到右顺序分配
    group_20_indices = []  # 所有包含 "20" 的列
    group_40_indices = []  # 所有包含 "40" 但不含 "H" 的列
    group_hq_indices = []  # 所有包含 "HQ" 或 "HC" 的列

    for ci, cell in enumerate(sub_cells):
        cu = cell.upper()
        if "20" in cu:
            group_20_indices.append(ci)
        elif "40" in cu and "H" not in cu:
            group_40_indices.append(ci)
        elif "HQ" in cu or "HC" in cu or "40H" in cu:
            group_hq_indices.append(ci)

    # 按顺序分配：第1个20是O/F, 第2个是BAF, 第3个是LSS
    if len(group_20_indices) >= 1:
        of_20 = group_20_indices[0]
    if len(group_20_indices) >= 2:
        baf_20 = group_20_indices[1]
    if len(group_20_indices) >= 3:
        lss_20 = group_20_indices[2]

    # 40GP: O/F 40 是紧跟 O/F 20 的
    if of_20 is not None:
        of_40 = of_20 + 1  # 40GP 紧跟 20GP
        of_hq = of_20 + 2  # 40HQ 紧跟 40GP
    if baf_20 is not None:
        baf_40 = baf_20 + 1
    if lss_20 is not None:
        lss_40 = lss_20 + 1

    if of_20 is None:
        return {"batch_id": batch_id, "parsed_rows": [],
                "warnings": ["无法在 KMTC 表头中定位 O/F 20GP 列"]}

    # port 列默认为 0
    port_col = col_map["port"] if col_map["port"] is not None else 0
    date_col = col_map["date"]
    remark_col = col_map["remark"]

    # --- 第3步：确定起运港和船司 ---
    from app.services.email_text_parser import _match_carrier
    origin_port = db.query(Port).filter(Port.un_locode == "CNSHA").first()
    carrier = _match_carrier("KMTC", db)  # 不存在会自动建一条

    # 尝试从文件内容中检测起运港
    file_text = " ".join(str(v) for v in df.iloc[:5].values.flatten() if pd.notna(v))
    if "宁波" in file_text or "NINGBO" in file_text.upper():
        origin_port = db.query(Port).filter(Port.un_locode == "CNNGB").first() or origin_port
    elif "青岛" in file_text or "QINGDAO" in file_text.upper():
        origin_port = db.query(Port).filter(Port.un_locode == "CNTAO").first() or origin_port

    if not origin_port or not carrier:
        return {"batch_id": batch_id, "parsed_rows": [],
                "warnings": ["缺少起运港基础数据，请先运行 seed_data"]}

    # --- 第4步：逐行解析数据 ---
    parsed_rows = []
    warnings = []
    data_start = sub_header_row + 1

    for i in range(data_start, len(df)):
        row = df.iloc[i]
        port_name = str(row[port_col]) if pd.notna(row[port_col]) else ""

        # 跳过非数据行：O/F 20GP 不是数字的行（区域标题行、备注行等）
        if not _is_numeric(row[of_20]):
            continue

        # 解析目的港
        dest_port = _resolve_port(port_name, db)
        if not dest_port:
            warnings.append(f"Row {i}: 无法识别港口 '{port_name}'")
            continue

        # 解析备注
        remark = ""
        if remark_col is not None and pd.notna(row[remark_col]):
            remark = str(row[remark_col])
        transit_days, is_direct = _parse_transit_days(remark)

        # 解析有效日期
        valid_from = None
        if date_col is not None and pd.notna(row[date_col]):
            v = row[date_col]
            if isinstance(v, datetime):
                valid_from = v.date()
            elif isinstance(v, date):
                valid_from = v

        parsed_rows.append({
            "carrier_id": carrier.id,
            "origin_port_id": origin_port.id,
            "origin_port_name": f"{origin_port.name_en}/{origin_port.name_cn}",
            "destination_port_id": dest_port.id,
            "destination_port_name": f"{dest_port.name_en}/{dest_port.name_cn}",
            "container_20gp": _safe_decimal(row[of_20]),
            "container_40gp": _safe_decimal(row[of_40]) if of_40 is not None else None,
            "container_40hq": _safe_decimal(row[of_hq]) if of_hq is not None else None,
            "container_45": None,
            "baf_20": _safe_decimal(row[baf_20]) if baf_20 is not None else None,
            "baf_40": _safe_decimal(row[baf_40]) if baf_40 is not None else None,
            "lss_20": _safe_decimal(row[lss_20]) if lss_20 is not None else None,
            "lss_40": _safe_decimal(row[lss_40]) if lss_40 is not None else None,
            "currency": "USD",
            "valid_from": valid_from,
            "valid_to": None,
            "transit_days": transit_days,
            "is_direct": is_direct,
            "remarks": remark if remark else None,
            "source_type": "excel",
            "source_file": str(file_path).split("/")[-1].split("\\")[-1],
            "upload_batch_id": batch_id,
        })

    return {
        "batch_id": batch_id,
        "file_name": str(file_path).split("/")[-1].split("\\")[-1],
        "source_type": "excel",
        "carrier_code": "KMTC",
        "parsed_rows": parsed_rows,
        "total_rows": len(parsed_rows),
        "warnings": warnings,
    }


# ============================================================
# NVO FAK Excel 解析器 (v2: 自动提取有效日期)
# ============================================================
def _extract_effective_dates(df: pd.DataFrame) -> tuple[date | None, date | None]:
    """从 NVO FAK 的前几行中提取 Effective from ... to ... 日期"""
    year = date.today().year  # 默认当年

    for i in range(min(5, len(df))):
        row_text = " ".join(str(v) for v in df.iloc[i] if pd.notna(v))

        # 提取年份（如 "NVO FAK 2026"）
        ym = re.search(r"20\d{2}", row_text)
        if ym:
            year = int(ym.group())

        # 提取日期范围 "Effective from 3/20 to 3/31" 或 "Effective from 03/20 to 03/31"
        m = re.search(
            r"[Ee]ffective\s+(?:from\s+)?(\d{1,2})[/\-](\d{1,2})\s+to\s+(\d{1,2})[/\-](\d{1,2})",
            row_text,
        )
        if m:
            try:
                from_month, from_day = int(m.group(1)), int(m.group(2))
                to_month, to_day = int(m.group(3)), int(m.group(4))
                return date(year, from_month, from_day), date(year, to_month, to_day)
            except ValueError:
                continue

    return None, None


def parse_nvo_fak_excel(file_path: str, db: Session, sheet_name: str | None = None) -> dict:
    """解析 NVO FAK 运价表 Excel（多 Sheet），自动提取有效日期"""
    from app.services.email_text_parser import _create_carrier
    batch_id = f"NVOFAK-{uuid.uuid4().hex[:8]}"
    carrier = db.query(Carrier).filter(Carrier.code == "NVO_FAK").first()
    if not carrier:
        carrier = _create_carrier(db, code="NVO_FAK", name_en="NVO FAK (Consolidated)", name_cn="NVO FAK整合")

    xls = pd.ExcelFile(file_path)
    sheets_to_parse = [sheet_name] if sheet_name else xls.sheet_names
    sheets_to_parse = [s for s in sheets_to_parse if s.lower() not in ("arbitrary",)]

    all_sheets = []
    all_warnings = []

    for sname in sheets_to_parse:
        df_raw = pd.read_excel(xls, sheet_name=sname, header=None)

        # 自动提取有效日期
        valid_from, valid_to = _extract_effective_dates(df_raw)

        # 找表头行（包含 "Origin"）
        header_row = None
        for i in range(min(15, len(df_raw))):
            row_vals = [str(v).strip().lower() for v in df_raw.iloc[i] if pd.notna(v)]
            if any("origin" in v for v in row_vals):
                header_row = i
                break

        if header_row is None:
            all_warnings.append(f"Sheet '{sname}': 找不到表头行")
            continue

        df = pd.read_excel(xls, sheet_name=sname, header=header_row)

        # 标准化列映射（用更精确的规则）
        col_map = {}
        for c in df.columns:
            cl = str(c).strip().lower()
            if cl.startswith("origin") or cl == "origin":
                col_map["origin"] = c
            elif "discharge" in cl:
                col_map["pod"] = c
            elif cl.startswith("destination") or cl == "destination":
                col_map["destination"] = c
            elif re.match(r"^20\s*(ft|'|gp)?$", cl):
                col_map["20ft"] = c
            elif re.match(r"^40\s*(ft|'|gp)?$", cl) and "h" not in cl:
                col_map["40ft"] = c
            elif re.match(r"^(hc|40\s*h[cq]?)$", cl):
                col_map["hc"] = c
            elif re.match(r"^45\s*(ft|')?$", cl):
                col_map["45ft"] = c
            elif cl.startswith("service"):
                col_map["service"] = c
            elif cl.startswith("coast"):
                col_map["coast"] = c

        if "20ft" not in col_map:
            all_warnings.append(f"Sheet '{sname}': 找不到 20ft 费率列")
            continue

        parsed_rows = []
        for idx, row in df.iterrows():
            # 检测是否进入 IPI/Remark 等非标准区域，立即停止
            first_cell = str(row.iloc[0]) if pd.notna(row.iloc[0]) else ""
            if any(kw in first_cell.lower() for kw in ("remark", "ipi", "ripi", "add-on", "note:")):
                break

            origin_raw = str(row.get(col_map.get("origin", ""), "")) if col_map.get("origin") else ""
            dest_raw = str(row.get(col_map.get("destination", ""), "")) if col_map.get("destination") else ""

            rate_20 = row.get(col_map.get("20ft", ""), None)
            if pd.isna(rate_20) if hasattr(rate_20, '__class__') else (rate_20 is None):
                continue
            rate_20 = _safe_decimal(rate_20)
            if rate_20 is None:
                continue

            # 解析 origin（可能是 "KRPUS,KRKAN" 多代码）
            origin_codes = [c.strip() for c in origin_raw.split(",") if c.strip()]
            if not origin_codes:
                continue

            # 解析 destination
            dest_port = _resolve_port(dest_raw.strip(), db)
            if not dest_port:
                pod_raw = str(row.get(col_map.get("pod", ""), "")) if col_map.get("pod") else ""
                dest_port = _resolve_port(pod_raw.strip().split(",")[0].strip(), db)
                if not dest_port:
                    all_warnings.append(f"Sheet '{sname}' Row {idx}: 无法识别目的港 '{dest_raw}'")
                    continue

            service = str(row.get(col_map.get("service", ""), "")) if col_map.get("service") else None
            if service and (str(service).lower() == "nan" or service.strip() == ""):
                service = None

            for oc in origin_codes:
                locode = ORIGIN_CODE_MAP.get(oc.upper(), oc.upper())
                origin_port = db.query(Port).filter(Port.un_locode == locode).first()
                if not origin_port:
                    continue

                parsed_rows.append({
                    "carrier_id": carrier.id,
                    "origin_port_id": origin_port.id,
                    "origin_port_name": f"{origin_port.name_en}/{origin_port.name_cn}",
                    "destination_port_id": dest_port.id,
                    "destination_port_name": f"{dest_port.name_en}/{dest_port.name_cn}",
                    "container_20gp": rate_20,
                    "container_40gp": _safe_decimal(row.get(col_map.get("40ft", ""), None)),
                    "container_40hq": _safe_decimal(row.get(col_map.get("hc", ""), None)),
                    "container_45": _safe_decimal(row.get(col_map.get("45ft", ""), None)),
                    "baf_20": None,
                    "baf_40": None,
                    "lss_20": None,
                    "lss_40": None,
                    "currency": "USD",
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                    "transit_days": None,
                    "is_direct": True,
                    "remarks": None,
                    "service_code": service,
                    "source_type": "excel",
                    "source_file": str(file_path).split("/")[-1].split("\\")[-1],
                    "upload_batch_id": batch_id,
                })

        all_sheets.append({
            "sheet_name": sname,
            "parsed_rows": parsed_rows,
            "total_rows": len(parsed_rows),
        })

    return {
        "batch_id": batch_id,
        "file_name": str(file_path).split("/")[-1].split("\\")[-1],
        "source_type": "excel",
        "carrier_code": "NVO_FAK",
        "sheets": all_sheets,
        "total_rows": sum(s["total_rows"] for s in all_sheets),
        "warnings": all_warnings,
    }


# ============================================================
# 通用：自动检测文件类型并解析
# ============================================================
def detect_and_parse(file_path: str, db: Session) -> dict:
    """自动检测 Excel 文件类型并调用对应解析器"""
    # 多策略检测：先看文件名，再看内容
    fname = str(file_path).lower()
    if "kmtc" in fname or "高丽" in fname:
        return parse_kmtc_excel(file_path, db)
    if "nvo" in fname or "fak" in fname:
        return parse_nvo_fak_excel(file_path, db)

    # 内容检测
    try:
        df_peek = pd.read_excel(file_path, header=None, nrows=10)
        content = " ".join(str(v) for v in df_peek.values.flatten() if pd.notna(v))
        content_upper = content.upper()

        if "KMTC" in content_upper or "高丽海运" in content or "KOREA MARINE" in content_upper:
            return parse_kmtc_excel(file_path, db)
        elif "NVO FAK" in content_upper or "NVO" in content_upper and "FAK" in content_upper:
            return parse_nvo_fak_excel(file_path, db)
        elif "BASE PORT" in content_upper or "EFFECTIVE FROM" in content_upper:
            return parse_nvo_fak_excel(file_path, db)
    except Exception:
        pass

    return {"error": "无法识别的 Excel 格式，支持 KMTC 运价表和 NVO FAK 格式", "detected_content": ""}


# ============================================================
# 确认导入：将解析结果写入数据库
# ============================================================
def import_parsed_rates(
    parsed_data: dict,
    db: Session,
    confirmed_indices: list[int] | None = None,
) -> dict:
    """将解析后的费率数据写入数据库"""
    batch_id = parsed_data["batch_id"]

    all_rows = []
    if "parsed_rows" in parsed_data:
        all_rows = parsed_data["parsed_rows"]
    elif "sheets" in parsed_data:
        for sheet in parsed_data["sheets"]:
            all_rows.extend(sheet["parsed_rows"])

    if confirmed_indices is not None:
        all_rows = [all_rows[i] for i in confirmed_indices if i < len(all_rows)]

    imported = 0
    errors = []

    for idx, row_data in enumerate(all_rows):
        try:
            # 防御性校验：必填外键缺失则跳过整行（不让 NOT NULL 报错炸掉整批）
            if not row_data.get("carrier_id"):
                errors.append(f"Row {idx}: 缺少 carrier_id（船司未识别），已跳过")
                continue
            if not row_data.get("origin_port_id") or not row_data.get("destination_port_id"):
                errors.append(f"Row {idx}: 缺少起运港或目的港，已跳过")
                continue
            rate = FreightRate(
                carrier_id=row_data["carrier_id"],
                origin_port_id=row_data["origin_port_id"],
                destination_port_id=row_data["destination_port_id"],
                service_code=row_data.get("service_code"),
                container_20gp=row_data.get("container_20gp"),
                container_40gp=row_data.get("container_40gp"),
                container_40hq=row_data.get("container_40hq"),
                container_45=row_data.get("container_45"),
                baf_20=row_data.get("baf_20"),
                baf_40=row_data.get("baf_40"),
                lss_20=row_data.get("lss_20"),
                lss_40=row_data.get("lss_40"),
                currency=row_data.get("currency", "USD"),
                valid_from=row_data.get("valid_from"),
                valid_to=row_data.get("valid_to"),
                transit_days=row_data.get("transit_days"),
                is_direct=row_data.get("is_direct", True),
                remarks=row_data.get("remarks"),
                source_type=SourceType(row_data.get("source_type", "excel")),
                source_file=row_data.get("source_file"),
                upload_batch_id=batch_id,
                status=RateStatus.active,
            )
            db.add(rate)
            imported += 1
        except Exception as e:
            errors.append(f"Row {idx}: {str(e)}")

    log = UploadLog(
        batch_id=batch_id,
        file_name=parsed_data.get("file_name", ""),
        file_type=parsed_data.get("file_type", "xlsx"),
        source_type=parsed_data.get("source_type", "excel"),
        records_parsed=len(all_rows),
        records_imported=imported,
        status=UploadStatus.completed if not errors else UploadStatus.failed,
        error_message="\n".join(errors) if errors else None,
    )
    db.add(log)
    db.commit()

    return {
        "batch_id": batch_id,
        "records_parsed": len(all_rows),
        "records_imported": imported,
        "errors": errors,
    }
