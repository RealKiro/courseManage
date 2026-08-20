# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2024-2026 courseManage Contributors
"""把后端返回的臃肿 JSON 压缩成 LLM 友好的精简结构。

后端的列表接口会带上大量对排课算法有用、但对对话机器人无意义的字段
（可排课时间段、创建时间、内部标记等）。全部丢给大模型既浪费上下文，
也会干扰推理，因此这里为每类实体定义「紧凑投影」。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

WEEKDAYS = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}

EXECUTION_STATUS = {
    "pending": "待上课",
    "completed": "已完课",
    "postponed": "已延期",
    "cancelled": "已取消",
}

SCHEDULE_TYPE = {"formal": "正式课", "trial": "试读课"}

ATTENDANCE = {"present": "出席", "absent": "缺席", "leave": "请假"}


def _drop_empty(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if v not in (None, "", [], {})}


def _name_of(value: Any) -> str | None:
    if isinstance(value, Mapping):
        return value.get("name")
    return None


def course(item: Mapping[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "id": item.get("id"),
            "code": item.get("code"),
            "name": item.get("name"),
            "type": item.get("course_type"),
            "hours": item.get("total_hours"),
            "parent_course_id": item.get("parent_course_id"),
            "active": item.get("is_active"),
        }
    )


def teacher(item: Mapping[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "id": item.get("id"),
            "code": item.get("code"),
            "name": item.get("name"),
            "title": item.get("title"),
            "department": item.get("department"),
            "phone": item.get("contact_phone"),
            "email": item.get("email"),
            "max_weekly_hours": item.get("max_weekly_hours"),
            "course_ids": item.get("course_ids"),
            "active": item.get("is_active"),
        }
    )


def klass(item: Mapping[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "id": item.get("id"),
            "code": item.get("code"),
            "name": item.get("name"),
            "description": item.get("description"),
            "active": item.get("is_active"),
        }
    )


def student(item: Mapping[str, Any]) -> dict[str, Any]:
    classes = item.get("classes") or []
    class_names = [c.get("name") for c in classes if isinstance(c, Mapping) and c.get("name")]
    return _drop_empty(
        {
            "id": item.get("id"),
            "code": item.get("code"),
            "name": item.get("name"),
            "school": item.get("school"),
            "grade": item.get("grade"),
            "classes": class_names or item.get("class_ids"),
            "contact_person": item.get("contact_person"),
            "phone": item.get("contact_phone"),
            "email": item.get("email"),
            "enrollment_date": item.get("enrollment_date"),
            "active": item.get("is_active"),
        }
    )


def room(item: Mapping[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "id": item.get("id"),
            "code": item.get("code"),
            "name": item.get("name"),
            "location": item.get("location"),
            "capacity": item.get("capacity"),
            "facilities": item.get("facilities"),
            "active": item.get("is_active"),
        }
    )


def schedule(item: Mapping[str, Any]) -> dict[str, Any]:
    dow = item.get("day_of_week")
    students = item.get("scheduled_students") or []
    attendance_summary: dict[str, int] = {}
    for entry in students:
        if not isinstance(entry, Mapping):
            continue
        label = ATTENDANCE.get(entry.get("attendance_status") or "", "未标记")
        attendance_summary[label] = attendance_summary.get(label, 0) + 1

    return _drop_empty(
        {
            "id": item.get("id"),
            "date": (
                item.get("start_date")
                if item.get("start_date") == item.get("end_date")
                else f"{item.get('start_date')} ~ {item.get('end_date')}"
            ),
            "weekday": WEEKDAYS.get(dow, dow),
            "time": f"{item.get('start_time')}-{item.get('end_time')}",
            "course": _name_of(item.get("course")),
            "teacher": _name_of(item.get("teacher")),
            "class": _name_of(item.get("class_")),
            "room": _name_of(item.get("room")) or item.get("meeting_link"),
            "room_type": "线上" if item.get("room_type") == "online_virtual" else "线下",
            "status": EXECUTION_STATUS.get(item.get("execution_status") or "", item.get("execution_status")),
            "type": SCHEDULE_TYPE.get(item.get("schedule_type") or "", item.get("schedule_type")),
            "conflict": item.get("conflict_reason") if item.get("has_conflict") else None,
            "student_count": len(students) or None,
            "attendance": attendance_summary or None,
            "feedback": item.get("content_feedback"),
        }
    )


def leave(item: Mapping[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "id": item.get("id"),
            "type": item.get("leave_type"),
            "teacher_id": item.get("teacher_id"),
            "student_id": item.get("student_id"),
            "start": item.get("start_date"),
            "end": item.get("end_date"),
            "reason": item.get("reason"),
        }
    )


def holiday(item: Mapping[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "id": item.get("id"),
            "date": item.get("date"),
            "name": item.get("name"),
            "description": item.get("description"),
        }
    )




def grade(item: Mapping[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "id": item.get("id"),
            "student": item.get("student_name"),
            "course": item.get("course_name"),
            "grade_level": item.get("grade_level"),
            "exam_stage": item.get("exam_stage"),
            "exam_date": item.get("exam_date"),
            "score": item.get("score"),
            "total_score": item.get("total_score"),
            "score_change": item.get("score_change"),
            "note": item.get("description"),
        }
    )


PROJECTORS: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {
    "course": course,
    "teacher": teacher,
    "class": klass,
    "student": student,
    "room": room,
    "schedule": schedule,
    "leave": leave,
    "holiday": holiday,
    "grade": grade,
}


def paginated(
    payload: Any,
    kind: str,
    *,
    limit: int,
    offset: int = 0,
    verbose: bool = False,
) -> dict[str, Any]:
    """统一列表返回结构：``{total, returned, offset, items}``。"""
    if isinstance(payload, Mapping):
        items: Iterable[Any] = payload.get("items") or []
        total = payload.get("total")
    elif isinstance(payload, list):
        items = payload
        total = len(payload)
    else:  # pragma: no cover - 后端返回了非预期结构
        return {"total": None, "returned": 0, "items": [], "raw": payload}

    items = list(items)
    projector = PROJECTORS.get(kind)
    if projector and not verbose:
        rendered = [projector(i) for i in items if isinstance(i, Mapping)]
    else:
        rendered = items

    truncated = len(rendered) > limit
    result: dict[str, Any] = {
        "total": total if total is not None else len(rendered),
        "returned": min(len(rendered), limit),
        "offset": offset,
        "items": rendered[:limit],
    }
    if truncated:
        result["note"] = f"结果已截断为 {limit} 条，请使用 offset/更精确的筛选条件继续查询。"
    return result


def single(payload: Any, kind: str, *, verbose: bool = False) -> Any:
    projector = PROJECTORS.get(kind)
    if projector and not verbose and isinstance(payload, Mapping):
        return projector(payload)
    return payload
