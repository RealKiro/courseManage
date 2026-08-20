# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2024-2026 courseManage Contributors
"""课时费模块占位（本部署已移除费用功能）。

背景
----
上游版本面向中小学，内置一整套课时费体系：
学生课费项（课时单价 × 课节数）、缴费/退费记录、按课自动扣减课时、
剩余课时预警与催缴提醒、课费报表导出等，共 18 个接口。

本仓库用于**中小学教务管理**。义务教育阶段不存在按课时向学生收费的场景，
「课费」「催缴」「退费」等概念不适用，因此已整体移除：

  * 删除本文件原有的全部业务逻辑与 18 个 ``/api/fees/*`` 接口
  * ``main.py`` 不再注册本路由
  * 删除 ``statistics.py`` 中 10 个 ``/fees/*`` 报表接口
  * KPI 的收入/退费/欠费/转化率/续费率固定为 0
  * 前端隐藏费用管理菜单、页面与运营大屏的费用图表
  * 移除 MCP 的课费类工具

为什么保留本文件而不是直接删除
------------------------------
``consume_hours_with_attendance`` 与 ``recalculate_consumed_hours``
被 ``routers/schedules.py``（3 处）与 ``utils/smart_command.py``（1 处）调用，
而这些调用点**同时承担了别的职责**——例如课程完课时若没有出勤记录，
会先按班级活跃学生批量创建「全部出席」的记录。
直接删除调用块会连带破坏考勤功能，因此这里保留同名空操作函数，
调用点无需任何改动。

数据库中的 ``student_fees`` / ``fee_logs`` 表与 ``models.py`` 中对应的
ORM 模型刻意保留：删除模型会影响 SQLAlchemy 映射关系，
保留则既无副作用，也不会破坏已有部署的历史数据（便于回滚）。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = ["consume_hours_with_attendance", "recalculate_consumed_hours"]


def consume_hours_with_attendance(schedule_id, db=None, current_user=None):
    """空操作：原用于课程完课后按出勤扣减学生剩余课时。

    签名与上游保持一致（``schedule_id`` / ``db`` / ``current_user``），
    因此 schedules.py 与 smart_command.py 的调用点无需修改。
    """
    logger.debug("费用模块已移除，跳过课时扣减（schedule_id=%s）", schedule_id)
    return None


def recalculate_consumed_hours(schedule_id, db=None, current_user=None):
    """空操作：原用于出勤变更后重算已消耗课时。"""
    logger.debug("费用模块已移除，跳过课时重算（schedule_id=%s）", schedule_id)
    return None
