"""Embed fonts.css and the usage data into template.html -> Phaze Usage Dashboard.html.

Usage: python build.py            (uses data.json from fetch.py, else sample_data.json)
       python build.py --sample   (always uses sample_data.json)
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "Phaze Usage Dashboard.html"


def main():
    src = HERE / "data.json"
    if "--sample" in sys.argv or not src.exists():
        src = HERE / "sample_data.json"
        print("using synthetic sample data (run fetch.py for your own)")
    tpl = (HERE / "template.html").read_text(encoding="utf-8")
    fonts = (HERE / "fonts.css").read_text(encoding="utf-8") if (HERE / "fonts.css").exists() else ""
    data = json.loads(src.read_text(encoding="utf-8"))
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    html = tpl.replace("/*FONTS*/", fonts, 1).replace("__DATA__", payload, 1)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.name} from {src.name} ({OUT.stat().st_size // 1024} KB, {len(data['sessions'])} sessions)")


if __name__ == "__main__":
    main()
