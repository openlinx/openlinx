"""Initialising without the CLI (010-add-workspace-and-cli-contract, workspace)."""

from spider.output.reporter import Collected
from spider.services.workspace import InitRequest, init_workspace
from spider.workspace.tables import SettingsTables
from tests.support.workspace import TempWorkspace


def test_initialising_without_the_cli(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.root / "shop"
    (shop / ".spider").mkdir(parents=True)
    blog = shop / "blog"
    data = blog / ".spider"
    reporter = Collected()
    request = InitRequest(cwd=temp_workspace.root, home=temp_workspace.home, workspace=blog)

    result = init_workspace(request, SettingsTables(), reporter)

    assert (
        result.created,
        [(warning.code, warning.details) for warning in reporter.warnings],
    ) == (
        [data, data / ".gitignore", data / "crawls", blog / "spider.toml"],
        [("workspace_nested", {"parent": str(shop)})],
    )
