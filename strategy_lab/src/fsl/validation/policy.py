"""Политики валидации как версионируемая конфигурация.

Разбор архитектуры, пункт 4: документ 05 замораживает перед OOS формулу,
признаки, пороги, окна, таргет и просмотренные данные — но не критерий, по
которому результат будет признан прохождением. Здесь критерий такой же
first-class объект: он грузится из YAML, хэшируется и попадает в заморозку.
Изменение критерия после просмотра OOS обнаруживается сверкой хэша.
"""
from __future__ import annotations

import dataclasses as dc
from pathlib import Path
from typing import Any

import yaml

from fsl.hashing import stable_hash

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


@dc.dataclass(frozen=True)
class Policy:
    name: str
    version: str
    payload: dict[str, Any]

    @property
    def hash(self) -> str:
        return stable_hash({"name": self.name, "version": self.version,
                            "payload": self.payload})

    def get(self, *path, default=None):
        node = self.payload
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


def load_policy(filename: str, name: str, config_dir: Path | None = None) -> Policy:
    path = (config_dir or CONFIG_DIR) / filename
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Policy(name=name, version=payload.get("version", "unversioned"), payload=payload)


def qualification_policy(config_dir: Path | None = None) -> Policy:
    return load_policy("qualification_policy.yaml", "QUALIFICATION_POLICY", config_dir)


def statistical_policy(config_dir: Path | None = None) -> Policy:
    return load_policy("statistical_policy.yaml", "STATISTICAL_POLICY", config_dir)


def research_policy(config_dir: Path | None = None) -> Policy:
    return load_policy("research_policy.yaml", "RESEARCH_POLICY", config_dir)
