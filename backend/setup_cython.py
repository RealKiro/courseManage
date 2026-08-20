# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2024-2026 courseManage Contributors
from setuptools import setup, Extension
from Cython.Build import cythonize
import os

# 注意：license 相关模块已从本列表移除。
# 本分支已放开全部高级功能，utils/license.py 已删除，
# routers/license.py 改为恒真的占位实现，无需再做源码保护。
CRITICAL_MODULES = [
    "optimizer.py",
    "utils/smart_command.py",
    "utils/wechat_notifier.py",
    "utils/remainder.py",
]

extensions = [
    Extension(
        module.replace("/", ".").replace(".py", ""),
        [module],
    )
    for module in CRITICAL_MODULES
]

setup(
    name="courseManage-protected",
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
            "cdivision": True,
        },
        force=True,
    ),
)