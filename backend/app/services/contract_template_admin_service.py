from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, status
from jinja2 import Environment, TemplateSyntaxError


class ContractTemplateAdminService:
    def __init__(self) -> None:
        self.template_dir = Path(__file__).resolve().parent.parent / "templates"
        self.contract_template_path = self.template_dir / "contract.html"

    def get_contract_template(self) -> dict:
        path = self._resolve_contract_template_path()
        stat = path.stat()
        return {
            "name": "contract.html",
            "content": path.read_text(encoding="utf-8"),
            "updatedAt": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "size": stat.st_size,
        }

    def update_contract_template(self, content: str) -> dict:
        self._validate_template(content)
        path = self._resolve_contract_template_path()
        path.write_text(content, encoding="utf-8", newline="\n")
        return self.get_contract_template()

    def preview_contract_template(self, content: str) -> dict:
        self._validate_template(content)
        try:
            rendered = Environment(autoescape=False).from_string(content).render(**self._sample_context())
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"模板渲染失败：{exc}",
            ) from exc
        return {"renderedHtml": rendered}

    def _resolve_contract_template_path(self) -> Path:
        path = self.contract_template_path.resolve()
        template_root = self.template_dir.resolve()
        if not path.is_file() or template_root not in path.parents:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="合同模板不存在")
        return path

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
                "dkdz": "杨师争",
                "dkxz": "王传连",
                "dknz": "汪文远、王成新",
                "dkbz": "王传明、王传奇等",
                "scmj_mu": "0.68",
                "dldj_text": "三等地",
            },
            {
                "dkmc": "富士地（东）南段",
                "dkbm": "3413211032010100072",
                "dkbm_prefix": "34132110320101",
                "dkbm_suffix": "00072",
                "dkdz": "王传印、孟凡启",
                "dkxz": "王传连",
                "dknz": "王集居民地",
                "dkbz": "机耕路",
                "scmj_mu": "0.95",
                "dldj_text": "三等地",
            },
            {
                "dkmc": "东北河洼地",
                "dkbm": "3413211032010100014",
                "dkbm_prefix": "34132110320101",
                "dkbm_suffix": "00014",
                "dkdz": "汪文彬",
                "dkxz": "王传连",
                "dknz": "机耕路",
                "dkbz": "王集居民地",
                "scmj_mu": "1.20",
                "dldj_text": "三等地",
            },
            {
                "dkmc": "富士地（小路东）",
                "dkbm": "3413211032010100095",
                "dkbm_prefix": "34132110320101",
                "dkbm_suffix": "00095",
                "dkdz": "王德将",
                "dkxz": "王传峰、王传明",
                "dknz": "沟渠",
                "dkbz": "张安七组承包地杨圣利户、王传奇",
                "scmj_mu": "2.64",
                "dldj_text": "三等地",
            },
            {
                "dkmc": "苹果园路东",
                "dkbm": "3413211032010100171",
                "dkbm_prefix": "34132110320101",
                "dkbm_suffix": "00171",
                "dkdz": "前王集十四组集体地",
                "dkxz": "王传明",
                "dknz": "机耕路",
                "dkbz": "郭思艾",
                "scmj_mu": "0.17",
                "dldj_text": "三等地",
            },
        ]
        return {
            "authentication_no": "唐寨NO.000104",
            "cbhtbm": "341321103201010028J",
            "fbfbm": "34132110320101",
            "fbfmc": "砀山县唐寨镇和谐村股份经济合作社",
            "fbf_social_credit_code": "N2341321MF0196829D",
            "fbf_fzr": "杨立文",
            "fbf_fzr_zjhm": "342221196709104238",
            "fbf_lxdh": "13705578699",
            "cbfbm": "341321103201010028",
            "cbfmc": "王传得",
            "cbfzjhm": "342221194803064018",
            "lxdh": "15385766993",
            "cbfdz": "安徽省宿州市砀山县唐寨镇和谐村前王集一组",
            "contract_years": "30",
            "cbqxq_iso": "2028-12-31",
            "cbqxz_iso": "2058-12-30",
            "qdsj_cn": "2026年02月09日",
            "htzmjm": "5.64",
            "cbdkzs": 5,
            "group_region_name": "和谐村前王集一组",
            "family_members": [
                {"cyxm": "王传得", "relation_text": "户主", "cyzjhm": "342221194803064018", "remark": ""},
                {"cyxm": "吴全英", "relation_text": "配偶", "cyzjhm": "342221194808014060", "remark": ""},
                {"cyxm": "王军", "relation_text": "子", "cyzjhm": "34222119760610407X", "remark": ""},
            ],
            "parcels": parcels,
        }


contract_template_admin_service = ContractTemplateAdminService()
