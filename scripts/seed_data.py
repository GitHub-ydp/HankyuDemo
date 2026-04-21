"""初始化港口和船司种子数据"""
import sys
from pathlib import Path

# 添加项目根到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy.orm import Session
from app.core.database import engine, init_db, SessionLocal
from app.models import Port, Carrier, CarrierType


# ============================================================
# 港口字典 — 从 KMTC/NVO FAK 实际数据提取 + 补充常用港口
# ============================================================
PORTS = [
    # 中国 (起运港)
    ("CNSHA", "Shanghai", "上海", "China", "East Asia"),
    ("CNNGB", "Ningbo", "宁波", "China", "East Asia"),
    ("CNTAO", "Qingdao", "青岛", "China", "East Asia"),
    ("CNXMN", "Xiamen", "厦门", "China", "East Asia"),
    ("CNYTN", "Yantian", "盐田", "China", "East Asia"),
    ("CNDLC", "Dalian", "大连", "China", "East Asia"),
    ("CNTSN", "Tianjin", "天津", "China", "East Asia"),

    # 韩国
    ("KRPUS", "Busan", "釜山", "South Korea", "East Asia"),
    ("KRKWA", "Kwangyang", "光阳", "South Korea", "East Asia"),
    ("KRULS", "Ulsan", "蔚山", "South Korea", "East Asia"),
    ("KRPOH", "Pohang", "浦项", "South Korea", "East Asia"),
    ("KRINC", "Inchon", "仁川", "South Korea", "East Asia"),
    ("KRKAN", "Gunsan", "群山", "South Korea", "East Asia"),

    # 香港/台湾
    ("HKHKG", "Hong Kong", "香港", "Hong Kong", "East Asia"),
    ("TWKHH", "Kaohsiung", "高雄", "Taiwan", "East Asia"),
    ("TWKEL", "Keelung", "基隆", "Taiwan", "East Asia"),
    ("TWTXG", "Taichung", "台中", "Taiwan", "East Asia"),
    ("TWTPE", "Taipei", "台北", "Taiwan", "East Asia"),

    # 越南
    ("VNHPH", "Haiphong", "海防", "Vietnam", "Southeast Asia"),
    ("VNSGN", "Ho Chi Minh", "胡志明", "Vietnam", "Southeast Asia"),
    ("VNCMP", "Cai Mep", "盖梅", "Vietnam", "Southeast Asia"),

    # 柬埔寨
    ("KHPNH", "Phnom Penh", "金边", "Cambodia", "Southeast Asia"),
    ("KHSHV", "Sihanoukville", "西哈努克", "Cambodia", "Southeast Asia"),

    # 泰国
    ("THBKK", "Bangkok", "曼谷", "Thailand", "Southeast Asia"),
    ("THLCH", "Laem Chabang", "林查班", "Thailand", "Southeast Asia"),
    ("THLKR", "Lat Krabang", "拉卡帮", "Thailand", "Southeast Asia"),

    # 新加坡
    ("SGSIN", "Singapore", "新加坡", "Singapore", "Southeast Asia"),

    # 马来西亚
    ("MYPGU", "Pasir Gudang", "巴西古荡", "Malaysia", "Southeast Asia"),
    ("MYPEN", "Penang", "槟城", "Malaysia", "Southeast Asia"),
    ("MYPKG", "Port Kelang", "巴生港", "Malaysia", "Southeast Asia"),
    ("MYKUA", "Kuantan", "关丹", "Malaysia", "Southeast Asia"),
    ("MYBTU", "Bintulu", "名都鲁", "Malaysia", "Southeast Asia"),

    # 印度尼西亚
    ("IDJKT", "Jakarta", "雅加达", "Indonesia", "Southeast Asia"),
    ("IDSMG", "Semarang", "三宝垄", "Indonesia", "Southeast Asia"),
    ("IDSUB", "Surabaya", "泗水", "Indonesia", "Southeast Asia"),
    ("IDBLW", "Belawan", "勿拉湾", "Indonesia", "Southeast Asia"),
    ("IDPNJ", "Panjang", "潘姜", "Indonesia", "Southeast Asia"),
    ("IDPLM", "Palembang", "巨港", "Indonesia", "Southeast Asia"),
    ("IDPTK", "Pontianak", "坤甸", "Indonesia", "Southeast Asia"),
    ("IDBTM", "Batam", "巴淡", "Indonesia", "Southeast Asia"),
    ("IDBJM", "Banjarmasin", "马辰港", "Indonesia", "Southeast Asia"),

    # 印度
    ("INNSA", "Nhava Sheva", "那瓦什瓦", "India", "South Asia"),
    ("INMUN", "Mundra", "蒙德拉", "India", "South Asia"),
    ("INHAZ", "Hazira", "哈兹拉", "India", "South Asia"),
    ("INMAA", "Chennai", "钦奈", "India", "South Asia"),
    ("INKTP", "Kattupalli", "卡图帕利", "India", "South Asia"),
    ("INVTZ", "Visakhapatnam", "维沙卡帕特南", "India", "South Asia"),
    ("INTUT", "Tuticorin", "图蒂戈林", "India", "South Asia"),
    ("INAMD", "Ahmedabad", "艾哈迈达巴德", "India", "South Asia"),

    # 巴基斯坦
    ("PKKHI", "Karachi", "卡拉奇", "Pakistan", "South Asia"),

    # 中东
    ("AEJEA", "Jebel Ali", "杰贝阿里", "UAE", "Middle East"),
    ("OMSOH", "Sohar", "苏哈尔", "Oman", "Middle East"),
    ("AEAUH", "Abu Dhabi", "阿布扎比", "UAE", "Middle East"),
    ("KWKWI", "Kuwait", "科威特", "Kuwait", "Middle East"),
    ("IQUQR", "Umm Qasr", "乌姆盖斯尔", "Iraq", "Middle East"),
    ("BHKBS", "Khalifa Bin Salman", "哈利法港", "Bahrain", "Middle East"),

    # 红海
    ("SAJED", "Jeddah", "吉达", "Saudi Arabia", "Red Sea"),
    ("EGSOK", "Sokhna", "苏赫纳", "Egypt", "Red Sea"),
    ("JOAQJ", "Aqaba", "亚喀巴", "Jordan", "Red Sea"),

    # 东非
    ("KEMBA", "Mombasa", "蒙巴萨", "Kenya", "East Africa"),
    ("TZDAR", "Dar es Salaam", "达累斯萨拉姆", "Tanzania", "East Africa"),

    # 墨西哥
    ("MXMAN", "Manzanillo", "曼萨尼约", "Mexico", "Central America"),

    # 美国 (NVO FAK 目的港)
    ("USLAX", "Los Angeles", "洛杉矶", "USA", "North America"),
    ("USLGB", "Long Beach", "长滩", "USA", "North America"),
    ("USOAK", "Oakland", "奥克兰", "USA", "North America"),
    ("USSEA", "Seattle", "西雅图", "USA", "North America"),
    ("USPDX", "Portland", "波特兰", "USA", "North America"),
    ("USNYC", "New York", "纽约", "USA", "North America"),
    ("USSAV", "Savannah", "萨凡纳", "USA", "North America"),
    ("USHOU", "Houston", "休斯顿", "USA", "North America"),
    ("USCHI", "Chicago", "芝加哥", "USA", "North America"),
    ("USATL", "Atlanta", "亚特兰大", "USA", "North America"),
    ("USDAL", "Dallas", "达拉斯", "USA", "North America"),
    ("USHNL", "Honolulu", "檀香山", "USA", "North America"),
    ("USCHS", "Charleston", "查尔斯顿", "USA", "North America"),
    ("USNOR", "Norfolk", "诺福克", "USA", "North America"),
    ("USBOS", "Boston", "波士顿", "USA", "North America"),
    ("USBAL", "Baltimore", "巴尔的摩", "USA", "North America"),
    ("USMIA", "Miami", "迈阿密", "USA", "North America"),
    ("USJAX", "Jacksonville", "杰克逊维尔", "USA", "North America"),
    ("USMEM", "Memphis", "孟菲斯", "USA", "North America"),
    ("USDET", "Detroit", "底特律", "USA", "North America"),
    ("USMIN", "Minneapolis", "明尼阿波利斯", "USA", "North America"),
    ("USCLT", "Charlotte", "夏洛特", "USA", "North America"),
    ("USTAC", "Tacoma", "塔科马", "USA", "North America"),
    ("USMOB", "Mobile", "莫比尔", "USA", "North America"),
    ("USMSY", "New Orleans", "新奥尔良", "USA", "North America"),
    ("USSAT", "San Antonio", "圣安东尼奥", "USA", "North America"),
    ("USELP", "El Paso", "埃尔帕索", "USA", "North America"),
    ("USPHX", "Phoenix", "凤凰城", "USA", "North America"),
    ("USRNO", "Reno", "里诺", "USA", "North America"),
    ("USCVG", "Cincinnati", "辛辛那提", "USA", "North America"),
    ("USCLV", "Cleveland", "克利夫兰", "USA", "North America"),
    ("USPIT", "Pittsburgh", "匹兹堡", "USA", "North America"),
    ("USBUF", "Buffalo", "布法罗", "USA", "North America"),
    ("USLUI", "Louisville", "路易斯维尔", "USA", "North America"),
    ("USIND", "Indianapolis", "印第安纳波利斯", "USA", "North America"),
    ("USMDT", "Harrisburg", "哈里斯堡", "USA", "North America"),
    ("USRIC", "Richmond", "里士满", "USA", "North America"),
    ("USHSV", "Huntsville", "亨茨维尔", "USA", "North America"),
    ("USCMH", "Columbus", "哥伦布", "USA", "North America"),
    ("USBNA", "Nashville", "纳什维尔", "USA", "North America"),
    ("USMKC", "Kansas City", "堪萨斯城", "USA", "North America"),
    ("USSTL", "St. Louis", "圣路易斯", "USA", "North America"),
    ("USDEN", "Denver", "丹佛", "USA", "North America"),
    ("USSLC", "Salt Lake City", "盐湖城", "USA", "North America"),

    # 加拿大
    ("CAVAN", "Vancouver", "温哥华", "Canada", "North America"),
    ("CATOR", "Toronto", "多伦多", "Canada", "North America"),
    ("CAMTR", "Montreal", "蒙特利尔", "Canada", "North America"),
    ("CAHAL", "Halifax", "哈利法克斯", "Canada", "North America"),
    ("CACAL", "Calgary", "卡尔加里", "Canada", "North America"),
    ("CAEDM", "Edmonton", "埃德蒙顿", "Canada", "North America"),
    ("CAWNP", "Winnipeg", "温尼伯", "Canada", "North America"),
    ("CASAS", "Saskatoon", "萨斯卡通", "Canada", "North America"),
]


# ============================================================
# 船司/供应商字典
# ============================================================
CARRIERS = [
    ("KMTC", "KMTC Line", "高丽海运", CarrierType.shipping_line, "South Korea"),
    ("ONE", "Ocean Network Express", "海洋网联", CarrierType.shipping_line, "Japan"),
    ("EMC", "Evergreen Marine", "长荣海运", CarrierType.shipping_line, "Taiwan"),
    ("OOCL", "Orient Overseas Container Line", "东方海外", CarrierType.shipping_line, "Hong Kong"),
    ("COSCO", "COSCO Shipping", "中远海运", CarrierType.shipping_line, "China"),
    ("MSC", "Mediterranean Shipping Company", "地中海航运", CarrierType.shipping_line, "Switzerland"),
    ("MSK", "Maersk Line", "马士基", CarrierType.shipping_line, "Denmark"),
    ("HPL", "Hapag-Lloyd", "赫伯罗特", CarrierType.shipping_line, "Germany"),
    ("YML", "Yang Ming Marine", "阳明海运", CarrierType.shipping_line, "Taiwan"),
    ("HMM", "HMM Co., Ltd.", "韩新海运", CarrierType.shipping_line, "South Korea"),
    ("ZIM", "ZIM Integrated Shipping", "以星航运", CarrierType.shipping_line, "Israel"),
    ("WHL", "Wan Hai Lines", "万海航运", CarrierType.shipping_line, "Taiwan"),
    ("PIL", "Pacific International Lines", "太平船务", CarrierType.shipping_line, "Singapore"),
    ("TSL", "T.S. Lines", "德翔航运", CarrierType.shipping_line, "Taiwan"),
    ("ESL", "Emirates Shipping Line", "阿联酋航运", CarrierType.shipping_line, "UAE"),
    ("NVO_FAK", "NVO FAK (Consolidated)", "NVO FAK整合", CarrierType.nvo, "USA"),
]


def seed_ports(db: Session):
    """导入港口数据"""
    created = 0
    for un_locode, name_en, name_cn, country, region in PORTS:
        existing = db.query(Port).filter(Port.un_locode == un_locode).first()
        if existing:
            continue
        port = Port(
            un_locode=un_locode,
            name_en=name_en,
            name_cn=name_cn,
            country=country,
            region=region,
        )
        db.add(port)
        created += 1
    db.commit()
    print(f"港口: 新增 {created} 条, 已存在 {len(PORTS) - created} 条")


def seed_carriers(db: Session):
    """导入船司数据"""
    created = 0
    for code, name_en, name_cn, carrier_type, country in CARRIERS:
        existing = db.query(Carrier).filter(Carrier.code == code).first()
        if existing:
            continue
        carrier = Carrier(
            code=code,
            name_en=name_en,
            name_cn=name_cn,
            carrier_type=carrier_type,
            country=country,
        )
        db.add(carrier)
        created += 1
    db.commit()
    print(f"船司: 新增 {created} 条, 已存在 {len(CARRIERS) - created} 条")


def main():
    print("正在初始化数据库表...")
    init_db()
    print("表创建完成\n")

    db = SessionLocal()
    try:
        print("=== 导入港口字典 ===")
        seed_ports(db)
        print()
        print("=== 导入船司字典 ===")
        seed_carriers(db)
        print()
        print("种子数据导入完成！")
    finally:
        db.close()


if __name__ == "__main__":
    main()
