"""A Windows client must never serialize backslashes as Linux Volume paths."""

from pathlib import PurePosixPath, PureWindowsPath

from modal_app.scorecard_paths import checkpoint_name, remote_checkpoint_path


def test_remote_checkpoint_paths_are_posix_even_on_windows():
    site = {"id": "forest-loss-va-01", "split": "holdout"}
    remote = remote_checkpoint_path(site)
    assert remote.startswith("/data/scorecard/paired-v1/")
    assert "\\" not in remote
    assert PurePosixPath(remote).name == checkpoint_name(site)
    assert str(PureWindowsPath("/data") / "scorecard") != remote


def test_cache_identity_is_stable_but_different_splits_cannot_share_checkpoints():
    a = {"id": "sample", "kind": "fire", "split": "train"}
    b = {"split": "train", "kind": "fire", "id": "sample"}
    assert checkpoint_name(a) == checkpoint_name(b)
    assert checkpoint_name(a) != checkpoint_name({**a, "split": "holdout"})
