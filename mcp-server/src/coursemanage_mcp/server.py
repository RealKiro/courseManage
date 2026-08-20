# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2024-2026 courseManage Contributors
"""MCP 工具定义。

工具命名遵循 ``动词_名词`` 约定，描述全部使用中文，便于国内大模型
（DeepSeek / 通义千问 / GLM 等）在 AstrBot 场景下正确选择工具。

写操作统一受 ``COURSEMANAGE_MCP_READONLY`` 控制：开启只读后，
所有会修改数据的工具都不会注册，第三方框架自然无法调用。
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Annotated, Any, TypeVar

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

from . import formatting as fmt
from .client import ApiError, CourseManageClient
from .config import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

INSTRUCTIONS = """\
courseManage 是面向教育培训机构的综合管理平台，覆盖排课、导师/学员/班级/教室、
请假、课费、成绩、评价与运营统计。

使用建议：
1. 需要按名字操作某个实体时，先用 list_students / list_teachers / list_courses /
   list_classes 搜索拿到 ID，再调用需要 ID 的工具。
2. 查询课程安排使用 list_schedules；查「今天 / 明天」直接用 get_schedules_by_day。
3. 不确定如何组合参数时，可以把用户原话交给 parse_smart_command 解析，
   确认无误后再调用 run_smart_command 执行。
4. 本部署已放开全部功能（含费用、成绩、评价、运营大屏、智能指令），
   无需任何激活即可调用。若仍收到 403，那是账号角色权限不足，不是授权问题。
5. 日期一律使用 YYYY-MM-DD，时间使用 HH:MM，星期使用 1-7（1=周一）。
"""


def _iso(value: date) -> str:
    return value.isoformat()


def build_server(settings: Settings, client: CourseManageClient) -> FastMCP:
    """构造并返回已注册全部工具的 FastMCP 实例。"""

    mcp = FastMCP(
        name="courseManage",
        instructions=INSTRUCTIONS,
        host=settings.host,
        port=settings.port,
        streamable_http_path=settings.path,
        stateless_http=settings.stateless_http,
        log_level=settings.log_level,
    )

    def _guard(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return await fn(*args, **kwargs)
            except ApiError as exc:
                raise ToolError(str(exc)) from exc
        return wrapper

    def tool(
        *, write: bool = False, enabled: bool = True
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
            if not enabled:
                logger.info("按配置跳过注册工具 %s", fn.__name__)
                return fn
            if write and settings.readonly:
                logger.info("只读模式：跳过注册写操作工具 %s", fn.__name__)
                return fn
            mcp.tool()(_guard(fn))
            return fn
        return decorator

    def _cap(limit: int) -> int:
        return max(1, min(limit, settings.max_items))

    def _notify(flag: bool) -> bool:
        """禁止通知时强制关闭 send_notification，避免机器人误发企业微信/邮件。"""
        return bool(flag) and settings.allow_notifications

    # ================================================================
    # 系统 / 元信息
    # ================================================================
    @tool()
    async def get_system_status() -> dict[str, Any]:
        """检查 courseManage 后端连通性、当前登录身份与已激活的高级功能。

        任何工具报错时都建议先调用它定位问题。
        """
        result: dict[str, Any] = {"connectivity": await client.ping(), "readonly": settings.readonly}
        try:
            result["current_user"] = await client.get("/api/auth/me")
        except ApiError as exc:
            result["current_user_error"] = str(exc)
        try:
            result["license"] = await client.get("/api/license/status")
        except ApiError as exc:
            result["license_error"] = str(exc)
        return result

    @tool()
    async def get_site_info() -> Any:
        """获取机构站点信息（机构名称、LOGO、官网、联系人等全局参数）。"""
        return await client.get("/api/settings/site-info")

    # ================================================================
    # 基础档案查询
    # ================================================================
    @tool()
    async def list_courses(
        search: Annotated[str | None, Field(description="按科目代码或名称模糊搜索")] = None,
        is_active: Annotated[bool | None, Field(description="仅启用(True)/仅停用(False)/全部(None)")] = True,
        limit: Annotated[int, Field(description="返回条数", ge=1, le=200)] = 20,
        offset: Annotated[int, Field(description="跳过条数，用于翻页", ge=0)] = 0,
    ) -> dict[str, Any]:
        """查询科目列表。需要科目 ID 时先用本工具按名称搜索。"""
        limit = _cap(limit)
        data = await client.get(
            "/api/courses", search=search, is_active=is_active, skip=offset, limit=limit
        )
        return fmt.paginated(data, "course", limit=limit, offset=offset)

    @tool()
    async def list_teachers(
        search: Annotated[str | None, Field(description="按导师代码或姓名模糊搜索")] = None,
        is_active: Annotated[bool | None, Field(description="仅在职(True)/仅离职(False)/全部(None)")] = True,
        limit: Annotated[int, Field(description="返回条数", ge=1, le=200)] = 20,
        offset: Annotated[int, Field(description="跳过条数", ge=0)] = 0,
    ) -> dict[str, Any]:
        """查询导师列表（含职称、部门、联系方式、可授科目 ID）。"""
        limit = _cap(limit)
        data = await client.get(
            "/api/teachers", search=search, is_active=is_active, skip=offset, limit=limit
        )
        return fmt.paginated(data, "teacher", limit=limit, offset=offset)

    @tool()
    async def list_classes(
        search: Annotated[str | None, Field(description="按班级代码或名称模糊搜索")] = None,
        is_active: Annotated[bool | None, Field(description="仅启用(True)/仅停用(False)/全部(None)")] = True,
        limit: Annotated[int, Field(description="返回条数", ge=1, le=200)] = 20,
        offset: Annotated[int, Field(description="跳过条数", ge=0)] = 0,
    ) -> dict[str, Any]:
        """查询班级列表。"""
        limit = _cap(limit)
        data = await client.get(
            "/api/classes", search=search, is_active=is_active, skip=offset, limit=limit
        )
        return fmt.paginated(data, "class", limit=limit, offset=offset)

    @tool()
    async def list_students(
        search: Annotated[str | None, Field(description="按学员代码、姓名或联系人模糊搜索")] = None,
        class_id: Annotated[int | None, Field(description="限定某个班级的学员")] = None,
        is_active: Annotated[bool | None, Field(description="仅在读(True)/仅结业(False)/全部(None)")] = True,
        limit: Annotated[int, Field(description="返回条数", ge=1, le=200)] = 20,
        offset: Annotated[int, Field(description="跳过条数", ge=0)] = 0,
    ) -> dict[str, Any]:
        """查询学员列表（含所属班级、学校、年级、联系方式）。"""
        limit = _cap(limit)
        data = await client.get(
            "/api/students",
            search=search,
            class_id=class_id,
            is_active=is_active,
            skip=offset,
            limit=limit,
        )
        return fmt.paginated(data, "student", limit=limit, offset=offset)

    @tool()
    async def get_student(
        student_id: Annotated[int, Field(description="学员 ID")],
    ) -> Any:
        """获取单个学员的完整档案。"""
        return fmt.single(await client.get(f"/api/students/{student_id}"), "student")

    @tool()
    async def list_rooms(
        search: Annotated[str | None, Field(description="按教室代码、名称或位置模糊搜索")] = None,
        is_active: Annotated[bool | None, Field(description="仅启用(True)/仅停用(False)/全部(None)")] = True,
        limit: Annotated[int, Field(description="返回条数", ge=1, le=200)] = 20,
        offset: Annotated[int, Field(description="跳过条数", ge=0)] = 0,
    ) -> dict[str, Any]:
        """查询教室列表（含位置、容量、设施）。"""
        limit = _cap(limit)
        data = await client.get(
            "/api/rooms", search=search, is_active=is_active, skip=offset, limit=limit
        )
        return fmt.paginated(data, "room", limit=limit, offset=offset)

    # ================================================================
    # 排课查询
    # ================================================================
    @tool()
    async def list_schedules(
        start_date: Annotated[str | None, Field(description="起始日期 YYYY-MM-DD（含）")] = None,
        end_date: Annotated[str | None, Field(description="截止日期 YYYY-MM-DD（含）")] = None,
        teacher_id: Annotated[int | None, Field(description="导师 ID")] = None,
        class_id: Annotated[int | None, Field(description="班级 ID")] = None,
        course_id: Annotated[int | None, Field(description="科目 ID")] = None,
        room_id: Annotated[int | None, Field(description="教室 ID")] = None,
        student_id: Annotated[int | None, Field(description="学员 ID：只看该学员参与的课")] = None,
        execution_status: Annotated[
            str | None,
            Field(description="执行状态：pending 待上课 / completed 已完训 / postponed 已延期 / cancelled 已取消"),
        ] = None,
        schedule_type: Annotated[
            str | None, Field(description="课程类型：formal 正式课 / trial 试听课")
        ] = None,
        has_conflict: Annotated[bool | None, Field(description="只看有冲突的排课")] = None,
        limit: Annotated[int, Field(description="返回条数", ge=1, le=200)] = 30,
        offset: Annotated[int, Field(description="跳过条数", ge=0)] = 0,
    ) -> dict[str, Any]:
        """按日期区间与多维度条件查询课程安排。

        日期区间为「重叠」语义：只要课程的起止日期与给定区间有交集就会返回。
        """
        limit = _cap(limit)
        data = await client.get(
            "/api/schedules",
            start_date=start_date,
            end_date=end_date,
            teacher_id=teacher_id,
            class_id=class_id,
            course_id=course_id,
            room_id=room_id,
            student_ids=str(student_id) if student_id else None,
            execution_status=execution_status,
            schedule_type=schedule_type,
            has_conflict=has_conflict,
            skip=offset,
            limit=limit,
            sort_field="start_date",
            sort_order="asc",
        )
        return fmt.paginated(data, "schedule", limit=limit, offset=offset)

    @tool()
    async def get_schedules_by_day(
        day: Annotated[
            str,
            Field(description="today 今天 / tomorrow 明天 / yesterday 昨天 / week 未来 7 天，或直接给 YYYY-MM-DD"),
        ] = "today",
        teacher_id: Annotated[int | None, Field(description="只看某位导师")] = None,
        class_id: Annotated[int | None, Field(description="只看某个班级")] = None,
        limit: Annotated[int, Field(description="返回条数", ge=1, le=200)] = 50,
    ) -> dict[str, Any]:
        """查询「今天 / 明天 / 本周」的课程安排，适合日常问答与课表播报。"""
        limit = _cap(limit)
        today = date.today()
        alias = day.strip().lower()
        if alias == "today":
            start = end = today
        elif alias == "tomorrow":
            start = end = today + timedelta(days=1)
        elif alias == "yesterday":
            start = end = today - timedelta(days=1)
        elif alias in ("week", "next7", "7d"):
            start, end = today, today + timedelta(days=6)
        else:
            try:
                start = end = date.fromisoformat(alias)
            except ValueError as exc:
                raise ToolError(
                    "day 参数只能是 today/tomorrow/yesterday/week 或 YYYY-MM-DD 格式的日期"
                ) from exc

        data = await client.get(
            "/api/schedules",
            start_date=_iso(start),
            end_date=_iso(end),
            teacher_id=teacher_id,
            class_id=class_id,
            skip=0,
            limit=limit,
            sort_field="start_time",
            sort_order="asc",
        )
        result = fmt.paginated(data, "schedule", limit=limit)
        result["range"] = {"start": _iso(start), "end": _iso(end)}
        return result

    @tool()
    async def get_schedule(
        schedule_id: Annotated[int, Field(description="课程安排 ID")],
        verbose: Annotated[bool, Field(description="返回后端原始字段（含作业、单词检查等）")] = False,
    ) -> Any:
        """获取单条课程安排详情，含学员出勤明细与冲突原因。"""
        data = await client.get(f"/api/schedules/{schedule_id}")
        return fmt.single(data, "schedule", verbose=verbose)

    @tool()
    async def list_schedule_conflicts(
        limit: Annotated[int, Field(description="返回条数", ge=1, le=200)] = 30,
    ) -> dict[str, Any]:
        """列出当前所有排课冲突（导师/教室/班级/学员时间撞车）。"""
        limit = _cap(limit)
        data = await client.get("/api/schedules/conflicts")
        return fmt.paginated(data, "conflict", limit=limit)

    @tool()
    async def get_absent_students(
        schedule_id: Annotated[int, Field(description="课程安排 ID")],
    ) -> Any:
        """查询某次课程的缺席学员（用于补课跟进）。"""
        return await client.get(f"/api/schedules/{schedule_id}/absent-students")

    # ================================================================
    # 请假与节假日
    # ================================================================
    @tool()
    async def list_leaves(
        leave_type: Annotated[str | None, Field(description="请假类型：teacher 导师 / student 学员")] = None,
        teacher_id: Annotated[int | None, Field(description="导师 ID")] = None,
        student_id: Annotated[int | None, Field(description="学员 ID")] = None,
        limit: Annotated[int, Field(description="返回条数", ge=1, le=200)] = 20,
        offset: Annotated[int, Field(description="跳过条数", ge=0)] = 0,
    ) -> dict[str, Any]:
        """查询请假记录。"""
        limit = _cap(limit)
        data = await client.get(
            "/api/leaves",
            leave_type=leave_type,
            teacher_id=teacher_id,
            student_id=student_id,
            skip=offset,
            limit=limit,
        )
        return fmt.paginated(data, "leave", limit=limit, offset=offset)

    @tool()
    async def list_holidays(
        limit: Annotated[int, Field(description="返回条数", ge=1, le=200)] = 50,
        offset: Annotated[int, Field(description="跳过条数", ge=0)] = 0,
    ) -> dict[str, Any]:
        """查询节假日列表（排课会自动避开这些日期）。"""
        limit = _cap(limit)
        data = await client.get("/api/holidays/holidays", skip=offset, limit=limit)
        return fmt.paginated(data, "holiday", limit=limit, offset=offset)

    # ================================================================
    # 运营统计
    # ================================================================
    @tool()
    async def get_dashboard_kpi() -> Any:
        """获取运营大屏核心 KPI（收入、转化率、学员数、导师数、课次、出勤率等）。"""
        return await client.get("/api/statistics/kpi")

    @tool()
    async def get_teacher_workload(
        days: Annotated[int, Field(description="统计最近多少天", ge=1, le=1080)] = 30,
    ) -> Any:
        """统计导师工作量排行。"""
        return await client.get("/api/statistics/teachers/workload", days=days)

    @tool()
    async def get_room_utilization(
        days: Annotated[int, Field(description="统计最近多少天", ge=1, le=1080)] = 7,
    ) -> Any:
        """统计教室使用率。"""
        return await client.get("/api/statistics/rooms/utilization", days=days)

    @tool()
    async def get_incomplete_schedules(
        limit: Annotated[int, Field(description="返回条数", ge=1, le=200)] = 30,
    ) -> Any:
        """列出已过期但仍未完训的课程安排，用于催办。"""
        return await client.get("/api/statistics/schedules/incomplete-list", limit=_cap(limit))

    # ================================================================
    # 课费
    # ================================================================
    @tool()
    async def list_student_fees(
        student_id: Annotated[int | None, Field(description="学员 ID")] = None,
        course_id: Annotated[int | None, Field(description="科目 ID")] = None,
        search: Annotated[str | None, Field(description="按学员姓名/科目模糊搜索")] = None,
        limit: Annotated[int, Field(description="返回条数", ge=1, le=200)] = 20,
        offset: Annotated[int, Field(description="跳过条数", ge=0)] = 0,
    ) -> dict[str, Any]:
        """查询学员课费项（剩余课时、已缴金额、余额）。"""
        limit = _cap(limit)
        data = await client.get(
            "/api/fees/student-fees",
            student_id=student_id,
            course_id=course_id,
            search=search,
            skip=offset,
            limit=limit,
        )
        return fmt.paginated(data, "student_fee", limit=limit, offset=offset)

    @tool()
    async def get_fee_alerts() -> Any:
        """获取收费提醒（剩余课时低于阈值的学员）。"""
        return await client.get("/api/fees/alerts")

    # ================================================================
    # 成绩与评价
    # ================================================================
    @tool()
    async def list_grades(
        student_id: Annotated[int | None, Field(description="学员 ID")] = None,
        course_id: Annotated[int | None, Field(description="科目 ID")] = None,
        limit: Annotated[int, Field(description="返回条数", ge=1, le=200)] = 20,
        offset: Annotated[int, Field(description="跳过条数", ge=0)] = 0,
    ) -> dict[str, Any]:
        """查询学员成绩记录。"""
        limit = _cap(limit)
        data = await client.get(
            "/api/grades", student_id=student_id, course_id=course_id, skip=offset, limit=limit
        )
        return fmt.paginated(data, "grade", limit=limit, offset=offset)

    @tool()
    async def get_student_grade_trend(
        student_id: Annotated[int, Field(description="学员 ID")],
    ) -> Any:
        """查询某学员所有科目的成绩变化趋势。"""
        return await client.get(f"/api/grades/student-trend/{student_id}")

    @tool()
    async def get_student_evaluation_profile(
        student_id: Annotated[int, Field(description="学员 ID")],
    ) -> Any:
        """查询学员综合能力画像（五维/多维评价）。"""
        return await client.get(f"/api/evaluations/student/{student_id}/profile")

    # ================================================================
    # 智能指令（自然语言操作）
    # ================================================================
    @tool()
    async def parse_smart_command(
        text: Annotated[str, Field(description="用户原始自然语言指令，例如「给三年级A班周三19点排一节数学课」")],
        use_ai: Annotated[
            bool,
            Field(description="是否用大模型解析（需先在系统中配置 API KEY），否则使用内置规则解析"),
        ] = False,
    ) -> Any:
        """解析自然语言指令并返回结构化预览，不会写入数据。

        推荐流程：parse_smart_command → 向用户确认 → run_smart_command。
        """
        return await client.post("/api/smart-command/preview", json={"text": text, "use_ai": use_ai})

    @tool(write=True)
    async def run_smart_command(
        parsed_intent: Annotated[
            dict[str, Any],
            Field(description="parse_smart_command 返回的 parsed_intent 对象，原样传回"),
        ],
    ) -> Any:
        """执行 parse_smart_command 解析出的指令，会真实写入数据。

        务必先让用户确认预览内容。
        """
        return await client.post(
            "/api/smart-command/execute", json={"parsed_intent": parsed_intent, "confirmed": True}
        )

    # ================================================================
    # 写操作：排课
    # ================================================================
    @tool(write=True)
    async def create_schedule(
        course_id: Annotated[int, Field(description="科目 ID")],
        teacher_id: Annotated[int, Field(description="导师 ID")],
        class_id: Annotated[int, Field(description="班级 ID")],
        day_of_week: Annotated[int, Field(description="星期几，1=周一 … 7=周日", ge=1, le=7)],
        start_time: Annotated[str, Field(description="开始时间 HH:MM")],
        end_time: Annotated[str, Field(description="结束时间 HH:MM")],
        start_date: Annotated[str, Field(description="课程开始日期 YYYY-MM-DD")],
        end_date: Annotated[str, Field(description="课程结束日期 YYYY-MM-DD")],
        room_id: Annotated[int | None, Field(description="教室 ID（线下课必填）")] = None,
        room_type: Annotated[
            str, Field(description="offline_physical 线下物理教室 / online_virtual 线上虚拟教室")
        ] = "offline_physical",
        meeting_link: Annotated[str | None, Field(description="会议室链接（线上课必填）")] = None,
        schedule_type: Annotated[str, Field(description="formal 正式课 / trial 试听课")] = "formal",
        send_notification: Annotated[bool, Field(description="是否发送企业微信/邮件通知")] = False,
    ) -> Any:
        """新建一条课程安排。系统会自动检测导师/教室/班级/学员时间冲突。"""
        if room_type == "offline_physical" and not room_id:
            raise ToolError("线下课程必须提供 room_id，可先用 list_rooms 查询可用教室。")
        if room_type == "online_virtual" and not meeting_link:
            raise ToolError("线上课程必须提供 meeting_link。")
        payload = {
            "course_id": course_id,
            "teacher_id": teacher_id,
            "class_id": class_id,
            "room_type": room_type,
            "room_id": room_id,
            "meeting_link": meeting_link,
            "day_of_week": day_of_week,
            "start_time": start_time,
            "end_time": end_time,
            "start_date": start_date,
            "end_date": end_date,
            "schedule_type": schedule_type,
            "execution_status": "pending",
            "send_notification": _notify(send_notification),
        }
        return fmt.single(await client.post("/api/schedules", json=payload), "schedule")

    @tool(write=True)
    async def complete_schedule(
        schedule_id: Annotated[int, Field(description="课程安排 ID")],
        content_feedback: Annotated[
            str,
            Field(description="课程反馈，建议格式：内容：…|作业：…|注意：…（用 | 分隔）"),
        ],
        renewal_intention: Annotated[
            str | None, Field(description="续报意愿：high / medium / low / none")
        ] = None,
        student_attendance: Annotated[
            dict[str, str] | None,
            Field(description='出勤字典，键为学员 ID 字符串，值为 present/absent/leave，如 {"12":"present"}'),
        ] = None,
        send_notification: Annotated[bool, Field(description="是否发送完训通知")] = False,
    ) -> Any:
        """把课程标记为已完训，并填写课后反馈与出勤。"""
        payload: dict[str, Any] = {
            "content_feedback": content_feedback,
            "renewal_intention": renewal_intention,
            "send_notification": _notify(send_notification),
        }
        if student_attendance:
            payload["student_attendance"] = {int(k): v for k, v in student_attendance.items()}
        return await client.post(f"/api/schedules/{schedule_id}/complete", json=payload)

    @tool(write=True)
    async def postpone_schedule(
        schedule_id: Annotated[int, Field(description="课程安排 ID")],
        start_date: Annotated[str, Field(description="新的开始日期 YYYY-MM-DD")],
        end_date: Annotated[str, Field(description="新的结束日期 YYYY-MM-DD")],
        start_time: Annotated[str, Field(description="新的开始时间 HH:MM")],
        end_time: Annotated[str, Field(description="新的结束时间 HH:MM")],
        postpone_reason: Annotated[str, Field(description="延期原因")],
        send_notification: Annotated[bool, Field(description="是否发送变更通知")] = False,
    ) -> Any:
        """把课程延期到新的日期/时间。"""
        return await client.post(
            f"/api/schedules/{schedule_id}/postpone",
            json={
                "start_date": start_date,
                "end_date": end_date,
                "start_time": start_time,
                "end_time": end_time,
                "postpone_reason": postpone_reason,
                "send_notification": _notify(send_notification),
            },
        )

    @tool(write=True)
    async def cancel_schedule(
        schedule_id: Annotated[int, Field(description="课程安排 ID")],
        cancel_reason: Annotated[str, Field(description="取消原因")],
        send_notification: Annotated[bool, Field(description="是否发送取消通知")] = False,
    ) -> Any:
        """取消一条课程安排。"""
        return await client.post(
            f"/api/schedules/{schedule_id}/cancel",
            json={"cancel_reason": cancel_reason, "send_notification": _notify(send_notification)},
        )

    @tool(write=True)
    async def update_attendance(
        schedule_id: Annotated[int, Field(description="课程安排 ID")],
        student_attendance: Annotated[
            dict[str, str],
            Field(description="出勤字典，键为学员 ID 字符串，值为 present/absent/leave"),
        ],
        absence_reasons: Annotated[
            dict[str, str] | None, Field(description="缺勤原因字典，键为学员 ID 字符串")
        ] = None,
    ) -> Any:
        """更新某次课程的学员签到状态（出席/请假/缺席）。"""
        payload: dict[str, Any] = {
            "student_attendance": {int(k): v for k, v in student_attendance.items()}
        }
        if absence_reasons:
            payload["absence_reasons"] = {int(k): v for k, v in absence_reasons.items()}
        return await client.put(f"/api/schedules/{schedule_id}/attendance", json=payload)

    # ================================================================
    # 写操作：档案与请假
    # ================================================================
    @tool(write=True)
    async def create_leave(
        leave_type: Annotated[str, Field(description="请假类型：teacher 导师请假 / student 学员请假")],
        start_date: Annotated[str, Field(description="开始日期 YYYY-MM-DD")],
        end_date: Annotated[str, Field(description="结束日期 YYYY-MM-DD")],
        teacher_id: Annotated[int | None, Field(description="导师 ID（导师请假必填）")] = None,
        student_id: Annotated[int | None, Field(description="学员 ID（学员请假必填）")] = None,
        reason: Annotated[str | None, Field(description="请假原因")] = None,
    ) -> Any:
        """登记一条请假记录，后续排课会自动规避该时间段。"""
        if leave_type == "teacher" and not teacher_id:
            raise ToolError("导师请假必须提供 teacher_id。")
        if leave_type == "student" and not student_id:
            raise ToolError("学员请假必须提供 student_id。")
        return fmt.single(
            await client.post(
                "/api/leaves",
                json={
                    "leave_type": leave_type,
                    "teacher_id": teacher_id,
                    "student_id": student_id,
                    "start_date": f"{start_date}T00:00:00",
                    "end_date": f"{end_date}T23:59:59",
                    "reason": reason,
                },
            ),
            "leave",
        )

    @tool(write=True)
    async def create_student(
        code: Annotated[str, Field(description="学员代码，机构内唯一")],
        name: Annotated[str, Field(description="学员姓名")],
        class_ids: Annotated[list[int] | None, Field(description="所属班级 ID 列表")] = None,
        school: Annotated[str | None, Field(description="就读学校")] = None,
        grade: Annotated[str | None, Field(description="年级")] = None,
        contact_person: Annotated[str | None, Field(description="联系人（家长）")] = None,
        contact_phone: Annotated[str | None, Field(description="联系电话")] = None,
        email: Annotated[str | None, Field(description="电子邮箱，用于课程提醒邮件")] = None,
        enrollment_date: Annotated[str | None, Field(description="进入机构日期 YYYY-MM-DD")] = None,
    ) -> Any:
        """新增一名学员档案。"""
        return fmt.single(
            await client.post(
                "/api/students",
                json={
                    "code": code,
                    "name": name,
                    "class_ids": class_ids or [],
                    "school": school,
                    "grade": grade,
                    "contact_person": contact_person,
                    "contact_phone": contact_phone,
                    "email": email,
                    "enrollment_date": enrollment_date,
                    "is_active": True,
                },
            ),
            "student",
        )

    @tool(write=True)
    async def create_course(
        code: Annotated[str, Field(description="科目代码，机构内唯一")],
        name: Annotated[str, Field(description="科目名称")],
        parent_course_id: Annotated[int | None, Field(description="父科目 ID（用于建立科目层级）")] = None,
    ) -> Any:
        """新增一个科目。"""
        return fmt.single(
            await client.post(
                "/api/courses",
                json={
                    "code": code,
                    "name": name,
                    "parent_course_id": parent_course_id,
                    "is_active": True,
                },
            ),
            "course",
        )

    @tool(write=True, enabled=settings.allow_notifications)
    async def notify_schedule(
        schedule_id: Annotated[int, Field(description="课程安排 ID")],
    ) -> Any:
        """按当前状态向关联导师群/班级群推送课程安排通知（企业微信 / 邮件）。

        仅当部署时设置 COURSEMANAGE_MCP_ALLOW_NOTIFICATIONS=true 才会注册此工具。
        """
        return await client.post(f"/api/schedules/{schedule_id}/notify")

    # ================================================================
    # 资源与提示词
    # ================================================================
    @mcp.resource("coursemanage://today-schedules", mime_type="application/json")
    async def today_schedules_resource() -> dict[str, Any]:
        """今日课程安排（只读资源）。"""
        today = _iso(date.today())
        data = await client.get(
            "/api/schedules", start_date=today, end_date=today, skip=0, limit=settings.max_items
        )
        return fmt.paginated(data, "schedule", limit=settings.max_items)

    @mcp.resource("coursemanage://site-info", mime_type="application/json")
    async def site_info_resource() -> Any:
        """机构站点信息（只读资源）。"""
        return await client.get("/api/settings/site-info")

    @mcp.prompt()
    def daily_briefing(scope: str = "today") -> str:
        """生成当日课务简报的提示词。"""
        return (
            f"请使用 get_schedules_by_day(day='{scope}') 获取课程安排，"
            "并结合 list_schedule_conflicts 与 get_fee_alerts（若已授权）"
            "生成一份中文课务简报，包含：\n"
            "1. 今日课次总数、按时段列出的课表（时间 / 科目 / 导师 / 班级 / 教室）\n"
            "2. 存在冲突或未完训的课程，并给出处理建议\n"
            "3. 需要催缴课费的学员提醒\n"
            "输出使用简洁的中文列表，不要编造数据。"
        )

    @mcp.prompt()
    def conflict_review() -> str:
        """生成排课冲突排查的提示词。"""
        return (
            "请调用 list_schedule_conflicts 获取全部排课冲突，"
            "对每条冲突说明冲突主体（导师/教室/班级/学员）、冲突时间，"
            "并给出可行的调整方案（改时间、换教室或换导师）。"
            "如需候选教室请调用 list_rooms，如需导师工作量请调用 get_teacher_workload。"
        )

    return mcp
