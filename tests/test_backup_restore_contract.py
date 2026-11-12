"""PILOT-BACKUP-RESTORE-01 脚本安全合同的快速离线检查。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "deploy" / "backup" / "pg_backup.ps1"
RESTORE = ROOT / "deploy" / "backup" / "pg_restore.ps1"
SEED = ROOT / "deploy" / "backup" / "seed_backup_restore_fixture.py"
VERIFY = ROOT / "deploy" / "backup" / "verify_backup_restore_fixture.py"


def test_backup_contract_uses_custom_dump_hash_manifest_and_repo_external_output():
    content = BACKUP.read_text(encoding="utf-8")
    assert "--format=custom" in content
    assert "Get-FileHash" in content
    assert "opsai.postgresql-backup-manifest/v1" in content
    assert "Refusing to write a backup inside the repository" in content
    assert "pg_dump --version" in content


def test_restore_contract_refuses_hash_mismatch_and_existing_target_database():
    content = RESTORE.read_text(encoding="utf-8")
    assert "backup SHA-256 does not match the manifest" in content
    assert "target database $TargetDatabase already exists" in content
    assert "createdb" in content
    assert "pg_restore --exit-on-error --no-owner --no-privileges" in content
    assert "dropdb" not in content


def test_fixture_scripts_are_isolated_and_cover_required_business_records():
    seed = SEED.read_text(encoding="utf-8")
    verify = VERIFY.read_text(encoding="utf-8")
    for required in (
        "User",
        "Article",
        "ArticleVersion",
        "ReviewRecord",
        "ArticleAudience",
        "FeedbackRecord",
    ):
        assert required in seed
        assert required in verify
    for content in (seed, verify):
        assert "OPSAI_BACKUP_RESTORE_DRILL" in content
        assert "opsai_backup_restore_" in content
