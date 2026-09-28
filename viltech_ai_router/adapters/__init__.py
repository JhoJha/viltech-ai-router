"""Known provider adapter factory; no generic or unsafe fallback."""

from .agy import AgyAdapter
from .base import BaseAdapter
from .codex import CodexAdapter
from .opencode import OpenCodeAdapter
from ..models import ResourceConfig

ADAPTER_CLASSES = {"agy": AgyAdapter, "opencode": OpenCodeAdapter, "codex": CodexAdapter}


def create_adapter(config: ResourceConfig) -> BaseAdapter:
    return ADAPTER_CLASSES[config.adapter](config)
