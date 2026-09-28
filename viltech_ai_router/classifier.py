"""Classify provider errors without treating arbitrary task failures as failover signals."""

import re
from .models import ErrorCategory

PATTERNS = (
    (ErrorCategory.RATE_LIMIT, (r"\b429\b", r"rate[ _-]?limit", r"too many requests", r"tpm limit", r"rpm limit")),
    (ErrorCategory.QUOTA_EXHAUSTED, (r"quota[ _-]?exceeded", r"insufficient[ _-]?quota", r"resource[ _-]?exhausted", r"credits?[ _-]?exhausted", r"billing[ _-]?hard[ _-]?limit", r"balance depleted", r"zero credits", r"out of quota")),
    (ErrorCategory.AUTH_ERROR, (r"\b401\b", r"\b403\b", r"unauthorized", r"authentication failed", r"auth[ _-]?failed", r"invalid[ _-]?(?:token|api[ _-]?key)", r"token expired", r"login required", r"access denied")),
    (
        ErrorCategory.PROVIDER_TIMEOUT,
        (
            r"request (?:timed out|timeout)",
            r"context deadline exceeded",
            r"deadline exceeded",
            r"gateway timeout",
            r"upstream.*(?:timed out|timeout)",
            r"provider.*(?:timed out|timeout)",
        ),
    ),
    (ErrorCategory.PROVIDER_DOWN, (r"\b50[0234]\b", r"bad gateway", r"service unavailable", r"provider down", r"connection refused", r"network unreachable", r"failed to connect to host", r"upstream connect error")),
    (ErrorCategory.TASK_FAILURE, (r"syntaxerror", r"assertionerror", r"compilation error", r"traceback \(most recent call last\)", r"failed to build", r"tests? failed", r"linter error")),
)
INFRA = {ErrorCategory.RATE_LIMIT, ErrorCategory.QUOTA_EXHAUSTED, ErrorCategory.AUTH_ERROR,
         ErrorCategory.PROVIDER_TIMEOUT, ErrorCategory.PROVIDER_DOWN, ErrorCategory.OFFLINE}


def classify_error(exit_code: int, stdout: str, stderr: str) -> tuple[ErrorCategory, bool]:
    if exit_code == 0:
        return ErrorCategory.NONE, False
    output = f"{stdout}\n{stderr}"
    for category, patterns in PATTERNS:
        if any(re.search(pattern, output, re.IGNORECASE) for pattern in patterns):
            return category, category in INFRA
    return ErrorCategory.UNKNOWN_ERROR, False
