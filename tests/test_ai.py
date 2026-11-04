import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error

from cataloglens.ai import Suggestion, classify_claude, validate_suggestion
from cataloglens.core import ValidationError
from cataloglens.evaluation import evaluate

ROOT=Path(__file__).resolve().parent.parent


class AITests(unittest.TestCase):
    def response(self, *, category="headphones", evidence="Headphones", stop="tool_use"):
        return {"model":"test-model","stop_reason":stop,"content":[{"type":"tool_use", "name":"suggest_category",
                "input":{"category":category,"evidence":evidence}}],"usage":{"input_tokens":80,"output_tokens":20}}

    def test_tool_contract_and_usage(self):
        seen=[]
        def opener(request,timeout):
            seen.append(json.loads(request.data))
            return io.BytesIO(json.dumps(self.response()).encode())
        result=classify_claude("Headphones","Audio",model="test-model",api_key="test-only",opener=opener)
        self.assertEqual((result.category,result.input_tokens,result.output_tokens),("headphones",80,20))
        self.assertEqual(seen[0]["tool_choice"],{"type":"auto"})
        self.assertEqual(seen[0]["tools"][0]["name"],"suggest_category")

    def test_missing_key_never_calls_network(self):
        with patch.dict("os.environ",{},clear=True), patch("urllib.request.urlopen") as network:
            with self.assertRaises(ValidationError): classify_claude("Item","")
            network.assert_not_called()

    def test_unsupported_category_invented_evidence_and_extra_fields_rejected(self):
        for payload in [{"category":"phones","evidence":"Headphones"},
                        {"category":"headphones","evidence":"noise cancellation"},
                        {"category":"headphones","evidence":""},
                        {"category":"headphones","evidence":"Headphones","price":1},
                        {"category":[],"evidence":"Headphones"}]:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                validate_suggestion(payload,"Headphones","Audio")

    def test_truncated_response_fails_closed(self):
        def opener(*args,**kwargs): return io.BytesIO(json.dumps(self.response(stop="max_tokens")).encode())
        with self.assertRaises(ValidationError):
            classify_claude("Headphones","",model="test",api_key="test",opener=opener)

    def test_http_error_has_no_response_or_key_leak_and_no_retry(self):
        calls=[]
        def opener(*args,**kwargs):
            calls.append(1)
            raise urllib.error.HTTPError("url",429,"rate limit",{},io.BytesIO(b"private body"))
        with self.assertRaisesRegex(ValidationError,"HTTP 429") as error:
            classify_claude("Headphones","",model="test",api_key="secret",opener=opener)
        self.assertEqual(len(calls),1)
        self.assertNotIn("secret",str(error.exception))

    def test_baseline_exposes_accessory_and_instruction_failures(self):
        result=evaluate(ROOT/"data/evaluation.json")
        self.assertEqual((result["cases"],result["correct"]),(24,18))
        failures={x["id"] for x in result["outcomes"] if not x["correct"]}
        self.assertTrue({"e17","e18","e19","e20","e24"}.issubset(failures))
        self.assertEqual(result["input_tokens"],0)

    def test_evaluation_provider_is_injectable_without_live_usage(self):
        def stub(title,description):
            return Suggestion("other","","stub",10,5,2)
        result=evaluate(ROOT/"data/evaluation.json",provider="claude",classifier=stub)
        self.assertEqual(result["models"],["stub"])
        self.assertEqual(result["input_tokens"],240)
        self.assertEqual(result["elapsed_ms"],48)


if __name__ == "__main__": unittest.main()
