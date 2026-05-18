"""
test_command_parser.py

command_parser 单元测试 — 覆盖多行多任务格式
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from command_parser import parse_command


class TestSharePixelToAccountMultiTask:
    def test_user_format_case1(self):
        text = """分享像素到账户
1.将像素：NYC01
分享到账户：21324536476857、756643232344
2.将像素：NYC02
分享到账户：9876544343432、43256787987867"""
        r = parse_command(text)
        assert r["action"] == "share_pixel_to_account"
        assert r["error"] is None
        assert len(r["tasks"]) == 2

        t1 = r["tasks"][0]
        assert t1["pixel_names"] == ["NYC01"]
        assert t1["target_account_ids"] == ["21324536476857", "756643232344"]

        t2 = r["tasks"][1]
        assert t2["pixel_names"] == ["NYC02"]
        assert t2["target_account_ids"] == ["9876544343432", "43256787987867"]

    def test_single_line(self):
        r = parse_command("分享像素到账户 将像素：NYC01 分享到账户：21324536476857")
        assert r["action"] == "share_pixel_to_account"
        assert r["error"] is None
        assert len(r["tasks"]) == 1
        assert r["tasks"][0]["pixel_names"] == ["NYC01"]
        assert r["tasks"][0]["target_account_ids"] == ["21324536476857"]

    def test_multi_pixels_single_task(self):
        r = parse_command("分享像素到账户 将像素：NYC01、NYC02 分享到账户：21324536476857")
        assert r["action"] == "share_pixel_to_account"
        assert r["tasks"][0]["pixel_names"] == ["NYC01", "NYC02"]
        assert r["tasks"][0]["target_account_ids"] == ["21324536476857"]

    def test_pixel_id_instead_of_name(self):
        r = parse_command("分享像素到账户 像素：1351490590154541 分享到账户：21324536476857")
        assert r["action"] == "share_pixel_to_account"
        assert r["tasks"][0]["pixel_ids"] == ["1351490590154541"]
        assert r["tasks"][0]["target_account_ids"] == ["21324536476857"]

    def test_missing_pixel(self):
        r = parse_command("分享像素到账户\n分享到账户：21324536476857")
        assert r["error"] is not None

    def test_missing_target(self):
        r = parse_command("分享像素到账户\n将像素：NYC01")
        assert r["error"] is not None


class TestSharePixelToBmMultiTask:
    def test_user_format_case1(self):
        text = """分享像素到BM
1.将像素：NYC02、NYC03
分享到BM：32321312322323
2.将像素：NYC04、NYC05
分享到BM：32321312322323"""
        r = parse_command(text)
        assert r["action"] == "share_pixel_to_bm"
        assert r["error"] is None
        assert len(r["tasks"]) == 2

        t1 = r["tasks"][0]
        assert t1["pixel_names"] == ["NYC02", "NYC03"]
        assert t1["target_bm_ids"] == ["32321312322323"]

        t2 = r["tasks"][1]
        assert t2["pixel_names"] == ["NYC04", "NYC05"]
        assert t2["target_bm_ids"] == ["32321312322323"]

    def test_single_line(self):
        r = parse_command("分享像素到BM 将像素：NYC02 分享到BM：32321312322323")
        assert r["action"] == "share_pixel_to_bm"
        assert r["tasks"][0]["pixel_names"] == ["NYC02"]
        assert r["tasks"][0]["target_bm_ids"] == ["32321312322323"]

    def test_original_format(self):
        r = parse_command("把BM 1632044938058987的像素 975850325406476分享给BM 2001982753911515")
        assert r["action"] == "share_pixel_to_bm"
        assert r["tasks"][0]["target_bm_ids"] == ["2001982753911515"]


class TestShareBmMultiTask:
    def test_user_format_case1(self):
        text = """分享BM
1.将BM：23432434324324243
分享到个号：DFgfsfsd@gmail.com
2.将BM：65676576576
分享到个号：dsd@gmail.com"""
        r = parse_command(text)
        assert r["action"] == "share_bm"
        assert r["error"] is None
        assert len(r["tasks"]) == 2

        t1 = r["tasks"][0]
        assert t1["bm_ids"] == ["23432434324324243"]
        assert t1["emails"] == ["DFgfsfsd@gmail.com"]

        t2 = r["tasks"][1]
        assert t2["bm_ids"] == ["65676576576"]
        assert t2["emails"] == ["dsd@gmail.com"]

    def test_single_line_share_bm(self):
        r = parse_command("分享BM 将BM：123456789 分享到个号：test@gmail.com")
        assert r["action"] == "share_bm"
        assert r["tasks"][0]["bm_ids"] == ["123456789"]
        assert r["tasks"][0]["emails"] == ["test@gmail.com"]


class TestEdgeCases:
    def test_empty_command(self):
        r = parse_command("")
        assert r["action"] == "unknown"

    def test_none_command(self):
        r = parse_command(None)
        assert r["action"] == "unknown"

    def test_unrecognized_command(self):
        r = parse_command("今天天气怎么样")
        assert r["action"] == "unknown"
        assert r["error"] is not None

    def test_colon_variations(self):
        r = parse_command("分享像素到账户 将像素:NYC01 分享到账户:21324536476857")
        assert r["action"] == "share_pixel_to_account"
        assert r["tasks"][0]["pixel_names"] == ["NYC01"]
        assert r["tasks"][0]["target_account_ids"] == ["21324536476857"]

    def test_pixel_name_with_underscore(self):
        r = parse_command("分享像素到账户 将像素：lucax_test 分享到账户：225617473696264")
        assert r["action"] == "share_pixel_to_account"
        assert r["tasks"][0]["pixel_names"] == ["lucax_test"]

    def test_case_insensitive_bm(self):
        r = parse_command("分享像素到bm 将像素：NYC01 分享到bm：123456789012")
        assert r["action"] == "share_pixel_to_bm"
        assert r["tasks"][0]["target_bm_ids"] == ["123456789012"]

    def test_ad_account_keyword(self):
        r = parse_command("分享像素到广告账户 将像素：NYC01 分享到广告账户：21324536476857")
        assert r["action"] == "share_pixel_to_account"

    def test_share_to_account_with_space_format(self):
        r = parse_command("将像素 NYC01 分享到广告账户 21324536476857")
        assert r["action"] == "share_pixel_to_account"
        assert r["tasks"][0]["pixel_names"] == ["NYC01"]
        assert r["tasks"][0]["target_account_ids"] == ["21324536476857"]


class TestNewTemplateWithSourceBm:
    def test_share_pixel_to_bm_with_source_bm(self):
        text = """分享像素到BM
1.将BM 1632044938058987
像素：NHW0518
分享到BM：2001982753911515"""
        r = parse_command(text)
        assert r["action"] == "share_pixel_to_bm"
        assert r["error"] is None
        assert len(r["tasks"]) == 1
        t = r["tasks"][0]
        assert t["source_bm_id"] == "1632044938058987"
        assert t["pixel_names"] == ["NHW0518"]
        assert t["target_bm_ids"] == ["2001982753911515"]

    def test_share_pixel_to_account_with_source_bm(self):
        text = """分享像素到账户
1.将BM 2001982753911515
像素：NHW0518
分享到账户：221893224124169、1636424280844118"""
        r = parse_command(text)
        assert r["action"] == "share_pixel_to_account"
        assert r["error"] is None
        assert len(r["tasks"]) == 1
        t = r["tasks"][0]
        assert t["source_bm_id"] == "2001982753911515"
        assert t["pixel_names"] == ["NHW0518"]
        assert t["target_account_ids"] == ["221893224124169", "1636424280844118"]

    def test_multi_task_source_bm_inherit(self):
        text = """分享像素到BM
1.将BM 1632044938058987
像素：NHW0518
分享到BM：2001982753911515
2.像素：NYC01
分享到BM：32321312322323"""
        r = parse_command(text)
        assert r["action"] == "share_pixel_to_bm"
        assert r["error"] is None
        assert len(r["tasks"]) == 2
        t1 = r["tasks"][0]
        assert t1["source_bm_id"] == "1632044938058987"
        assert t1["pixel_names"] == ["NHW0518"]
        t2 = r["tasks"][1]
        assert t2["source_bm_id"] == "1632044938058987"
        assert t2["pixel_names"] == ["NYC01"]

    def test_multi_task_source_bm_override(self):
        text = """分享像素到账户
1.将BM 111111111
像素：NYC01
分享到账户：222222222
2.将BM 333333333
像素：NYC02
分享到账户：444444444"""
        r = parse_command(text)
        assert r["action"] == "share_pixel_to_account"
        assert r["error"] is None
        assert len(r["tasks"]) == 2
        assert r["tasks"][0]["source_bm_id"] == "111111111"
        assert r["tasks"][1]["source_bm_id"] == "333333333"

    def test_source_bm_with_colon(self):
        text = """分享像素到BM
1.将BM：1632044938058987
像素：NHW0518
分享到BM：2001982753911515"""
        r = parse_command(text)
        assert r["action"] == "share_pixel_to_bm"
        assert r["error"] is None
        assert r["tasks"][0]["source_bm_id"] == "1632044938058987"

    def test_old_template_without_source_bm_still_works(self):
        text = """分享像素到BM
1.将像素：NHW0518
分享到BM：2001982753911515"""
        r = parse_command(text)
        assert r["action"] == "share_pixel_to_bm"
        assert r["error"] is None
        assert r["tasks"][0]["source_bm_id"] == ""
        assert r["tasks"][0]["pixel_names"] == ["NHW0518"]
        assert r["tasks"][0]["target_bm_ids"] == ["2001982753911515"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
