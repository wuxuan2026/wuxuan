"""MySQL 连接配置 CRUD + 加密存储测试。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch):
    """让 mysql_config_service 用临时文件，避免污染 data/。"""
    import app.services.mysql_config_service as svc
    cfg_file = tmp_path / "mysql_connections.yaml"
    key_file = tmp_path / ".secret_key"
    monkeypatch.setattr(svc, "CONFIG_PATH", cfg_file)
    monkeypatch.setattr(svc, "SECRET_KEY_PATH", key_file)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    # 重置内部 fernet 缓存（如果有）
    return svc


def test_encrypt_decrypt_roundtrip(isolated_config):
    cipher = isolated_config.encrypt_password("hello@world#123")
    assert cipher != "hello@world#123"
    assert isolated_config.decrypt_password(cipher) == "hello@world#123"


def test_encrypt_different_each_time(isolated_config):
    """Fernet 加密有随机 IV，每次结果不同。"""
    a = isolated_config.encrypt_password("same")
    b = isolated_config.encrypt_password("same")
    assert a != b
    # 但都能解出原文
    assert isolated_config.decrypt_password(a) == "same"
    assert isolated_config.decrypt_password(b) == "same"


def test_decrypt_invalid_returns_empty(isolated_config):
    assert isolated_config.decrypt_password("not-a-valid-token") == ""
    assert isolated_config.decrypt_password("") == ""


def test_upsert_and_get(isolated_config):
    isolated_config.upsert_connection(
        name="DEFAULT", host="127.0.0.1", user="root",
        password="secret", database="mydb", port=3306,
    )
    cfg = isolated_config.get_connection("DEFAULT")
    assert cfg["host"] == "127.0.0.1"
    assert cfg["user"] == "root"
    assert cfg["database"] == "mydb"
    # 密码必须是密文
    assert cfg["password"] != "secret"
    assert isolated_config.decrypt_password(cfg["password"]) == "secret"


def test_upsert_update_keeps_password_on_mask(isolated_config):
    """编辑时传 password=****** 应保留原密码。"""
    isolated_config.upsert_connection(
        name="C1", host="h", user="u", password="orig", database="d",
    )
    # 编辑其他字段，password 传 ****** → 保留原密码
    isolated_config.upsert_connection(
        name="C1", host="new-host", user="u", password="******", database="d",
    )
    cfg = isolated_config.get_connection("C1")
    assert cfg["host"] == "new-host"
    assert isolated_config.decrypt_password(cfg["password"]) == "orig"


def test_upsert_update_overwrites_password(isolated_config):
    """编辑时传新密码 → 覆盖。"""
    isolated_config.upsert_connection(name="C1", host="h", user="u", password="orig", database="d")
    isolated_config.upsert_connection(name="C1", host="h", user="u", password="new", database="d")
    cfg = isolated_config.get_connection("C1")
    assert isolated_config.decrypt_password(cfg["password"]) == "new"


def test_delete(isolated_config):
    isolated_config.upsert_connection(name="C1", host="h", user="u", password="p", database="d")
    assert isolated_config.delete_connection("C1") is True
    assert isolated_config.get_connection("C1") is None
    # 删不存在的连接返回 False
    assert isolated_config.delete_connection("C1") is False


def test_list_masked_never_returns_plaintext(isolated_config):
    isolated_config.upsert_connection(
        name="C1", host="h", user="u", password="supersecret", database="d",
    )
    for c in isolated_config.list_connections_masked():
        assert c["password"] == "******"
        assert "supersecret" not in str(c)


def test_persisted_file_does_not_contain_plaintext(isolated_config):
    """YAML 文件里不应有明文密码。"""
    isolated_config.upsert_connection(
        name="C1", host="h", user="u", password="plainpw", database="d",
    )
    content = isolated_config.CONFIG_PATH.read_text(encoding="utf-8")
    assert "plainpw" not in content
    data = yaml.safe_load(content)
    assert data["connections"][0]["password"] != "plainpw"


def test_get_connection_for_loader_prefers_yaml(isolated_config):
    """loader 应该读 YAML 配置，而不是只读 env。"""
    isolated_config.upsert_connection(
        name="DEFAULT", host="yaml-host", user="yaml-user",
        password="yaml-pw", database="yaml-db",
    )
    cfg = isolated_config.get_connection_for_loader(None)
    assert cfg["host"] == "yaml-host"
    assert cfg["user"] == "yaml-user"
    assert cfg["password"] == "yaml-pw"
    assert cfg["database"] == "yaml-db"


def test_get_connection_for_loader_falls_back_to_env(isolated_config, monkeypatch):
    """没 YAML 配置时 fallback 到环境变量。"""
    monkeypatch.setenv("MYSQL_FALLBACK_HOST", "env-host")
    monkeypatch.setenv("MYSQL_FALLBACK_USER", "env-user")
    monkeypatch.setenv("MYSQL_FALLBACK_PASSWORD", "env-pw")
    monkeypatch.setenv("MYSQL_FALLBACK_DATABASE", "env-db")
    cfg = isolated_config.get_connection_for_loader("FALLBACK")
    assert cfg["host"] == "env-host"
    assert cfg["database"] == "env-db"


def test_secret_key_from_env_overrides_file(tmp_path: Path, monkeypatch):
    """环境变量 SECRET_KEY 优先于文件。"""
    import app.services.mysql_config_service as svc
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    monkeypatch.setenv("SECRET_KEY", "base64:" + key.decode("ascii"))
    f = svc._get_or_create_fernet()
    assert f._signing_key == Fernet(key)._signing_key


# ----------------- 路由测试 -----------------


def test_connections_page_renders(isolated_config):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.get("/mysql/connections")
    assert r.status_code == 200
    text = r.content.decode("utf-8")
    assert "MySQL 连接管理" in text
    assert "新增连接" in text


def test_create_connection_via_form(isolated_config):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post(
        "/mysql/connections/new",
        data={
            "name": "TESTCONN",
            "host": "127.0.0.1",
            "port": "3306",
            "user": "root",
            "password": "secret",
            "database": "mydb",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    # 配置已写入
    cfg = isolated_config.get_connection("TESTCONN")
    assert cfg["host"] == "127.0.0.1"


def test_create_duplicate_rejected(isolated_config):
    isolated_config.upsert_connection(name="DUP", host="h", user="u", password="p", database="d")
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post(
        "/mysql/connections/new",
        data={"name": "DUP", "host": "h2", "user": "u", "password": "p", "database": "d"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "name_exists" in r.headers["location"]


def test_edit_page_renders(isolated_config):
    isolated_config.upsert_connection(name="EDIT", host="h", user="u", password="p", database="d")
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.get("/mysql/connections/EDIT/edit")
    assert r.status_code == 200
    text = r.content.decode("utf-8")
    assert "EDIT" in text
    assert "******" in text  # 密码掩码


def test_delete_via_form(isolated_config):
    isolated_config.upsert_connection(name="DEL", host="h", user="u", password="p", database="d")
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post("/mysql/connections/DEL/delete", follow_redirects=False)
    assert r.status_code == 303
    assert isolated_config.get_connection("DEL") is None


def test_test_connection_endpoint_with_mock(isolated_config):
    """测试连接 endpoint，用 mock 模拟成功。"""
    isolated_config.upsert_connection(name="T", host="h", user="u", password="p", database="d")
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    with patch("sqlalchemy.create_engine") as fake:
        conn = MagicMock()
        fake.return_value.connect.return_value.__enter__.return_value = conn
        r = c.post("/mysql/connections/T/test")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True


def test_test_connection_endpoint_failure(isolated_config):
    """连接失败时返回 ok=False + error。"""
    isolated_config.upsert_connection(name="BAD", host="h", user="u", password="p", database="d")
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post("/mysql/connections/BAD/test")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert "error" in data