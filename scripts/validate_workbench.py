#!/usr/bin/env python3
"""Optional real-browser validation; requires Playwright and a Chromium binary.

Uses temporary synthetic materials and isolated registry state. The core Skill
and unit suite do not require these browser testing dependencies.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import functools
import http.server
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_reliability_v160 import FlowFixture
from coach import attempts as at


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",required=True)
    parser.add_argument("--transport",choices=["static-http","set-content"],default="static-http",help="set-content renders supplied HTML when container navigation is policy-blocked; native persistence is then not tested")
    parser.add_argument("--chromium",default=shutil.which("chromium") or shutil.which("google-chrome"))
    args=parser.parse_args()
    out=Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):parser.error("use a new empty directory")
    out.mkdir(parents=True,exist_ok=True)
    from playwright.sync_api import sync_playwright
    fixture=FlowFixture();fixture.setUp()
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args): pass
    server=http.server.ThreadingHTTPServer(("127.0.0.1",0),functools.partial(QuietHandler,directory=str(out)))
    serving=threading.Thread(target=server.serve_forever,daemon=True);serving.start()
    base_url="http://127.0.0.1:%s/"%server.server_address[1]
    results={"render_transport":args.transport,"not_tested":[],"synthetic_only":True,"live_platform":False,"checks":[],"console_errors":[],"network_requests":[]}
    def render(page,filename):
        context=page.context
        page.close()
        page=context.new_page()
        page.on("pageerror",lambda e:results["console_errors"].append(str(e)))
        page.on("request",lambda req:results["network_requests"].append(req.url) if (req.url.startswith(("http://","https://")) and not req.url.startswith(base_url)) else None)
        if args.transport=="set-content":
            page.set_content((out/filename).read_text(encoding="utf-8"),wait_until="load")
        else:
            page.goto(base_url+filename,wait_until="load")
        return page
    def check(name,value):
        results["checks"].append({"name":name,"passed":bool(value)})
        if not value:raise AssertionError(name)
    try:
        fixture.planned();q=fixture.q()
        fixture.run_cmd("quiz","--qid",q["id"])
        fixture.run_cmd("workbench","--out",out/"question.html")
        a=at.active(fixture.state())
        with sync_playwright() as pw:
            opts={"headless":True,"args":["--no-sandbox"]}
            if args.chromium:opts["executable_path"]=args.chromium
            browser=pw.chromium.launch(**opts)
            results["browser_version"]=browser.version
            context=browser.new_context(viewport={"width":1365,"height":950},accept_downloads=True)
            page=context.new_page()
            page.on("pageerror",lambda e:results["console_errors"].append(str(e)))
            page.on("request",lambda req:results["network_requests"].append(req.url) if (req.url.startswith(("http://","https://")) and not req.url.startswith(base_url)) else None)
            page=render(page,"question.html")
            check("no_reference_key_before_submit",page.evaluate("JSON.parse(document.querySelector('#data').textContent).feedback===null"))
            check("desktop_no_horizontal_document_overflow",page.evaluate("document.documentElement.scrollWidth<=innerWidth+1"))
            check("raw_answer_has_accessible_label",page.get_by_label("写下你的原答与关键步骤").count()==1)
            page.screenshot(path=str(out/"desktop-question.png"),full_page=True)
            page.locator(".option").nth(1).click()
            check("option_selects_response",page.locator("#response").input_value()=="B")
            with page.expect_download() as dl:page.locator("#submit").click()
            receipt=out/"synthetic-answer.json";dl.value.save_as(receipt)
            frozen=json.loads(receipt.read_text(encoding="utf-8"))
            check("receipt_binds_exact_attempt",frozen["attempt_id"]==a["id"] and frozen["qid"]==q["id"])
            check("submit_freezes_controls",page.locator("#response").is_disabled() and page.locator("#submit").is_disabled())
            if args.transport=="static-http":
                page.reload(wait_until="load")
                check("reload_restores_frozen_answer",page.locator("#response").is_disabled() and page.locator("#response").input_value()=="B")
            else:
                results["not_tested"].append("Native file/HTTP navigation and localStorage persistence across page reload (container browser policy blocks URL navigation).")
                check("storage_unavailable_is_explicit", "不允许持久保存" in page.locator("#receipt").inner_text())
            with page.expect_download() as dl:page.locator("#again").click()
            again=out/"synthetic-answer-repeat.json";dl.value.save_as(again)
            check("repeat_export_is_identical",json.loads(again.read_text(encoding="utf-8"))==frozen)
            fixture.run_cmd("import-answer",receipt);fixture.run_cmd("import-answer",receipt)
            fixture.run_cmd("grade",q["id"])
            h=fixture.state()["history"]
            check("backend_import_and_grade_exactly_once",len(h)==1 and h[0]["response"]=="B" and h[0]["attempt_id"]==a["id"])
            fixture.run_cmd("workbench","--out",out/"feedback.html")
            page=render(page,"feedback.html")
            check("feedback_after_backend_grade",page.locator("#feedback").is_visible() and "正确" in page.locator("#feedback").inner_text())
            check("feedback_hides_answer_entry_and_options",page.locator("#answerArea").is_hidden() and page.locator("#options").is_hidden())
            page.screenshot(path=str(out/"desktop-feedback.png"),full_page=True)
            mobile=browser.new_context(viewport={"width":390,"height":844},is_mobile=True,device_scale_factor=1)
            mp=mobile.new_page()
            mp.on("pageerror",lambda e:results["console_errors"].append(str(e)))
            mp.on("request",lambda req:results["network_requests"].append(req.url) if (req.url.startswith(("http://","https://")) and not req.url.startswith(base_url)) else None)
            mp=render(mp,"question.html")
            check("mobile_no_horizontal_document_overflow",mp.evaluate("document.documentElement.scrollWidth<=innerWidth+1"))
            check("mobile_question_is_prioritized",mp.locator("#stem").bounding_box()["y"]<400)
            check("mobile_buttons_have_no_overflow",mp.locator("#submit").bounding_box()["width"]<=390)
            mp.screenshot(path=str(out/"mobile-question.png"),full_page=True)
            mp=render(mp,"feedback.html")
            mp.screenshot(path=str(out/"mobile-feedback.png"),full_page=True)
            check("no_javascript_errors",not results["console_errors"])
            check("no_remote_requests",not results["network_requests"])
            mobile.close();context.close();browser.close()
        results["passed"]=True
        print(json.dumps(results,ensure_ascii=False,indent=2))
    finally:
        server.shutdown();server.server_close()
        fixture.doCleanups()
        (out/"browser-results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")


if __name__=="__main__":main()
