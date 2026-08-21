import unittest
from wallpaper_core import (select_video, dedupe_by_id, status_id_from_url,
                            parse_issue_status_ids, extract_reply_ids)

E1 = {"id": "111", "width": 720}
E2 = {"id": "222", "width": 1080}
E3 = {"id": "333"}

class TestSelectVideo(unittest.TestCase):
    def test_empty(self):
        self.assertIsNone(select_video([], "first"))

    def test_explicit_id_wins_over_index_semantics(self):
        # media ID 是长数字串，必须先按 ID 精确匹配而不是当序号
        self.assertEqual(select_video([E1, E2], "222"), E2)

    def test_first_last(self):
        self.assertEqual(select_video([E1, E2], "first"), E1)
        self.assertEqual(select_video([E1, E2], "last"), E2)

    def test_none_defaults_to_last(self):
        self.assertEqual(select_video([E1, E2], None), E2)

    def test_index_1_based(self):
        self.assertEqual(select_video([E1, E2], 1), E1)
        self.assertEqual(select_video([E1, E2], "2"), E2)

    def test_index_out_of_range(self):
        self.assertIsNone(select_video([E1], 5))

    def test_unknown_keep(self):
        self.assertIsNone(select_video([E1], "bogus"))


class TestDedupe(unittest.TestCase):
    def test_keeps_first_occurrence(self):
        items = [E1, E2, {"id": "111", "dup": True}, E3]
        out = dedupe_by_id(items)
        self.assertEqual([i["id"] for i in out], ["111", "222", "333"])
        self.assertNotIn("dup", out[0])

    def test_skips_missing_id(self):
        self.assertEqual(dedupe_by_id([{"x": 1}, E1]), [E1])


class TestStatusUrl(unittest.TestCase):
    def test_x_com(self):
        self.assertEqual(status_id_from_url("https://x.com/i/status/123"), "123")
        self.assertEqual(status_id_from_url("https://x.com/foo/status/456?s=20"), "456")

    def test_twitter_com(self):
        self.assertEqual(status_id_from_url("http://www.twitter.com/ab/status/789"), "789")

    def test_invalid(self):
        self.assertIsNone(status_id_from_url("https://example.com/status/1"))
        self.assertIsNone(status_id_from_url(""))


class TestIssueParse(unittest.TestCase):
    def test_extracts_reported_only(self):
        issues = [
            {"number": 1, "title": "[壁纸上报] status_42", "body": "链接: https://x.com/a/status/42\n备注: 好"},
            {"number": 2, "title": "随便聊聊", "body": "https://x.com/a/status/99"},
            {"number": 3, "title": "[壁纸上报] bad", "body": "没有链接"},
        ]
        self.assertEqual(parse_issue_status_ids(issues), [(1, "42")])

    def test_empty(self):
        self.assertEqual(parse_issue_status_ids([]), [])
        self.assertEqual(parse_issue_status_ids(None), [])


class TestReplyIds(unittest.TestCase):
    MD = """
    # 夏一跳 on X: "主帖文本"
    [夏一跳](https://x.com/xiayitiaoAI) 文本 [7:51 AM](https://x.com/xiayitiaoAI/status/100)
    [Aug 19](https://x.com/xiayitiaoAI/status/200) Seedance 提示词...
    [someone](https://x.com/other/status/300) 别人的回复
    [Aug 19](https://x.com/xiayitiaoAI/status/200) 重复链接
    """

    def test_extracts_author_replies_excluding_main_and_dups(self):
        self.assertEqual(extract_reply_ids(self.MD, "xiayitiaoAI", exclude_id="100"), ["200"])

    def test_no_exclude(self):
        self.assertEqual(extract_reply_ids(self.MD, "xiayitiaoAI"), ["100", "200"])

    def test_other_author_ignored(self):
        self.assertEqual(extract_reply_ids(self.MD, "other", exclude_id="100"), ["300"])


if __name__ == "__main__":
    unittest.main()
