import copy
import importlib.util
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

spec = importlib.util.spec_from_file_location("study_server", Path(__file__).resolve().parents[1] / "server.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = app.DB
        app.DB = Path(self.temp.name) / "study.sqlite3"
        app.init_db()
        self.config = dict(app.CONFIG)

    def tearDown(self):
        app.DB = self.db
        app.CONFIG.update(self.config)
        self.temp.cleanup()

    def real_session(self):
        s = app.new_session({"demo": True})
        s["demo"] = False
        app.save_session(s)
        return s

    def output(self, verdict="correct", advance=False):
        return {"feedback": "已检查你的解释。", "verdict": verdict, "question": "请举出一个新的适用情境。",
                "advance": advance, "evidence": "准确解释了用途和条件。"}

    def test_transcript_formats_and_source_ids(self):
        srt = "1\n00:00:01,100 --> 00:00:02,200\n第一句话\n\n2\n00:00:03,000 --> 00:00:04,000\n第二句话"
        result = app.parse_transcript(srt)
        self.assertEqual([s["id"] for s in result], ["S1", "S2"])
        self.assertEqual(result[0]["start"], "00:00:01.100")
        vtt = "WEBVTT\n\n00:01.000 --> 00:02.000\n字幕文本"
        self.assertEqual(app.parse_transcript(vtt)[0]["text"], "字幕文本")
        obj = '{"body":[{"from":5,"to":8,"content":"事实"}]}'
        self.assertEqual(app.parse_transcript(obj)[0]["start"], "00:00:05")
        self.assertIsNone(app.parse_transcript("纯文本\n第二段")[0]["start"])
        with self.assertRaises(app.AppError):
            app.parse_transcript("x" * (app.MAX_MATERIAL + 1))

    def test_reject_fabricated_citations(self):
        seg = app.parse_transcript(app.DEMO_TEXT)
        plan = app.demo_plan(seg)
        plan["points"][0]["refs"] = ["S999"]
        with self.assertRaisesRegex(app.AppError, "不存在"):
            app.validate_plan(plan, seg)

    def test_independent_explanation_then_application(self):
        s = self.real_session()
        with patch.object(app, "model_call", return_value=self.output()):
            app.apply_turn(s, "answer", "独立解释")
        self.assertEqual(s["records"]["K1"]["status"], "可独立解释")
        self.assertEqual(s["stage"], "apply")
        self.assertEqual(s["current"], 0)
        with patch.object(app, "model_call", return_value=self.output(advance=True)):
            app.apply_turn(s, "answer", "新场景应用")
        self.assertEqual(s["records"]["K1"]["status"], "可迁移应用")
        self.assertEqual(s["current"], 1)

    def test_hint_cannot_count_as_independent_mastery(self):
        s = self.real_session()
        with patch.object(app, "model_call", return_value=self.output("unassessed")):
            app.apply_turn(s, "hint")
        with patch.object(app, "model_call", return_value=self.output(advance=True)):
            app.apply_turn(s, "answer", "借助提示答对")
        self.assertEqual(s["records"]["K1"]["status"], "需要提示")
        self.assertEqual(s["stage"], "explain")
        self.assertEqual(s["current"], 0)
        self.assertFalse(s["assisted"])
        self.assertIn("独立解释", s["messages"][-1]["text"])

    def test_model_cannot_promote_on_hint(self):
        s = self.real_session()
        before = app.get_session(s["id"])
        with patch.object(app, "model_call", return_value=self.output(advance=True)):
            with self.assertRaises(app.AppError):
                app.apply_turn(s, "hint")
        self.assertEqual(app.get_session(s["id"]), before)

    def test_failed_call_does_not_save_answer(self):
        s = self.real_session()
        before = app.get_session(s["id"])
        with patch.object(app, "model_call", side_effect=app.AppError("网络中断")):
            with self.assertRaises(app.AppError):
                app.apply_turn(s, "answer", "我的回答")
        self.assertEqual(app.get_session(s["id"]), before)

    def test_demo_never_marks_mastered_and_can_resume(self):
        s = app.new_session({"demo": True})
        for i in range(8):
            app.apply_turn(s, "answer", "独立解释且迁移应用")
        self.assertTrue(s["ended"])
        self.assertTrue(all(r["status"] == "未验证" for r in s["records"].values()))
        app.resume_session(s)
        self.assertFalse(s["ended"])
        app.apply_turn(s, "skip")
        self.assertTrue(s["records"]["K1"]["skipped"])
        self.assertEqual(s["records"]["K1"]["status"], "未验证")
        notes = app.export_notes(s)
        self.assertIn("S1", notes)
        self.assertIn("下一次练习", notes)
        self.assertIn("固定演示", notes)

    def test_bilibili_import_selects_page_and_never_forwards_cookie(self):
        calls = []
        def fake_request(url, headers=None, payload=None):
            calls.append((url, dict(headers or {})))
            if "web-interface/view" in url:
                return {"code":0,"data":{"title":"示例","pages":[{"cid":1,"part":"第一段"},{"cid":2,"part":"第二段"}]}}
            if "player/v2" in url:
                return {"data":{"subtitle":{"subtitles":[{"lan":"zh-CN","subtitle_url":"//aisubtitle.hdslb.com/demo.json"}]}}}
            return {"body":[{"from":1,"to":2,"content":"实际字幕"}]}
        with patch.dict(app.os.environ, {"BILI_SESSDATA":"secret-cookie"}), patch.object(app,"request_json",side_effect=fake_request):
            result = app.import_bilibili("https://www.bilibili.com/video/BV1234567890/?p=2")
        self.assertIn("cid=2", calls[1][0])
        self.assertIn("Cookie", calls[0][1])
        self.assertNotIn("Cookie", calls[2][1])
        self.assertEqual(result["segments"][0]["text"], "实际字幕")
        with self.assertRaises(app.AppError):
            app.import_bilibili("https://evil.example/video/BV1234567890")

    def test_mock_model_http_and_secret_not_persisted(self):
        received = []
        plan = app.demo_plan(app.parse_transcript(app.DEMO_TEXT))
        class MockHandler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append((self.path,body,self.headers.get("Authorization")))
                content=json.dumps(plan,ensure_ascii=False)
                reply=json.dumps({"choices":[{"message":{"content":content}}]},ensure_ascii=False).encode()
                self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(reply)));self.end_headers();self.wfile.write(reply)
        server=ThreadingHTTPServer(("127.0.0.1",0),MockHandler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            app.set_config({"base_url":f"http://127.0.0.1:{server.server_port}/v1","model":"mock","api_key":"test-secret"})
            result=app.new_session({"transcript":app.DEMO_TEXT,"title":"模型集成"})
            self.assertFalse(result["demo"])
            self.assertEqual(received[0][0],"/v1/chat/completions")
            self.assertEqual(received[0][2],"Bearer test-secret")
            self.assertEqual(received[0][1]["messages"][0]["role"],"system")
            self.assertNotIn("test-secret",json.dumps(app.get_session(result["id"])))
            self.assertNotIn("api_key", app.public_config())
        finally:
            server.shutdown();server.server_close();worker.join()

    def test_changing_provider_clears_previous_key(self):
        app.set_config({"base_url":"https://first.example/v1","model":"first","api_key":"first-secret"})
        app.set_config({"base_url":"https://second.example/v1","model":"second"})
        self.assertFalse(app.public_config()["has_key"])

    def test_http_origin_version_and_persistence(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),app.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f"http://127.0.0.1:{server.server_port}"
        def post(path,data,origin=None):
            headers={"Content-Type":"application/json"}
            if origin:headers["Origin"]=origin
            return urlopen(Request(base+path,data=json.dumps(data).encode(),headers=headers))
        try:
            with post('/api/start',{"demo":True}) as response: s=json.load(response)
            with urlopen(base+'/api/session?id='+s['id']) as response:self.assertEqual(json.load(response)['title'],s['title'])
            with self.assertRaises(HTTPError) as error:post('/api/turn',{"id":s['id'],"version":0,"action":"skip"})
            self.assertEqual(error.exception.code,400)
            with self.assertRaises(HTTPError):post('/api/config',{},'https://evil.example')
            with urlopen(base+'/') as response:self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
        finally:
            server.shutdown();server.server_close();worker.join()


if __name__ == '__main__':
    unittest.main()
