from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, status
from jinja2 import Environment, TemplateSyntaxError

from app.db.session import SessionLocal
from app.services.contract_template_service import (
    CADASTRAL_MEMBER_MIN_ROWS,
    CADASTRAL_POINTS_PER_PAGE,
    blank_boundary_flags,
)
from app.services.dictionary_service import (
    DEFAULT_SURVEY_ORG,
    SURVEY_ORG_DICT_TYPE,
    dictionary_service,
)
from app.services.survey.boundary import (
    CADASTRAL_LINE_CATEGORY_COLUMNS,
    CADASTRAL_LINE_POSITION_COLUMNS,
    CADASTRAL_MARK_TYPE_COLUMNS,
    CADASTRAL_MARK_TYPE_FALLBACK,
    boundary_column_flags,
)


class ContractTemplateAdminService:
    def __init__(self) -> None:
        self.template_dir = Path(__file__).resolve().parent.parent / "templates"
        self.template_registry = {
            "contract": {"name": "合同模板", "filename": "contract.html"},
            "plot-sketch-map": {"name": "承包地块示意图模板", "filename": "poltsketchmap.html"},
            "registration-application": {"name": "不动产登记申请书模板", "filename": "registration_application.html"},
            "cadastral-survey": {"name": "地籍调查表模板", "filename": "cadastral_survey.html"},
            "issuer-survey": {"name": "发包方调查表模板", "filename": "issuer_survey.html"},
        }

    def get_contract_template(self) -> dict:
        return self.get_print_template("contract")

    def get_print_template(self, template_key: str) -> dict:
        meta, path = self._resolve_print_template_path(template_key)
        stat = path.stat()
        return {
            "key": template_key,
            "title": meta["name"],
            "name": meta["filename"],
            "content": path.read_text(encoding="utf-8"),
            "updatedAt": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "size": stat.st_size,
        }

    def update_contract_template(self, content: str) -> dict:
        return self.update_print_template("contract", content)

    def update_print_template(self, template_key: str, content: str) -> dict:
        self._validate_template(content)
        _, path = self._resolve_print_template_path(template_key)
        path.write_text(content, encoding="utf-8", newline="\n")
        return self.get_print_template(template_key)

    def preview_contract_template(self, content: str) -> dict:
        return self.preview_print_template("contract", content)

    def preview_print_template(self, template_key: str, content: str) -> dict:
        self._resolve_template_meta(template_key)
        self._validate_template(content)
        try:
            rendered = Environment(autoescape=False).from_string(content).render(**self._sample_context())
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"模板渲染失败：{exc}",
            ) from exc
        return {"renderedHtml": rendered}

    def _resolve_template_meta(self, template_key: str) -> dict:
        meta = self.template_registry.get(template_key)
        if meta is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="打印模板类型不存在")
        return meta

    def _resolve_print_template_path(self, template_key: str) -> tuple[dict, Path]:
        meta = self._resolve_template_meta(template_key)
        path = (self.template_dir / meta["filename"]).resolve()
        template_root = self.template_dir.resolve()
        if not path.is_file() or template_root not in path.parents:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{meta['name']}文件不存在")
        return meta, path

    def _validate_template(self, content: str) -> None:
        try:
            Environment(autoescape=False).parse(content)
        except TemplateSyntaxError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"模板语法错误：第 {exc.lineno} 行，{exc.message}",
            ) from exc

    def _sample_context(self) -> dict:
        parcels = [
            {
                "dkmc": "大梨园东西路南",
                "dkbm": "3413211032010100287",
                "dkbm_prefix": "34132110320101",
                "dkbm_suffix": "00287",
                "dkdz": "杨师傅",
                "dkxz": "王传远",
                "dknz": "汪文远、王成新",
                "dkbz": "王传明、王传奇等",
                "scmj_mu": "0.68",
                "dldj_text": "三等地",
                "code": "00287",
                "area": "0.68",
                "area_mu": "0.68",
                "boundaries": "东至杨师傅，南至汪文远，西至王传远，北至王传明",
                "is_basic_farmland": True,
                "remarks": "",
            },
            {
                "dkmc": "富士地（东）南段",
                "dkbm": "3413211032010100072",
                "dkbm_prefix": "34132110320101",
                "dkbm_suffix": "00072",
                "dkdz": "王传印、孙凡启",
                "dkxz": "王传远",
                "dknz": "王集居民地",
                "dkbz": "机耕路",
                "scmj_mu": "0.95",
                "dldj_text": "三等地",
                "code": "00072",
                "area": "0.95",
                "area_mu": "0.95",
                "boundaries": "东至王传印，南至王集居民地，西至王传远，北至机耕路",
                "is_basic_farmland": False,
                "remarks": "",
            },
            {
                "dkmc": "东北河湾地",
                "dkbm": "3413211032010100014",
                "dkbm_prefix": "34132110320101",
                "dkbm_suffix": "00014",
                "dkdz": "汪文彬",
                "dkxz": "王传远",
                "dknz": "机耕路",
                "dkbz": "王集居民地",
                "scmj_mu": "1.20",
                "dldj_text": "三等地",
                "code": "00014",
                "area": "1.20",
                "area_mu": "1.20",
                "boundaries": "东至汪文彬，南至机耕路，西至王传远，北至居民地",
                "is_basic_farmland": True,
                "remarks": "",
            },
        ]
        family_members = [
            {
                "name": "王传德",
                "id_type": "身份证",
                "id_number": "342221194803064018",
                "relation": "户主",
                "phone": "15385766993",
                "cyxm": "王传德",
                "relation_text": "户主",
                "cyzjhm": "342221194803064018",
                "remark": "",
            },
            {
                "name": "吴全英",
                "id_type": "身份证",
                "id_number": "342221194808014060",
                "relation": "配偶",
                "phone": "",
                "cyxm": "吴全英",
                "relation_text": "配偶",
                "cyzjhm": "342221194808014060",
                "remark": "",
            },
        ]
        return {
            "authentication_no": "唐寨NO.000104",
            "cbhtbm": "341321103201010028J",
            "fbfbm": "34132110320101",
            "fbfmc": "砀山县唐寨镇和谐村股份经济合作社",
            "fbf_social_credit_code": "N2341321MF0196829D",
            "fbf_fzr": "杨立方",
            "fbf_fzr_zjhm": "342221196709104238",
            "fbf_lxdh": "13705578699",
            "cbfbm": "341321103201010028",
            "cbfmc": "王传德",
            "cbfzjhm": "342221194803064018",
            "lxdh": "15385766993",
            "cbfdz": "安徽省宿州市砀山县唐寨镇和谐村前王集一组",
            "contract_years": "30",
            "cbqxq_iso": "2028-12-31",
            "cbqxz_iso": "2058-12-30",
            "qdsj_cn": "2026年2月9日",
            "htzmjm": "2.83",
            "cbdkzs": 3,
            "group_region_name": "和谐村前王集一组",
            "family_members": family_members,
            "parcels": parcels,
            # 合同末页附件「承包地块示意图」；版式与 poltsketchmap.html 一致
            "sketch": _sample_sketch_context(parcels),
            "right_type": "land_contract",
            "reg_type": "first",
            "contract_method": "family",
            "rep_name": "王传德",
            "rep_id_type": "身份证",
            "rep_id_number": "342221194803064018",
            "rep_phone": "15385766993",
            "issuer_name": "砀山县唐寨镇和谐村股份经济合作社",
            "issuer_id_type": "统一社会信用代码",
            "issuer_id_number": "N2341321MF0196829D",
            "issuer_phone": "13705578699",
            "auditor": "审核者：和谐村前王集一组　2026年2月9日",
            "mapper": "制图者：和谐村前王集一组　2026年2月9日",
            "compile_unit": _survey_org_setting(),
            "right_start_date": "2028-12-31",
            "right_end_date": "2058-12-30",
            "applicant_remarks": "",
            "total_area_mu": "2.83",
            "total_parcels": 3,
            "inquiry_q1": "yes",
            "inquiry_q2": "no",
            "inquiry_q3": "无",
            "survey_org": _survey_org_setting(),
            "member_min_rows": CADASTRAL_MEMBER_MIN_ROWS,
            "points_per_page": CADASTRAL_POINTS_PER_PAGE,
            "packets": [_sample_cadastral_packet(parcels, family_members)],
        }


def _survey_org_setting() -> str:
    """模板管理页预览用的「调查单位（机构）」。

    与实际打印读同一个字典项（``survey_org``），避免"预览一个名字、打印另一个名字"。
    预览属于辅助功能，数据库不可用时直接退回默认值，不让整个预览失败。
    """
    try:
        with SessionLocal() as db:
            value = dictionary_service.get_setting(db, SURVEY_ORG_DICT_TYPE, DEFAULT_SURVEY_ORG)
    except Exception:  # noqa: BLE001 - 预览不应因取配置失败而报错
        return DEFAULT_SURVEY_ORG
    return value or DEFAULT_SURVEY_ORG


def _sample_sketch_context(parcels: list[dict]) -> dict:
    """合同末页附件「承包地块示意图」的样例数据（模板管理页预览用）。

    键名必须与 ``contract_template_service.build_plot_sketch_data`` 的返回一致，
    否则预览会静默少画图。图形只用于预览，取的是 poltsketchmap.html 里那批样例
    多边形，不代表任何真实地块。
    """
    geometries = [
        [[0, 0], [62, 6], [118, 5], [119, 24], [57, 23], [0, 18], [0, 0]],
        [[31, 0], [75, 2], [55, 118], [8, 127], [31, 0]],
        [[48, 0], [61, 1], [43, 126], [31, 126], [48, 0]],
        [[42, 0], [74, 5], [52, 82], [42, 82], [28, 133], [52, 135], [42, 0]],
        [[0, 0], [114, 0], [109, 118], [0, 121], [0, 0]],
    ]
    plots = []
    for index, parcel in enumerate(parcels):
        plots.append({
            "code": parcel.get("dkbm_suffix") or parcel.get("dkbm", ""),
            "dkbm": parcel.get("dkbm", ""),
            "area": parcel.get("scmj_mu", ""),
            "north": parcel.get("dkbz", ""),
            "south": parcel.get("dknz", ""),
            "west": parcel.get("dkxz", ""),
            "east": parcel.get("dkdz", ""),
            "geometry": {"type": "Polygon", "coordinates": [geometries[index % len(geometries)]]},
        })
    overview = plots + [
        {
            "dkbm": "3413211032010100200",
            "geometry": {"type": "Polygon", "coordinates": [geometries[3]]},
        },
        {
            "dkbm": "3413211032010100201",
            "geometry": {"type": "Polygon", "coordinates": [geometries[4]]},
        },
    ]
    return {
        "plots": plots,
        "overview": overview,
        "highlight": plots,
        "village_name": "和谐村前王集一组",
        "auditor": "审核者：杨立方　2026年02月09日",
        "mapper": "制图者：杨立方　2026年02月09日",
        "compile_unit": _survey_org_setting(),
        "audit_date": "2026年02月09日",
        "map_date": "2026年02月09日",
    }


def _sample_cadastral_packet(parcels: list[dict], family_members: list[dict]) -> dict:
    """Sample context for the cadastral-survey template (template管理页预览用）。

    这份样例必须与真实打印件（``contract_template_service._build_cadastral_packet``）
    **保持同一套键**，否则预览会报错或"静默少列"。凡是列排布/勾选结构，
    一律调真实打印用的同一个函数，不要在这里另写一套。
    """

    def make_points(count: int) -> list[dict]:
        base_x, base_y = 3685858.192, 39591674.606
        # 界标类型 / 界址线类别 / 界址线位置 是甲方表上的**固定勾选格**，
        # 列跨度由 CADASTRAL_*_COLUMNS 决定。预览要让三种情况各出现一次：
        #   · 第 1 行：木桩（C.12 码值 5） + 沟渠（02） + 内（01）→ 都是"码值命中"；
        #   · 第 2 行：水泥桩（码值 2，甲方表上没这格）→ 走 fallback 落「埋石」；
        #   · 第 3 行起：界标类型为空 → 走 fallback 落「无」，界址线两组留空。
        # 这样一眼能看出「界标类型三选一」与「其他两组只勾命中项」的差别。
        mark_samples: tuple[str | None, ...] = ("5", "2", None)
        line_samples: tuple[str | None, ...] = ("02", "01", None)
        pos_samples: tuple[str | None, ...] = ("01", "02", None)
        points = []
        for index in range(count):
            mark = mark_samples[index] if index < len(mark_samples) else None
            line = line_samples[index] if index < len(line_samples) else None
            pos = pos_samples[index] if index < len(pos_samples) else None
            points.append({
                "seq": index + 1,
                "code": f"J{index + 1}",
                "x": f"{base_x + index * 12.345:.3f}",
                "y": f"{base_y + index * 9.876:.3f}",
                "edge": f"{15.4 + index:.3f}",
                "remark": "",
                "jzdh": "",
                "mark_flags": boundary_column_flags(
                    CADASTRAL_MARK_TYPE_COLUMNS,
                    mark,
                    fallback=CADASTRAL_MARK_TYPE_FALLBACK,
                ),
                "line_flags": boundary_column_flags(
                    CADASTRAL_LINE_CATEGORY_COLUMNS, line,
                ),
                "pos_flags": boundary_column_flags(
                    CADASTRAL_LINE_POSITION_COLUMNS, pos,
                ),
                "line_note": "",
            })
        return points

    members = [
        {
            "name": item.get("cyxm") or item.get("name") or "",
            "relation": item.get("relation_text") or item.get("relation") or "",
            "id_no": item.get("cyzjhm") or item.get("id_number") or "",
            "remark": item.get("remark") or "",
        }
        for item in family_members
    ]

    sample_parcels = []
    for index, parcel in enumerate(parcels):
        points = make_points(4 + index)
        sample_parcels.append({
            "dkbm": parcel.get("dkbm", ""),
            "dkmc": parcel.get("dkmc", ""),
            "dklb_text": "承包地块",
            "fbfbm": "34132110320101",
            "htmjm": parcel.get("scmj_mu", ""),
            "scmj": parcel.get("scmj", ""),
            "area_mu": parcel.get("scmj_mu", ""),
            "east": parcel.get("dkdz", ""),
            "south": parcel.get("dknz", ""),
            "west": parcel.get("dkxz", ""),
            "north": parcel.get("dkbz", ""),
            "boundary_note": "",
            "use_text": "种植业",
            "use_flags": [
                {"label": "种植业", "checked": True},
                {"label": "林业", "checked": False},
                {"label": "畜牧业", "checked": False},
                {"label": "渔业", "checked": False},
            ],
            "grade_text": "三等地",
            "landuse_text": parcel.get("tdlylx_text", "旱地"),
            "landuse_flags": [
                {"label": "水田", "checked": False},
                {"label": "旱地", "checked": True},
                {"label": "水浇地", "checked": False},
                {"label": "林地", "checked": False},
                {"label": "果园", "checked": False},
            ],
            "basic_farmland": bool(parcel.get("is_basic_farmland")),
            "sheet_no": "",
            "survey_note": "经调查该地块信息准确无误。",
            "audit_note": "同意。",
            "auditor": "",
            "audit_date_text": "",
            "points": points,
            "point_pages": [points],
            "table_points": points[:8],
            "table_point_rows": max(8, len(points[:8])),
            "hidden_point_count": max(0, len(points) - 8),
            "has_points": True,
            # 空行勾选列：与真实打印件共用同一个函数，列跨度不会跑偏。
            "blank_flags": blank_boundary_flags(),
        })

    return {
        "issuer": {
            "name": "砀山县唐寨镇和谐村股份经济合作社",
            "code": "34132110320101",
            "head": "杨立方",
            "head_id_type": "居民身份证",
            "head_id_no": "342221196709104238",
            "head_phone": "13705578699",
            "address": "安徽省宿州市砀山县唐寨镇和谐村",
            "postcode": "235300",
            "survey_note": "调查员：杨立方（签字并摁手印）\n日期：2026年2月9日",
            "audit_note": "合格。",
            "auditor": "杨立方",
            "audit_date_text": "2026年02月09日",
        },
        "contractor": {
            "name": "王传德",
            "code": "341321103201010028",
            "short_code": "0028",
            "type_text": "农户",
            "id_type": "居民身份证",
            "id_no": "342221194803064018",
            "phone": "15385766993",
            "address": "安徽省宿州市砀山县唐寨镇和谐村前王集一组",
            "postcode": "235300",
            "has_contract": True,
            "contract_code": "341321103201010028J",
            "has_cert": True,
            "cert_code": "341321103201010028J",
            "acquire_method": "家庭承包",
            "acquire_code": "110",
            "term_begin": "2028年12月31日",
            "term_end": "2058年12月30日",
            "term_years": "30",
            "member_count": len(members),
            "members": members,
            "sheet_ysdm": "",
            "survey_note": (
                "承包方代表变更情况：无变更\n"
                "土地承包经营权权属特殊情况：无。\n"
                "农户内成员分家析产、合户或家庭成员其他情况：无。\n"
                "其他需要说明的情况：无。\n"
                "调查员：王传德（签字并摁手印）\n"
                "日期：2026年02月09日"
            ),
            "audit_note": "合格。",
            "auditor": "杨立方",
            "audit_date_text": "2026年02月09日",
        },
        "parcels": sample_parcels,
        "survey_date_text": "2026年02月09日",
    }


contract_template_admin_service = ContractTemplateAdminService()
