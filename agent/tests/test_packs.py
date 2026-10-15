import shutil

import pytest
import yaml

from dejafix_agent.packs import PackError, find_packs_dir, load_pack


def test_test_pack_loads(test_pack):
    assert set(test_pack.actions) == {
        "t_look",
        "t_tweak",
        "t_tweak_norollback",
        "t_smash",
    }
    assert test_pack.default_tier == "C"
    assert test_pack.fallback_plans == {"heat": ["t_look", "t_tweak"]}
    assert "analyze" in test_pack.prompts


def test_classify_key(test_pack):
    assert test_pack.classify_key("probe.temp") == "heat"
    assert test_pack.classify_key("probe.db[mic2]") == "noise"
    assert test_pack.classify_key("unknown.key") is None


def test_allowed_actions_text_lists_ids(test_pack):
    text = test_pack.allowed_actions_text()
    assert "t_look" in text and "tier A" in text


def test_missing_pack_fails(packs_dir):
    with pytest.raises(PackError):
        load_pack("nope", packs_dir)


def test_fallback_unknown_id_fails(tmp_path, packs_dir):
    shutil.copytree(packs_dir / "test", tmp_path / "bad")
    actions = tmp_path / "bad" / "actions.yaml"
    data = yaml.safe_load(actions.read_text(encoding="utf-8"))
    data["fallback_plans"]["heat"].append("no_such_action")
    actions.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(PackError):
        load_pack("bad", tmp_path)


def test_missing_metrics_file_fails(tmp_path, packs_dir):
    shutil.copytree(packs_dir / "test", tmp_path / "nometrics")
    (tmp_path / "nometrics" / "metrics.yaml").unlink()
    with pytest.raises(PackError):
        load_pack("nometrics", tmp_path)


def test_it_pack_actions_are_consistent():
    # packs/it/actions.yaml 자체 점검: fallback ID 존재, B 동작에 precheck·rollback (packs/it/README 검증 절)
    data = yaml.safe_load(
        (find_packs_dir() / "it" / "actions.yaml").read_text(encoding="utf-8")
    )
    ids = {a["id"] for a in data["actions"]}
    assert data["default_tier"] == "C"
    for alias, plan in data["fallback_plans"].items():
        assert set(plan) <= ids, alias
    for a in data["actions"]:
        assert a["tier"] in ("A", "B", "C")
        if a["tier"] == "B":
            assert a.get("precheck") and a.get("rollback"), a["id"]
