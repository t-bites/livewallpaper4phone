import unittest, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from enrich_prompts import parse_llm_json


class TestParseLlmJson(unittest.TestCase):
    def test_plain(self):
        d = parse_llm_json('{"prompt": "A cat", "source": "tweet"}')
        self.assertEqual(d, {"prompt": "A cat", "source": "tweet"})

    def test_fenced(self):
        d = parse_llm_json('```json\n{"prompt": "A cat", "source": "tweet"}\n```')
        self.assertEqual(d["prompt"], "A cat")

    def test_surrounding_text(self):
        d = parse_llm_json('结果如下：{"prompt": " A cat ", "source": "tweet"} 完毕')
        self.assertEqual(d["prompt"], "A cat")

    def test_null_prompt(self):
        d = parse_llm_json('{"prompt": null, "source": null}')
        self.assertEqual(d, {"prompt": None, "source": None})

    def test_garbage(self):
        self.assertEqual(parse_llm_json("没有json"), {"prompt": None, "source": None})

    def test_bad_source_normalized(self):
        d = parse_llm_json('{"prompt": "cat", "source": "comment"}')
        self.assertEqual(d["source"], "unknown")

    def test_empty_prompt_normalized(self):
        d = parse_llm_json('{"prompt": "  ", "source": "tweet"}')
        self.assertEqual(d, {"prompt": None, "source": None})


if __name__ == "__main__":
    unittest.main()
