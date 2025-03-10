import json
from pathlib import Path
from typing import Any, Dict

import pytest
from packaging.utils import canonicalize_name

from ..lib import PipTestEnvironment, TestData


def _install_dict(report: Dict[str, Any]) -> Dict[str, Any]:
    return {canonicalize_name(i["metadata"]["name"]): i for i in report["install"]}


def test_install_report_basic(
    script: PipTestEnvironment, shared_data: TestData, tmp_path: Path
) -> None:
    report_path = tmp_path / "report.json"
    script.pip(
        "install",
        "simplewheel",
        "--dry-run",
        "--no-index",
        "--find-links",
        str(shared_data.root / "packages/"),
        "--report",
        str(report_path),
    )
    report = json.loads(report_path.read_text())
    assert "install" in report
    assert len(report["install"]) == 1
    simplewheel_report = _install_dict(report)["simplewheel"]
    assert simplewheel_report["metadata"]["name"] == "simplewheel"
    assert simplewheel_report["requested"] is True
    assert simplewheel_report["is_direct"] is False
    url = simplewheel_report["download_info"]["url"]
    assert url.startswith("file://")
    assert url.endswith("/packages/simplewheel-2.0-1-py2.py3-none-any.whl")
    assert (
        simplewheel_report["download_info"]["archive_info"]["hash"]
        == "sha256=191d6520d0570b13580bf7642c97ddfbb46dd04da5dd2cf7bef9f32391dfe716"
    )


def test_install_report_dep(
    script: PipTestEnvironment, shared_data: TestData, tmp_path: Path
) -> None:
    """Test dependencies are present in the install report with requested=False."""
    report_path = tmp_path / "report.json"
    script.pip(
        "install",
        "require_simple",
        "--dry-run",
        "--no-index",
        "--find-links",
        str(shared_data.root / "packages/"),
        "--report",
        str(report_path),
    )
    report = json.loads(report_path.read_text())
    assert len(report["install"]) == 2
    assert _install_dict(report)["require-simple"]["requested"] is True
    assert _install_dict(report)["simple"]["requested"] is False


@pytest.mark.network
def test_install_report_index(script: PipTestEnvironment, tmp_path: Path) -> None:
    """Test report for sdist obtained from index."""
    report_path = tmp_path / "report.json"
    script.pip(
        "install",
        "--dry-run",
        "Paste[openid]==1.7.5.1",
        "--report",
        str(report_path),
    )
    report = json.loads(report_path.read_text())
    assert len(report["install"]) == 2
    install_dict = _install_dict(report)
    assert install_dict["paste"]["requested"] is True
    assert install_dict["python-openid"]["requested"] is False
    paste_report = install_dict["paste"]
    assert paste_report["download_info"]["url"].startswith(
        "https://files.pythonhosted.org/"
    )
    assert paste_report["download_info"]["url"].endswith("/Paste-1.7.5.1.tar.gz")
    assert (
        paste_report["download_info"]["archive_info"]["hash"]
        == "sha256=11645842ba8ec986ae8cfbe4c6cacff5c35f0f4527abf4f5581ae8b4ad49c0b6"
    )
    assert paste_report["requested_extras"] == ["openid"]
    assert "requires_dist" in paste_report["metadata"]


@pytest.mark.network
def test_install_report_direct_index(script: PipTestEnvironment, shared_data: TestData, tmp_path: Path) -> None:
    """Compare report for sdist obtained via direct url and sdist obtained from index"""
    report_direct_path = tmp_path / "report.json"
    package = shared_data.root / "packages" / "mypy-0.782-py3-none-any.whl"
    script.pip(
        "install",
        "--dry-run",
        f"{package}[dmypy]",
        "--report",
        str(report_direct_path),
    )
    report_direct = json.loads(report_direct_path.read_text())

    report_index_path = tmp_path / "report.json"
    script.pip(
        "install",
        "--dry-run",
        f"mypy[dmypy]==0.782",
        "--report",
        str(report_index_path),
    )
    report_index = json.loads(report_index_path.read_text())

    assert len(report_direct["install"]) == len(report_index["install"])
    for (direct, index) in zip(report_direct["install"], report_index["install"]):
        name = direct['metadata']['name']
        assert name == index['metadata']['name']
        if name != "mypy":
            continue

        assert direct["is_direct"] == True
        assert index["is_direct"] == False
        del direct["is_direct"]
        del index["is_direct"]

        assert direct["download_info"]["url"].startswith("file://")
        assert index["download_info"]["url"].startswith("https://")
        del direct["download_info"]["url"]
        del index ["download_info"]["url"]

        # TODO: Is this intended behaviour? 'hash' is equal, 'hashes' is missing
        # in direct installs.
        # assert "hashes" not in direct["download_info"]["archive_info"]
        # assert "hashes" in index["download_info"]["archive_info"]
        # del index["download_info"]["archive_info"]["hashes"]

        # TODO: this would be required to pass with pip 23.0.1, see
        # https://github.com/pypa/pip/issues/11946
        # assert "requested_extras" not in direct
        # assert index["requested_extras"] == ['dmypy']
        # del index["requested_extras"]

        assert direct == index


@pytest.mark.network
def test_install_report_vcs_and_wheel_cache(
    script: PipTestEnvironment, tmp_path: Path
) -> None:
    """Test report for VCS reference, and interactions with the wheel cache."""
    cache_dir = tmp_path / "cache"
    report_path = tmp_path / "report.json"
    script.pip(
        "install",
        "git+https://github.com/pypa/pip-test-package"
        "@5547fa909e83df8bd743d3978d6667497983a4b7",
        "--cache-dir",
        str(cache_dir),
        "--report",
        str(report_path),
    )
    report = json.loads(report_path.read_text())
    assert len(report["install"]) == 1
    pip_test_package_report = report["install"][0]
    assert pip_test_package_report["is_direct"] is True
    assert pip_test_package_report["requested"] is True
    assert (
        pip_test_package_report["download_info"]["url"]
        == "https://github.com/pypa/pip-test-package"
    )
    assert pip_test_package_report["download_info"]["vcs_info"]["vcs"] == "git"
    assert (
        pip_test_package_report["download_info"]["vcs_info"]["commit_id"]
        == "5547fa909e83df8bd743d3978d6667497983a4b7"
    )
    # Now do it again to make sure the cache is used and that the report still contains
    # the original VCS url.
    report_path.unlink()
    result = script.pip(
        "install",
        "pip-test-package @ git+https://github.com/pypa/pip-test-package"
        "@5547fa909e83df8bd743d3978d6667497983a4b7",
        "--ignore-installed",
        "--cache-dir",
        str(cache_dir),
        "--report",
        str(report_path),
    )
    assert "Using cached pip_test_package" in result.stdout
    report = json.loads(report_path.read_text())
    assert len(report["install"]) == 1
    pip_test_package_report = report["install"][0]
    assert pip_test_package_report["is_direct"] is True
    assert pip_test_package_report["requested"] is True
    assert (
        pip_test_package_report["download_info"]["url"]
        == "https://github.com/pypa/pip-test-package"
    )
    assert pip_test_package_report["download_info"]["vcs_info"]["vcs"] == "git"
    assert (
        pip_test_package_report["download_info"]["vcs_info"]["commit_id"]
        == "5547fa909e83df8bd743d3978d6667497983a4b7"
    )


@pytest.mark.network
def test_install_report_vcs_editable(
    script: PipTestEnvironment, tmp_path: Path
) -> None:
    """Test report remote editable."""
    report_path = tmp_path / "report.json"
    script.pip(
        "install",
        "--editable",
        "git+https://github.com/pypa/pip-test-package"
        "@5547fa909e83df8bd743d3978d6667497983a4b7"
        "#egg=pip-test-package",
        "--report",
        str(report_path),
    )
    report = json.loads(report_path.read_text())
    assert len(report["install"]) == 1
    pip_test_package_report = report["install"][0]
    assert pip_test_package_report["is_direct"] is True
    assert pip_test_package_report["download_info"]["url"].startswith("file://")
    assert pip_test_package_report["download_info"]["url"].endswith(
        "/src/pip-test-package"
    )
    assert pip_test_package_report["download_info"]["dir_info"]["editable"] is True


def test_install_report_to_stdout(
    script: PipTestEnvironment, shared_data: TestData
) -> None:
    result = script.pip(
        "install",
        "simplewheel",
        "--quiet",
        "--dry-run",
        "--no-index",
        "--find-links",
        str(shared_data.root / "packages/"),
        "--report",
        "-",
    )
    report = json.loads(result.stdout)
    assert "install" in report
    assert len(report["install"]) == 1
