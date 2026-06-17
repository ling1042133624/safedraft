"""超集去重算法测试。"""


class TestDeduplicateSuperset:
    def test_basic_subset(self, tmp_db):
        """A 是 B 的子串，删除 A。"""
        tmp_db.save_content_forced("AAAABBC")
        tmp_db.save_content_forced("AAAABBCGWERER")

        deleted = tmp_db.deduplicate_drafts_superset()

        assert deleted == 1
        contents = [r[1] for r in tmp_db.get_history()]
        assert "AAAABBCGWERER" in contents
        assert "AAAABBC" not in contents

    def test_chain(self, tmp_db):
        """A⊂B⊂C，只保留 C。"""
        tmp_db.save_content_forced("abc")
        tmp_db.save_content_forced("abcd")
        tmp_db.save_content_forced("abcde")

        deleted = tmp_db.deduplicate_drafts_superset()

        assert deleted == 2
        contents = [r[1] for r in tmp_db.get_history()]
        assert contents == ["abcde"]

    def test_multi_maximal(self, tmp_db):
        """A⊂B、A⊂C，B 与 C 不互含；保留 B、C，删除 A。"""
        tmp_db.save_content_forced("abc")
        tmp_db.save_content_forced("abcd")
        tmp_db.save_content_forced("abcef")

        deleted = tmp_db.deduplicate_drafts_superset()

        assert deleted == 1
        contents = sorted(r[1] for r in tmp_db.get_history())
        assert contents == ["abcd", "abcef"]

    def test_case_sensitive(self, tmp_db):
        """严格区分大小写：'abc' 和 'ABC' 互不为子串，都保留。"""
        tmp_db.save_content_forced("abc")
        tmp_db.save_content_forced("ABC")

        deleted = tmp_db.deduplicate_drafts_superset()

        assert deleted == 0
        contents = sorted(r[1] for r in tmp_db.get_history())
        assert contents == ["ABC", "abc"]

    def test_blank_records_removed(self, tmp_db):
        """空白记录直接删除。"""
        tmp_db.save_content_forced("hello")
        tmp_db.cursor.execute(
            "INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)",
            ("   ", "2026-06-18T10:00:00", "2026-06-18T10:00:00"),
        )
        tmp_db.cursor.execute(
            "INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)",
            ("", "2026-06-18T10:00:00", "2026-06-18T10:00:00"),
        )
        tmp_db.conn.commit()

        deleted = tmp_db.deduplicate_drafts_superset()

        assert deleted == 2
        contents = [r[1] for r in tmp_db.get_history()]
        assert contents == ["hello"]

    def test_no_duplicates(self, tmp_db):
        """没有子集关系，全部保留。"""
        tmp_db.save_content_forced("hello")
        tmp_db.save_content_forced("world")

        deleted = tmp_db.deduplicate_drafts_superset()

        assert deleted == 0
        contents = sorted(r[1] for r in tmp_db.get_history())
        assert contents == ["hello", "world"]

    def test_empty_db(self, tmp_db):
        """空数据库返回 0。"""
        deleted = tmp_db.deduplicate_drafts_superset()
        assert deleted == 0
