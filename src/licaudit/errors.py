# -*- coding: utf-8 -*-
"""领域异常。

所有异常都继承 :class:`ValueError`，因为 CLI 只捕获 ``(UsageError, RulesetError)``；
继承裸 ``Exception`` 会让「该报的错」变成未捕获 traceback。
"""


class LicAuditError(ValueError):
    """本项目所有领域异常的基类。"""

    code = "error"

    def __init__(self, message, **details):
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self):
        if not self.details:
            return self.message
        rendered = ", ".join(
            "{0}={1}".format(key, self.details[key]) for key in sorted(self.details)
        )
        return "{0} ({1})".format(self.message, rendered)


class UsageError(LicAuditError):
    """用法或输入问题 → exit 2。"""

    code = "usage_error"


class RulesetError(LicAuditError):
    """规则包缺失或校验失败 → exit 3。"""

    code = "ruleset_error"
