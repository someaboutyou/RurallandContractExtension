"""NY/T 2539-2016 Appendix C dictionary presets.

Generated from the standard's appendix C classification tables.
Each tuple is (dict_type, dict_name, code, name, sort_order, remark).
"""

NYT2539_APPENDIX_C_DICTIONARY_ITEMS = [
    # C.1 控制点类型及等级代码表
    ("nyt2539_c01_control_point_type_grade", "C.1 控制点类型及等级代码表", "110100", "平面控制点", 10, "控制点类型：平面控制点"),
    ("nyt2539_c01_control_point_type_grade", "C.1 控制点类型及等级代码表", "110101", "大地原点 / 大地原点", 20, "控制点类型：平面控制点"),
    ("nyt2539_c01_control_point_type_grade", "C.1 控制点类型及等级代码表", "110102", "三角点 / 一等，二等，三等，四等，5秒，10秒", 30, "控制点类型：平面控制点"),
    ("nyt2539_c01_control_point_type_grade", "C.1 控制点类型及等级代码表", "110103", "导线点 / 一级，二级", 40, "控制点类型：平面控制点"),
    ("nyt2539_c01_control_point_type_grade", "C.1 控制点类型及等级代码表", "110200", "高程控制点", 50, "控制点类型：高程控制点"),
    ("nyt2539_c01_control_point_type_grade", "C.1 控制点类型及等级代码表", "110201", "水准原点 / 水准原点", 60, "控制点类型：高程控制点"),
    ("nyt2539_c01_control_point_type_grade", "C.1 控制点类型及等级代码表", "110202", "水准点 / 一等，二等，三等，四等", 70, "控制点类型：高程控制点"),
    ("nyt2539_c01_control_point_type_grade", "C.1 控制点类型及等级代码表", "110203", "三角高程点 / 三角高程点", 80, "控制点类型：高程控制点"),
    ("nyt2539_c01_control_point_type_grade", "C.1 控制点类型及等级代码表", "110300", "像片控制点", 90, "控制点类型：像片控制点"),
    ("nyt2539_c01_control_point_type_grade", "C.1 控制点类型及等级代码表", "110400", "GPS 控制点", 100, "控制点类型：GPS控制点"),

    # C.2 标石类型代码表
    ("nyt2539_c02_marker_stone_type", "C.2 标石类型代码表", "1", "基岩标石", 10, None),
    ("nyt2539_c02_marker_stone_type", "C.2 标石类型代码表", "2", "混凝土标石", 20, None),
    ("nyt2539_c02_marker_stone_type", "C.2 标石类型代码表", "3", "普通标石", 30, None),
    ("nyt2539_c02_marker_stone_type", "C.2 标石类型代码表", "4", "其他标石", 40, None),

    # C.3 标志类型代码表
    ("nyt2539_c03_marker_type", "C.3 标志类型代码表", "1", "铜标志", 10, None),
    ("nyt2539_c03_marker_type", "C.3 标志类型代码表", "2", "钢标志", 20, None),
    ("nyt2539_c03_marker_type", "C.3 标志类型代码表", "3", "刻十字标志", 30, None),
    ("nyt2539_c03_marker_type", "C.3 标志类型代码表", "4", "其他标志", 40, None),

    # C.4 界线类型代码表
    ("nyt2539_c04_boundary_type", "C.4 界线类型代码表", "250200", "海岸线", 10, None),
    ("nyt2539_c04_boundary_type", "C.4 界线类型代码表", "250201", "大潮平均高潮线", 20, None),
    ("nyt2539_c04_boundary_type", "C.4 界线类型代码表", "250202", "零米等深线", 30, None),
    ("nyt2539_c04_boundary_type", "C.4 界线类型代码表", "600100", "行政区界线", 40, None),
    ("nyt2539_c04_boundary_type", "C.4 界线类型代码表", "600200", "地籍区界线", 50, None),
    ("nyt2539_c04_boundary_type", "C.4 界线类型代码表", "600300", "地籍子区界线", 60, None),
    ("nyt2539_c04_boundary_type", "C.4 界线类型代码表", "600400", "宗地界线", 70, None),
    ("nyt2539_c04_boundary_type", "C.4 界线类型代码表", "600500", "界址线", 80, None),
    ("nyt2539_c04_boundary_type", "C.4 界线类型代码表", "610100", "争议区界线", 90, None),
    ("nyt2539_c04_boundary_type", "C.4 界线类型代码表", "610200", "工作区界线", 100, None),
    ("nyt2539_c04_boundary_type", "C.4 界线类型代码表", "610300", "保护区界线", 110, None),
    ("nyt2539_c04_boundary_type", "C.4 界线类型代码表", "610400", "规划区界线", 120, None),

    # C.5 界线性质代码表
    ("nyt2539_c05_boundary_property", "C.5 界线性质代码表", "600001", "已定界", 10, None),
    ("nyt2539_c05_boundary_property", "C.5 界线性质代码表", "600002", "未定界", 20, None),
    ("nyt2539_c05_boundary_property", "C.5 界线性质代码表", "600003", "争议界", 30, None),
    ("nyt2539_c05_boundary_property", "C.5 界线性质代码表", "600004", "工作界", 40, None),
    ("nyt2539_c05_boundary_property", "C.5 界线性质代码表", "600005", "其他", 50, None),

    # C.6 所有权性质代码表
    ("nyt2539_c06_ownership_property", "C.6 所有权性质代码表", "10", "国有土地所有权", 10, None),
    ("nyt2539_c06_ownership_property", "C.6 所有权性质代码表", "30", "集体土地所有权", 20, None),
    ("nyt2539_c06_ownership_property", "C.6 所有权性质代码表", "31", "村民小组", 30, None),
    ("nyt2539_c06_ownership_property", "C.6 所有权性质代码表", "32", "村集体经济组织", 40, None),
    ("nyt2539_c06_ownership_property", "C.6 所有权性质代码表", "33", "乡集体经济组织", 50, None),
    ("nyt2539_c06_ownership_property", "C.6 所有权性质代码表", "34", "其他集体经济组织", 60, None),

    # C.7 地块类别代码表
    ("nyt2539_c07_parcel_category", "C.7 地块类别代码表", "10", "承包地块", 10, None),
    ("nyt2539_c07_parcel_category", "C.7 地块类别代码表", "21", "自留地", 20, None),
    ("nyt2539_c07_parcel_category", "C.7 地块类别代码表", "22", "机动地", 30, None),
    ("nyt2539_c07_parcel_category", "C.7 地块类别代码表", "23", "开荒地", 40, None),
    ("nyt2539_c07_parcel_category", "C.7 地块类别代码表", "24", "其他", 50, None),

    # C.8 地力等级代码表
    ("nyt2539_c08_land_grade", "C.8 地力等级代码表", "01", "一等地", 10, None),
    ("nyt2539_c08_land_grade", "C.8 地力等级代码表", "02", "二等地", 20, None),
    ("nyt2539_c08_land_grade", "C.8 地力等级代码表", "03", "三等地", 30, None),
    ("nyt2539_c08_land_grade", "C.8 地力等级代码表", "04", "四等地", 40, None),
    ("nyt2539_c08_land_grade", "C.8 地力等级代码表", "05", "五等地", 50, None),
    ("nyt2539_c08_land_grade", "C.8 地力等级代码表", "06", "六等地", 60, None),
    ("nyt2539_c08_land_grade", "C.8 地力等级代码表", "07", "七等地", 70, None),
    ("nyt2539_c08_land_grade", "C.8 地力等级代码表", "08", "八等地", 80, None),
    ("nyt2539_c08_land_grade", "C.8 地力等级代码表", "09", "九等地", 90, None),
    ("nyt2539_c08_land_grade", "C.8 地力等级代码表", "10", "十等地", 100, None),

    # C.9 土地用途代码表
    ("nyt2539_c09_land_use", "C.9 土地用途代码表", "1", "种植业", 10, None),
    ("nyt2539_c09_land_use", "C.9 土地用途代码表", "2", "林业", 20, None),
    ("nyt2539_c09_land_use", "C.9 土地用途代码表", "3", "畜牧业", 30, None),
    ("nyt2539_c09_land_use", "C.9 土地用途代码表", "4", "渔业", 40, None),
    ("nyt2539_c09_land_use", "C.9 土地用途代码表", "5", "其他", 50, None),

    # C.10 承包经营权取得方式代码表
    ("nyt2539_c10_right_acquire_method", "C.10 承包经营权取得方式代码表", "100", "承包", 10, None),
    ("nyt2539_c10_right_acquire_method", "C.10 承包经营权取得方式代码表", "110", "家庭承包", 20, None),
    ("nyt2539_c10_right_acquire_method", "C.10 承包经营权取得方式代码表", "120", "其他方式承包", 30, None),
    ("nyt2539_c10_right_acquire_method", "C.10 承包经营权取得方式代码表", "200", "转让", 40, None),
    ("nyt2539_c10_right_acquire_method", "C.10 承包经营权取得方式代码表", "300", "互换", 50, None),
    ("nyt2539_c10_right_acquire_method", "C.10 承包经营权取得方式代码表", "400", "继承", 60, None),
    ("nyt2539_c10_right_acquire_method", "C.10 承包经营权取得方式代码表", "500", "受赠", 70, None),
    ("nyt2539_c10_right_acquire_method", "C.10 承包经营权取得方式代码表", "600", "法院判决", 80, None),
    ("nyt2539_c10_right_acquire_method", "C.10 承包经营权取得方式代码表", "700", "其他", 90, None),
    ("nyt2539_c10_right_acquire_method", "C.10 承包经营权取得方式代码表", "800", "初始登记", 100, None),

    # C.11 界址点类型代码表
    ("nyt2539_c11_boundary_point_type", "C.11 界址点类型代码表", "1", "实测法界址点", 10, None),
    ("nyt2539_c11_boundary_point_type", "C.11 界址点类型代码表", "2", "航测法界址点", 20, None),
    ("nyt2539_c11_boundary_point_type", "C.11 界址点类型代码表", "3", "图解法界址点", 30, None),

    # C.12 界标类型代码表
    ("nyt2539_c12_boundary_marker_type", "C.12 界标类型代码表", "1", "钢钉", 10, None),
    ("nyt2539_c12_boundary_marker_type", "C.12 界标类型代码表", "2", "水泥桩", 20, None),
    ("nyt2539_c12_boundary_marker_type", "C.12 界标类型代码表", "3", "石灰桩", 30, None),
    ("nyt2539_c12_boundary_marker_type", "C.12 界标类型代码表", "4", "喷涂标志", 40, None),
    ("nyt2539_c12_boundary_marker_type", "C.12 界标类型代码表", "5", "木桩", 50, None),
    ("nyt2539_c12_boundary_marker_type", "C.12 界标类型代码表", "6", "塑料桩", 60, None),
    ("nyt2539_c12_boundary_marker_type", "C.12 界标类型代码表", "7", "带钢帽水泥桩", 70, None),
    ("nyt2539_c12_boundary_marker_type", "C.12 界标类型代码表", "8", "瓷标志", 80, None),
    ("nyt2539_c12_boundary_marker_type", "C.12 界标类型代码表", "9", "其他", 90, None),

    # C.13 界址线类别代码表
    ("nyt2539_c13_boundary_line_category", "C.13 界址线类别代码表", "01", "田垄（埂）", 10, None),
    ("nyt2539_c13_boundary_line_category", "C.13 界址线类别代码表", "02", "沟渠", 20, None),
    ("nyt2539_c13_boundary_line_category", "C.13 界址线类别代码表", "03", "道路", 30, None),
    ("nyt2539_c13_boundary_line_category", "C.13 界址线类别代码表", "04", "围墙", 40, None),
    ("nyt2539_c13_boundary_line_category", "C.13 界址线类别代码表", "05", "栅栏", 50, None),
    ("nyt2539_c13_boundary_line_category", "C.13 界址线类别代码表", "06", "屋墙", 60, None),
    ("nyt2539_c13_boundary_line_category", "C.13 界址线类别代码表", "07", "滴水线", 70, None),
    ("nyt2539_c13_boundary_line_category", "C.13 界址线类别代码表", "08", "山脊线", 80, None),
    ("nyt2539_c13_boundary_line_category", "C.13 界址线类别代码表", "09", "其他", 90, None),

    # C.14 界址线位置代码表
    ("nyt2539_c14_boundary_line_position", "C.14 界址线位置代码表", "01", "内", 10, None),
    ("nyt2539_c14_boundary_line_position", "C.14 界址线位置代码表", "02", "中", 20, None),
    ("nyt2539_c14_boundary_line_position", "C.14 界址线位置代码表", "03", "外", 30, None),

    # C.15 证件类型代码表
    ("nyt2539_c15_id_document_type", "C.15 证件类型代码表", "1", "居民身份证", 10, None),
    ("nyt2539_c15_id_document_type", "C.15 证件类型代码表", "2", "军官证", 20, None),
    ("nyt2539_c15_id_document_type", "C.15 证件类型代码表", "3", "行政、企事业单位机构代码证或法人代码证", 30, None),
    ("nyt2539_c15_id_document_type", "C.15 证件类型代码表", "4", "户口簿", 40, None),
    ("nyt2539_c15_id_document_type", "C.15 证件类型代码表", "5", "护照", 50, None),
    ("nyt2539_c15_id_document_type", "C.15 证件类型代码表", "9", "其他", 60, None),

    # C.16 承包方类型代码表
    ("nyt2539_c16_contractor_type", "C.16 承包方类型代码表", "1", "农户", 10, None),
    ("nyt2539_c16_contractor_type", "C.16 承包方类型代码表", "2", "个人", 20, None),
    ("nyt2539_c16_contractor_type", "C.16 承包方类型代码表", "3", "单位", 30, None),

    # C.17 性别代码表
    ("nyt2539_c17_gender", "C.17 性别代码表", "1", "男", 10, None),
    ("nyt2539_c17_gender", "C.17 性别代码表", "2", "女", 20, None),

    # C.18 成员备注代码表
    ("nyt2539_c18_member_remark", "C.18 成员备注代码表", "1", "外嫁女", 10, None),
    ("nyt2539_c18_member_remark", "C.18 成员备注代码表", "2", "入赘男", 20, None),
    ("nyt2539_c18_member_remark", "C.18 成员备注代码表", "3", "在校大学生", 30, None),
    ("nyt2539_c18_member_remark", "C.18 成员备注代码表", "4", "现役军人", 40, None),
    ("nyt2539_c18_member_remark", "C.18 成员备注代码表", "5", "服刑人员", 50, None),
    ("nyt2539_c18_member_remark", "C.18 成员备注代码表", "6", "常住人口", 60, None),
    ("nyt2539_c18_member_remark", "C.18 成员备注代码表", "7", "外出务工人员", 70, None),
    ("nyt2539_c18_member_remark", "C.18 成员备注代码表", "8", "其他", 80, None),

    # C.19 是否代码表
    ("nyt2539_c19_yes_no", "C.19 是否代码表", "1", "是", 10, None),
    ("nyt2539_c19_yes_no", "C.19 是否代码表", "2", "否", 20, None),

    # 扩展：与户主关系代码表
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "01", "本人", 10, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "02", "户主", 20, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "10", "配偶", 30, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "11", "夫", 40, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "12", "妻", 50, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "20", "子", 60, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "21", "独生子", 70, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "22", "长子", 80, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "23", "次子", 90, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "24", "三子", 100, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "25", "四子", 110, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "26", "五子", 120, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "27", "养子或继子", 130, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "28", "女婿", 140, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "29", "其他儿子", 150, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "30", "女", 160, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "31", "独生女", 170, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "32", "长女", 180, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "33", "次女", 190, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "34", "三女", 200, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "35", "四女", 210, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "36", "五女", 220, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "37", "养女或继女", 230, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "38", "儿媳", 240, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "39", "其他女儿", 250, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "40", "孙子、孙女或外孙子、外孙女", 260, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "41", "孙子", 270, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "42", "孙女", 280, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "43", "外孙子", 290, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "44", "外孙女", 300, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "45", "孙媳妇或外孙媳妇", 310, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "46", "孙女婿或外孙女婿", 320, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "47", "曾孙子或外曾孙子", 330, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "48", "曾孙女或外曾孙女", 340, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "49", "其他孙子、孙女或外孙子、外孙女", 350, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "50", "父母", 360, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "51", "父亲", 370, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "52", "母亲", 380, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "60", "祖父母或外祖父母", 390, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "61", "祖父", 400, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "62", "祖母", 410, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "63", "外祖父", 420, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "64", "外祖母", 430, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "70", "兄、弟、姐、妹", 440, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "71", "哥哥", 450, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "72", "弟弟", 460, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "73", "姐夫", 470, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "74", "妹夫", 480, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "75", "姐姐", 490, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "76", "妹妹", 500, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "77", "嫂子", 510, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "78", "弟媳", 520, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "79", "其他兄弟姐妹", 530, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "80", "其他", 540, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "81", "伯父、叔父、舅父、姑父、姨夫", 550, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "82", "伯母、婶母、舅母、姑母、姨母", 560, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "83", "公公", 570, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "84", "婆婆", 580, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "85", "岳父", 590, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "86", "岳母", 600, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "90", "祖父、祖母、外祖父、外祖母的兄弟姐妹", 610, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "91", "堂兄弟姐妹、表兄弟姐妹", 620, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "92", "妯娌", 630, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "93", "侄子、侄女、外甥、外甥女", 640, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "94", "其他亲属", 650, None),
    ("nyt2539_c20_relation_to_head", "与户主关系代码表", "95", "非亲属", 660, None),
]
