"""Render test results to JUnit XML (for CI) and a standalone HTML report."""

from __future__ import annotations

import html
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:  # avoid a runtime import cycle
    from ..testing.test_case import TestResult


def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)


def write_junit_xml(results: List["TestResult"], path: str,
                    suite_name: str = "bms_hil") -> str:
    total = len(results)
    failures = sum(1 for r in results if r.status == "fail")
    errors = sum(1 for r in results if r.status == "error")
    skipped = sum(1 for r in results if r.status == "skip")
    duration = sum(r.duration_s for r in results)

    suite = ET.Element("testsuite", {
        "name": suite_name,
        "tests": str(total),
        "failures": str(failures),
        "errors": str(errors),
        "skipped": str(skipped),
        "time": f"{duration:.3f}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    for r in results:
        case = ET.SubElement(suite, "testcase", {
            "name": r.name,
            "classname": r.category or suite_name,
            "time": f"{r.duration_s:.3f}",
        })
        if r.status == "fail":
            fail = ET.SubElement(case, "failure", {"message": r.message})
            fail.text = "\n".join(r.log)
        elif r.status == "error":
            err = ET.SubElement(case, "error", {"message": r.message})
            err.text = "\n".join(r.log)
        elif r.status == "skip":
            ET.SubElement(case, "skipped", {"message": r.message})
        if r.log:
            ET.SubElement(case, "system-out").text = "\n".join(r.log)

    _ensure_dir(path)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)
    return path


_HTML_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>BMS HIL Test Report</title>
<style>
 body{{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:2rem;color:#1a1a1a;background:#fafafa}}
 h1{{margin-bottom:.2rem}} .sub{{color:#666;margin-top:0}}
 .summary{{display:flex;gap:1rem;margin:1.5rem 0}}
 .card{{border-radius:8px;padding:1rem 1.4rem;color:#fff;min-width:90px}}
 .pass{{background:#2e7d32}} .fail{{background:#c62828}}
 .error{{background:#ef6c00}} .skip{{background:#616161}} .total{{background:#37474f}}
 .card b{{font-size:1.6rem;display:block}}
 table{{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
 th,td{{text-align:left;padding:.55rem .8rem;border-bottom:1px solid #eee;vertical-align:top}}
 th{{background:#eceff1}}
 .st{{font-weight:700;text-transform:uppercase;font-size:.75rem;padding:.15rem .5rem;border-radius:4px;color:#fff}}
 .st.pass{{background:#2e7d32}} .st.fail{{background:#c62828}}
 .st.error{{background:#ef6c00}} .st.skip{{background:#616161}}
 pre{{white-space:pre-wrap;margin:.3rem 0 0;color:#444;font-size:.82rem}}
</style></head><body>
<h1>BMS HIL Test Report</h1>
<p class="sub">Generated {ts} &middot; total duration {dur:.2f}s</p>
<div class="summary">
 <div class="card total"><b>{total}</b>tests</div>
 <div class="card pass"><b>{passed}</b>passed</div>
 <div class="card fail"><b>{failed}</b>failed</div>
 <div class="card error"><b>{errors}</b>errors</div>
 <div class="card skip"><b>{skipped}</b>skipped</div>
</div>
<table><thead><tr><th>Test</th><th>Category</th><th>Status</th><th>Time</th><th>Detail</th></tr></thead>
<tbody>
{rows}
</tbody></table>
</body></html>
"""


def write_html_report(results: List["TestResult"], path: str) -> str:
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    errors = sum(1 for r in results if r.status == "error")
    skipped = sum(1 for r in results if r.status == "skip")
    duration = sum(r.duration_s for r in results)

    rows = []
    for r in results:
        detail = html.escape(r.message)
        if r.log:
            detail += "<pre>" + html.escape("\n".join(r.log[-12:])) + "</pre>"
        rows.append(
            f'<tr><td>{html.escape(r.name)}</td>'
            f'<td>{html.escape(r.category or "")}</td>'
            f'<td><span class="st {r.status}">{r.status}</span></td>'
            f'<td>{r.duration_s:.2f}s</td>'
            f'<td>{detail}</td></tr>'
        )

    doc = _HTML_TEMPLATE.format(
        ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        dur=duration, total=len(results), passed=passed, failed=failed,
        errors=errors, skipped=skipped, rows="\n".join(rows),
    )
    _ensure_dir(path)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path
