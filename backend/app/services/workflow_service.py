from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from SpiffWorkflow.bpmn.serializer.workflow import BpmnWorkflowSerializer
from SpiffWorkflow.bpmn.workflow import BpmnWorkflow
from SpiffWorkflow.spiff.parser import SpiffBpmnParser
from SpiffWorkflow.spiff.serializer import DEFAULT_CONFIG as SPIFF_SERIALIZER_CONFIG
from SpiffWorkflow.util.task import TaskState
from SpiffWorkflow.version import __version__ as spiff_version


BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
RURAL_NS = "http://ruralland.cn/schema/bpmn"
NS = {"bpmn": BPMN_NS}


@dataclass(slots=True)
class WorkflowTaskConfig:
    code: str
    name: str
    permission_code: str | None = None
    data_scope: str | None = None
    require_comment: bool = False
    require_attachment: bool = False
    attachment_types: list[str] | None = None
    candidate_role_codes: list[str] | None = None
    candidate_user_mode: str | None = None
    is_applicant_task: bool = False


@dataclass(slots=True)
class WorkflowDefinition:
    workflow_code: str
    process_id: str
    name: str
    applicant_task_codes: set[str]
    review_task_codes: list[str]
    task_configs: dict[str, WorkflowTaskConfig]
    step_order: list[tuple[str, str]]


@dataclass(slots=True)
class WorkflowBundle:
    mtime: float
    parser: SpiffBpmnParser
    definition: WorkflowDefinition


@dataclass(slots=True)
class WorkflowSnapshot:
    workflow_state: str
    current_step: str
    status: str
    current_task_code: str | None
    current_task_name: str | None
    required_permission: str | None
    require_comment: bool
    data_scope: str | None
    candidate_role_codes: list[str]
    candidate_user_mode: str | None
    completed: bool


class WorkflowService:
    default_workflow_code = "rural_contract"

    def __init__(self) -> None:
        registry = BpmnWorkflowSerializer.configure(SPIFF_SERIALIZER_CONFIG)
        self._serializer = BpmnWorkflowSerializer(registry=registry)
        self._workflow_dir = Path(__file__).resolve().parent.parent / "workflows"
        self._bundle_cache: dict[str, WorkflowBundle] = {}

    def get_status(self) -> dict:
        return {
            "enabled": True,
            "provider": "SpiffWorkflow",
            "version": spiff_version,
            "message": "已接入 BPMN 工作流引擎",
        }

    def resolve_workflow_code(self, workflow_code: str | None) -> str:
        return workflow_code or self.default_workflow_code

    def get_definition(self, workflow_code: str | None = None, workflow_content: str | None = None) -> WorkflowDefinition:
        return self._get_bundle(self.resolve_workflow_code(workflow_code), workflow_content=workflow_content).definition

    def get_task_config(
        self,
        workflow_code: str | None,
        task_code: str | None,
        workflow_content: str | None = None,
    ) -> WorkflowTaskConfig | None:
        if not task_code:
            return None
        return self.get_definition(workflow_code, workflow_content=workflow_content).task_configs.get(task_code)

    def get_applicant_task_codes(self, workflow_code: str | None = None, workflow_content: str | None = None) -> set[str]:
        return set(self.get_definition(workflow_code, workflow_content=workflow_content).applicant_task_codes)

    def get_review_task_codes(self, workflow_code: str | None = None, workflow_content: str | None = None) -> list[str]:
        return list(self.get_definition(workflow_code, workflow_content=workflow_content).review_task_codes)

    def get_step_order(self, workflow_code: str | None = None, workflow_content: str | None = None) -> list[tuple[str, str]]:
        return list(self.get_definition(workflow_code, workflow_content=workflow_content).step_order)

    def create_workflow(
        self,
        workflow_code: str | None = None,
        data: dict[str, Any] | None = None,
        workflow_content: str | None = None,
    ) -> WorkflowSnapshot:
        resolved_code = self.resolve_workflow_code(workflow_code)
        workflow = BpmnWorkflow(self._get_spec(resolved_code, workflow_content=workflow_content))
        if data:
            workflow.set_data(**data)
        self._run_engine(workflow)
        return self.snapshot(resolved_code, workflow, workflow_content=workflow_content)

    def restore_workflow(
        self,
        workflow_code: str | None,
        workflow_state: str,
        workflow_content: str | None = None,
    ) -> BpmnWorkflow:
        resolved_code = self.resolve_workflow_code(workflow_code)
        self.get_definition(resolved_code, workflow_content=workflow_content)
        workflow = self._serializer.deserialize_json(workflow_state)
        self._run_engine(workflow)
        return workflow

    def snapshot(
        self,
        workflow_code: str | None,
        workflow: BpmnWorkflow,
        workflow_content: str | None = None,
    ) -> WorkflowSnapshot:
        definition = self.get_definition(workflow_code, workflow_content=workflow_content)
        task = self.get_current_task(workflow)
        if workflow.is_completed():
            return WorkflowSnapshot(
                workflow_state=self._serializer.serialize_json(workflow),
                current_step="已办结",
                status="已办结",
                current_task_code=None,
                current_task_name=None,
                required_permission=None,
                require_comment=False,
                data_scope=None,
                candidate_role_codes=[],
                candidate_user_mode=None,
                completed=True,
            )

        task_code = self.get_task_code(task)
        task_name = self.get_task_name(task)
        task_config = definition.task_configs.get(task_code or "")
        current_step, status = self._derive_step_and_status(task_code, task_name, task_config)
        return WorkflowSnapshot(
            workflow_state=self._serializer.serialize_json(workflow),
            current_step=current_step,
            status=status,
            current_task_code=task_code,
            current_task_name=task_name,
            required_permission=task_config.permission_code if task_config else None,
            require_comment=task_config.require_comment if task_config else False,
            data_scope=task_config.data_scope if task_config else None,
            candidate_role_codes=list(task_config.candidate_role_codes or []) if task_config else [],
            candidate_user_mode=task_config.candidate_user_mode if task_config else None,
            completed=False,
        )

    def complete_task(
        self,
        workflow_state: str,
        expected_codes: set[str],
        data: dict[str, Any] | None = None,
        *,
        workflow_code: str | None = None,
        workflow_content: str | None = None,
    ) -> WorkflowSnapshot:
        resolved_code = self.resolve_workflow_code(workflow_code)
        workflow = self.restore_workflow(resolved_code, workflow_state, workflow_content=workflow_content)
        task = self.get_current_task(workflow)
        task_code = self.get_task_code(task)
        if task_code not in expected_codes:
            raise ValueError(f"当前任务 {task_code!r} 不允许执行该动作")
        if data:
            task.set_data(**data)
        task.run()
        self._run_engine(workflow)
        return self.snapshot(resolved_code, workflow, workflow_content=workflow_content)

    def bootstrap_snapshot(
        self,
        *,
        workflow_code: str | None = None,
        status: str,
        current_step: str,
        request_context: dict[str, Any] | None = None,
        workflow_content: str | None = None,
    ) -> WorkflowSnapshot:
        resolved_code = self.resolve_workflow_code(workflow_code)
        definition = self.get_definition(resolved_code, workflow_content=workflow_content)
        snapshot = self.create_workflow(resolved_code, request_context, workflow_content=workflow_content)

        first_applicant_code = next(
            (
                code
                for code, config in definition.task_configs.items()
                if config.is_applicant_task and "revision" not in code
            ),
            None,
        )
        if first_applicant_code is None:
            first_applicant_code = next(iter(definition.applicant_task_codes), None)
        first_review_code = definition.review_task_codes[0] if definition.review_task_codes else None

        if status == "待提交" or not first_applicant_code:
            return snapshot

        if status == "已退回" and first_review_code:
            submitted = self.complete_task(
                snapshot.workflow_state,
                {first_applicant_code},
                {"approval_result": None},
                workflow_code=resolved_code,
                workflow_content=workflow_content,
            )
            return self.complete_task(
                submitted.workflow_state,
                {first_review_code},
                {"approval_result": "rejected"},
                workflow_code=resolved_code,
                workflow_content=workflow_content,
            )

        if not first_review_code:
            return snapshot

        current_snapshot = self.complete_task(
            snapshot.workflow_state,
            {first_applicant_code},
            {"approval_result": None},
            workflow_code=resolved_code,
            workflow_content=workflow_content,
        )

        current_name_to_code = {name: code for code, name in definition.step_order}
        target_code = current_name_to_code.get(current_step)

        if status == "审核中" and target_code == current_snapshot.current_task_code:
            return current_snapshot

        for review_code in definition.review_task_codes:
            if current_snapshot.current_task_code != review_code:
                break
            if status == "审核中" and target_code == review_code:
                return current_snapshot
            current_snapshot = self.complete_task(
                current_snapshot.workflow_state,
                {review_code},
                {"approval_result": "approved"},
                workflow_code=resolved_code,
                workflow_content=workflow_content,
            )
            if status == "已办结" and current_snapshot.completed:
                return current_snapshot

        return current_snapshot

    def get_current_task(self, workflow: BpmnWorkflow):
        tasks = workflow.get_tasks(state=TaskState.READY, manual=True)
        return sorted(tasks, key=lambda item: str(item.id))[0] if tasks else None

    def get_task_code(self, task) -> str | None:
        return task.task_spec.name if task is not None else None

    def get_task_name(self, task) -> str | None:
        if task is None:
            return None
        return getattr(task.task_spec, "bpmn_name", None) or task.task_spec.name

    def _derive_step_and_status(
        self,
        task_code: str | None,
        task_name: str | None,
        task_config: WorkflowTaskConfig | None,
    ) -> tuple[str, str]:
        if task_config and task_config.is_applicant_task:
            if task_code and "revision" in task_code:
                return "申请", "已退回"
            return "申请", "待提交"
        if task_config and task_config.permission_code:
            return task_config.name, "审核中"
        return task_name or "处理中", "处理中"

    def _get_workflow_file(self, workflow_code: str) -> Path:
        file_path = self._workflow_dir / f"{workflow_code}.bpmn"
        if not file_path.exists():
            raise FileNotFoundError(f"未找到流程定义文件：{workflow_code}.bpmn")
        return file_path

    def _build_inline_cache_key(self, workflow_code: str, workflow_content: str) -> str:
        digest = hashlib.sha1(workflow_content.encode("utf-8")).hexdigest()
        return f"{workflow_code}:inline:{digest}"

    def _get_bundle(self, workflow_code: str, workflow_content: str | None = None) -> WorkflowBundle:
        if workflow_content is not None:
            cache_key = self._build_inline_cache_key(workflow_code, workflow_content)
            cached = self._bundle_cache.get(cache_key)
            if cached:
                return cached

            parser = SpiffBpmnParser()
            parser.add_bpmn_str(workflow_content.encode("utf-8"), f"{workflow_code}.bpmn")
            definition = self._parse_definition(workflow_code, workflow_content)
            bundle = WorkflowBundle(mtime=0, parser=parser, definition=definition)
            self._bundle_cache[cache_key] = bundle
            return bundle

        workflow_file = self._get_workflow_file(workflow_code)
        mtime = workflow_file.stat().st_mtime
        cached = self._bundle_cache.get(workflow_code)
        if cached and cached.mtime == mtime:
            return cached

        parser = SpiffBpmnParser()
        with workflow_file.open("rb") as workflow_file_handle:
            parser.add_bpmn_io(workflow_file_handle, str(workflow_file))

        content = workflow_file.read_text(encoding="utf-8")
        definition = self._parse_definition(workflow_code, content)
        bundle = WorkflowBundle(mtime=mtime, parser=parser, definition=definition)
        self._bundle_cache[workflow_code] = bundle
        return bundle

    def _get_spec(self, workflow_code: str, workflow_content: str | None = None):
        bundle = self._get_bundle(workflow_code, workflow_content=workflow_content)
        return bundle.parser.get_spec(bundle.definition.process_id)

    def _parse_definition(self, workflow_code: str, content: str) -> WorkflowDefinition:
        root = ElementTree.fromstring(content)
        process = root.find("bpmn:process", NS)
        if process is None:
            raise ValueError("流程定义中缺少 process 节点")

        process_id = process.attrib.get("id") or workflow_code
        process_name = process.attrib.get("name") or process_id

        task_configs: dict[str, WorkflowTaskConfig] = {}
        applicant_task_codes: set[str] = set()
        review_task_codes: list[str] = []

        for user_task in process.findall("bpmn:userTask", NS):
            code = user_task.attrib.get("id")
            if not code:
                continue
            name = user_task.attrib.get("name") or code
            permission_code = user_task.attrib.get(f"{{{RURAL_NS}}}permissionCode") or None
            data_scope = user_task.attrib.get(f"{{{RURAL_NS}}}dataScope") or None
            require_comment = self._parse_bool(user_task.attrib.get(f"{{{RURAL_NS}}}requireComment"))
            require_attachment = self._parse_bool(user_task.attrib.get(f"{{{RURAL_NS}}}requireAttachment"))
            attachment_types = self._split_codes(user_task.attrib.get(f"{{{RURAL_NS}}}attachmentTypes"))
            candidate_role_codes = self._split_codes(user_task.attrib.get(f"{{{RURAL_NS}}}candidateRoleCodes"))
            candidate_user_mode = user_task.attrib.get(f"{{{RURAL_NS}}}candidateUserMode") or None
            is_applicant_task = self._is_applicant_task(code, name, permission_code)

            config = WorkflowTaskConfig(
                code=code,
                name=name,
                permission_code=permission_code,
                data_scope=data_scope,
                require_comment=require_comment,
                require_attachment=require_attachment,
                attachment_types=attachment_types,
                candidate_role_codes=candidate_role_codes,
                candidate_user_mode=candidate_user_mode,
                is_applicant_task=is_applicant_task,
            )
            task_configs[code] = config
            if is_applicant_task:
                applicant_task_codes.add(code)
            else:
                review_task_codes.append(code)

        step_order: list[tuple[str, str]] = []
        if applicant_task_codes:
            step_order.append(("apply", "申请"))
        for task_code in review_task_codes:
            step_order.append((task_code, task_configs[task_code].name))
        step_order.append(("complete", "已办结"))

        return WorkflowDefinition(
            workflow_code=workflow_code,
            process_id=process_id,
            name=process_name,
            applicant_task_codes=applicant_task_codes,
            review_task_codes=review_task_codes,
            task_configs=task_configs,
            step_order=step_order,
        )

    def _is_applicant_task(self, code: str, name: str, permission_code: str | None) -> bool:
        if permission_code:
            return False
        normalized = f"{code} {name}".lower()
        return "applicant" in normalized or "申请" in normalized

    def _split_codes(self, value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def _parse_bool(self, value: str | None) -> bool:
        if value is None:
            return False
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}

    def _run_engine(self, workflow: BpmnWorkflow) -> None:
        workflow.refresh_waiting_tasks()
        workflow.do_engine_steps()


workflow_service = WorkflowService()
