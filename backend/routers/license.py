# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2024-2026 courseManage Contributors
"""授权门禁占位模块（本部署已放开全部高级功能）。

背景
----
上游版本通过 RSA 签名的 License Key 对 9 项高级功能做门禁，并会向供应商的
企业微信 webhook / 心跳服务回传学校名称、联系人、机器码等信息。

本仓库为 AGPL-3.0 下的自用分支，已：
  * 删除 ``utils/license.py``（RSA 验签、机器码、心跳、供应商发现）
  * 移除 ``main.py`` 中的 ``premium_feature_guard`` 中间件
  * 移除全部向供应商回传数据的接口

为什么保留本文件而不是一并删除：
  ``_check_premium_feature`` 被 11 个模块（fees / grades / evaluations /
  database / wechat / settings / schedules / smart_command 等）引用。
  保留这一个恒真函数，就能一次性放开所有调用点，无需改动那 11 个文件，
  改动面最小、回归风险最低。

同时保留少量只读接口，让前端「系统授权管理」页面仍能正常渲染。
"""

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Settings
from routers.auth import get_current_user, User

router = APIRouter(prefix="/license", tags=["系统授权"])

# 9 项原高级功能标识（保留常量，供前端与其他模块引用）
PREMIUM_FEATURES = [
    "grade_trend",
    "fee_management",
    "smart_scheduling",
    "wechat_notify",
    "smart_command",
    "dashboard_view",
    "floating_sphere",
    "database_management",
    "student_evaluation",
]

FEATURE_NAMES = {
    "grade_trend": "学生成绩管理",
    "fee_management": "费用管理",
    "smart_scheduling": "智能算法排课",
    "wechat_notify": "微信通知管理",
    "smart_command": "智能指令管理",
    "dashboard_view": "运营大屏",
    "floating_sphere": "全站快捷按钮",
    "database_management": "数据库管理",
    "student_evaluation": "学生评价管理",
}

_OPEN_NOTICE = "本部署已放开全部高级功能，无需授权。"


def _check_premium_feature(feature_name: str, db: Session) -> bool:
    """恒返回 True —— 门禁已移除。

    签名与上游保持一致（``feature_name`` / ``db``），因此那 11 个调用点
    无需任何修改。参数刻意保留但不使用。
    """
    return True


def _all_features_enabled() -> dict:
    return {feature: True for feature in PREMIUM_FEATURES}


# ---------------------------------------------------------------- 只读兼容接口
class FeatureCheckResponse(BaseModel):
    feature: str
    enabled: bool


class LicenseStatusResponse(BaseModel):
    activated: bool = True
    license_type: str = "perpetual"
    license_type_name: str = "自用版（已放开全部功能）"
    organization_name: str = ""
    features: dict = {}
    expiry_date: Optional[str] = None
    issued_at: Optional[str] = None
    machine_code: str = ""
    trial_available: bool = False
    deactivated_licenses: list = []
    license_key: str = ""
    referral_code: str = ""
    referral_activated: bool = False
    referral_threshold: float = 0
    discount_percent: float = 0
    rebate_percent: float = 0
    total_spending: float = 0
    site_name: str = ""
    contact_person: str = ""
    contact_phone: str = ""
    contact_email: str = ""
    contact_wechat: str = ""
    notice: str = _OPEN_NOTICE


@router.get("/status", response_model=LicenseStatusResponse)
def get_license_status(db: Session = Depends(get_db)):
    """返回「已激活、全部功能可用」的固定状态。

    仍从 settings 读取学校与联系人信息，让前端页面展示保持正常。
    """
    settings = db.query(Settings).first()

    def field(name: str) -> str:
        if not settings:
            return ""
        return getattr(settings, name, "") or ""

    return LicenseStatusResponse(
        features=_all_features_enabled(),
        organization_name=field("site_name"),
        site_name=field("site_name"),
        contact_person=field("contact_person"),
        contact_phone=field("contact_phone"),
        contact_email=field("contact_email"),
        contact_wechat=field("contact_wechat"),
    )


@router.get("/features", response_model=List[FeatureCheckResponse])
def list_features(current_user: User = Depends(get_current_user)):
    """列出全部功能，均为启用状态。"""
    return [FeatureCheckResponse(feature=f, enabled=True) for f in PREMIUM_FEATURES]


@router.get("/check/{feature_name}", response_model=FeatureCheckResponse)
def check_feature(feature_name: str, current_user: User = Depends(get_current_user)):
    """单个功能检查，恒为启用。"""
    return FeatureCheckResponse(feature=feature_name, enabled=True)


@router.get("/machine-code")
def get_machine_code(current_user: User = Depends(get_current_user)):
    """机器码机制已随授权校验一并移除。

    保留接口只为兼容前端调用；不再读写 ``/app/backups/.machine_id``，
    因此删除数据卷也不会再导致「授权失效」。
    """
    return {"machine_code": "", "notice": "机器码机制已移除（门禁已放开）。"}


# ---------------------------------------------------------------- 写操作占位
class LicenseActionResponse(BaseModel):
    success: bool
    message: str


@router.post("/activate", response_model=LicenseActionResponse)
def activate_license(current_user: User = Depends(get_current_user)):
    """无需激活。保留接口避免前端按钮 404。"""
    return LicenseActionResponse(success=True, message=_OPEN_NOTICE)


@router.post("/deactivate", response_model=LicenseActionResponse)
def deactivate_license(current_user: User = Depends(get_current_user)):
    """不提供停用能力：门禁已移除，停用没有意义。"""
    return LicenseActionResponse(
        success=False, message="门禁已移除，无法停用；如需恢复门禁请还原 routers/license.py。"
    )


@router.post("/deactivate-feature/{feature_name}", response_model=LicenseActionResponse)
def deactivate_feature(feature_name: str, current_user: User = Depends(get_current_user)):
    """同上，单功能停用同样不再支持。"""
    return LicenseActionResponse(
        success=False, message="门禁已移除，无法停用单个功能。"
    )


# ---------------------------------------------------------------- 已禁用的对外回传
# 上游这几个接口会把学校名称、联系人、电话、邮箱、机器码等发送到供应商的
# 企业微信 webhook 与邮箱。自用部署没有这个需要，故只保留空实现，
# 既不发送任何数据，也不会让前端按钮变成 404。
_NO_UPSTREAM = "本部署已移除向供应商回传数据的通道，未发送任何信息。"


@router.post("/apply", response_model=LicenseActionResponse)
def apply_license(payload: Optional[dict] = None, current_user: User = Depends(get_current_user)):
    """原「申请授权」：不再向供应商发送学校与联系人信息。"""
    return LicenseActionResponse(success=False, message=_NO_UPSTREAM)


@router.post("/preview-addon", response_model=LicenseActionResponse)
def preview_addon_license(payload: Optional[dict] = None, current_user: User = Depends(get_current_user)):
    """原「预览增购」：授权体系已移除。"""
    return LicenseActionResponse(success=False, message=_OPEN_NOTICE)


@router.post("/notify-supplier-view", response_model=LicenseActionResponse)
def notify_supplier_view(payload: Optional[dict] = None):
    """原「通知供应商查看」：已禁用。"""
    return LicenseActionResponse(success=False, message=_NO_UPSTREAM)


@router.post("/request-replace", response_model=LicenseActionResponse)
def request_replace_license(payload: Optional[dict] = None):
    """原「申请换机」：机器码机制已移除，不再需要换机。"""
    return LicenseActionResponse(success=False, message=_NO_UPSTREAM)


@router.post("/feedback", response_model=LicenseActionResponse)
def submit_feedback(payload: Optional[dict] = None):
    """原「功能/系统反馈」：不再回传到供应商 webhook。

    如需保留反馈功能，可在此改为只发送到本校自己配置的 SMTP 邮箱。
    """
    return LicenseActionResponse(success=False, message=_NO_UPSTREAM)
