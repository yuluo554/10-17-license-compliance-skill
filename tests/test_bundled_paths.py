# -*- coding: utf-8 -*-
"""随包资源定位守门（源码态 ↔ 安装态）。

阶段三实测坑：`default_spdx_dir()` 原先只按「打包文件位置」上溯三级，源码态得到仓库根没问题，
但 **wheel 安装后**这里是 ``<venv>/Lib``，于是 `licaudit assess` 报「SPDX 快照不可读（exit 2）」——
`pip install licaudit` 装完不能用。规则包一路（`ruleset.loader.candidate_dirs`）同样需要两处都找。

本文件把「两处都找」这件事锁死：真实仓库态 + 造一个假的安装态布局（monkeypatch `resource_roots`）。
"""

import io
import os

import pytest

from _helpers import REPO_ROOT

from licaudit.inventory import spdx_snapshot
from licaudit.ruleset import loader


def test_resource_roots_are_repo_root_then_site_packages():
    roots = loader.resource_roots()
    assert len(roots) == 2
    repo_root, installed_root = roots
    assert os.path.abspath(repo_root) == os.path.abspath(REPO_ROOT)
    assert os.path.abspath(installed_root) == os.path.abspath(os.path.join(REPO_ROOT, "src"))
    # 第一个根必须真的是「源码态仓库根」，否则规则包候选会先撞到错位置
    assert os.path.isfile(os.path.join(repo_root, "pyproject.toml"))
    assert loader.repo_root_from_package() == repo_root


def test_default_spdx_dir_points_at_an_existing_snapshot():
    spdx_dir = spdx_snapshot.default_spdx_dir()
    assert spdx_dir.endswith(os.path.join("references", "spdx")), spdx_dir
    for name in (spdx_snapshot.LICENSES_FILE, spdx_snapshot.EXCEPTIONS_FILE,
                 spdx_snapshot.MANIFEST_FILE):
        assert os.path.isfile(os.path.join(spdx_dir, name)), name


def test_installed_layout_is_found_when_repo_root_has_no_references(tmp_path, monkeypatch):
    """造一个「安装态」布局：第一候选根没有 references/，第二候选根才有。"""
    fake_repo = tmp_path / "Lib"
    site_packages = fake_repo / "site-packages"
    (site_packages / "references" / "spdx").mkdir(parents=True)
    (site_packages / "references" / "ruleset").mkdir(parents=True)
    (site_packages / "references" / "spdx" / spdx_snapshot.LICENSES_FILE).write_text("{}", encoding="utf-8")
    (site_packages / "references" / "ruleset" / "manifest.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(loader, "resource_roots", lambda: [str(fake_repo), str(site_packages)])

    assert spdx_snapshot.default_spdx_dir() == str(site_packages / "references" / "spdx")
    candidates = loader.candidate_dirs()
    assert str(site_packages / "references" / "ruleset") in candidates
    assert str(fake_repo / "references" / "ruleset") in candidates


def test_missing_snapshot_raises_usage_error(tmp_path, monkeypatch):
    """两处都没有 → 明确报错（exit 2 语义），而不是静默降级。"""
    from licaudit.errors import UsageError

    empty_a = tmp_path / "a"
    empty_b = tmp_path / "b"
    empty_a.mkdir()
    empty_b.mkdir()
    monkeypatch.setattr(loader, "resource_roots", lambda: [str(empty_a), str(empty_b)])
    with pytest.raises(UsageError):
        spdx_snapshot.load_snapshot()