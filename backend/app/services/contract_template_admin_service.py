from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, status
from jinja2 import Environment, TemplateSyntaxError


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
            "compile_unit": "砀山县唐寨镇和谐村股份经济合作社",
            "right_start_date": "2028-12-31",
            "right_end_date": "2058-12-30",
            "applicant_remarks": "",
            "total_area_mu": "2.83",
            "total_parcels": 3,
            "inquiry_q1": "yes",
            "inquiry_q2": "no",
            "inquiry_q3": "无",
        }


contract_template_admin_service = ContractTemplateAdminService()
