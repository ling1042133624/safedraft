"""强制推送（覆盖远程）测试。SFTP 用 mock 替代。"""
from unittest.mock import patch, MagicMock


class TestForcePushOverwrite:
    def test_calls_rename_when_remote_exists(self, tmp_db):
        """远程存在 DB 时，先备份再上传。"""
        tmp_db.save_content_forced("local data")

        with patch.object(tmp_db, '_get_ssh_client') as mock_ssh_ctor:
            ssh = MagicMock()
            sftp = MagicMock()
            ssh.open_sftp.return_value = sftp
            mock_ssh_ctor.return_value = ssh

            sftp.stat.return_value = MagicMock()
            sftp.listdir.return_value = []

            tmp_db.force_push_overwrite("user@host", "/remote/path")

            assert sftp.rename.called, "应该调用 sftp.rename 备份远程 DB"
            assert sftp.put.called, "应该调用 sftp.put 上传 DB"
            ssh.open_sftp.assert_called_once()

    def test_skips_rename_when_remote_missing(self, tmp_db):
        """远程不存在 DB 时，跳过备份，直接上传。"""
        tmp_db.save_content_forced("local data")

        with patch.object(tmp_db, '_get_ssh_client') as mock_ssh_ctor:
            ssh = MagicMock()
            sftp = MagicMock()
            ssh.open_sftp.return_value = sftp
            mock_ssh_ctor.return_value = ssh

            sftp.stat.side_effect = FileNotFoundError("not found")
            sftp.listdir.return_value = []

            tmp_db.force_push_overwrite("user@host", "/remote/path")

            assert not sftp.rename.called, "远程不存在时不应调用 rename"
            assert sftp.put.called

    def test_raises_on_empty_config(self, tmp_db):
        """server_ip 或 remote_path 为空时抛 ValueError。"""
        try:
            tmp_db.force_push_overwrite("", "/remote/path")
            assert False, "应抛 ValueError"
        except ValueError:
            pass

        try:
            tmp_db.force_push_overwrite("user@host", "")
            assert False, "应抛 ValueError"
        except ValueError:
            pass

    def test_removes_old_md5_files(self, tmp_db):
        """远程有旧 md5 文件时，应被删除。"""
        tmp_db.save_content_forced("local data")

        with patch.object(tmp_db, '_get_ssh_client') as mock_ssh_ctor:
            ssh = MagicMock()
            sftp = MagicMock()
            ssh.open_sftp.return_value = sftp
            mock_ssh_ctor.return_value = ssh

            sftp.stat.side_effect = FileNotFoundError("not found")
            sftp.listdir.return_value = [
                "safedraft_oldhash1.md5",
                "safedraft_oldhash2.md5",
                "other_file.txt",
            ]

            tmp_db.force_push_overwrite("user@host", "/remote/path")

            removed_paths = [call.args[0] for call in sftp.remove.call_args_list]
            assert any("safedraft_oldhash1.md5" in p for p in removed_paths)
            assert any("safedraft_oldhash2.md5" in p for p in removed_paths)
            assert not any("other_file.txt" in p for p in removed_paths), "不应删除无关文件"
