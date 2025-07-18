from datetime import datetime, timezone
from jinja2 import Environment, FileSystemLoader
import json

latex_format_map = {
	"YYYY": "%Y",
	"MMMM yyyy": "%B %Y",
	"MMMM YYYY": "%B %Y",
	"MM-yyyy": "%m-%Y",
	"MMM yyyy": "%b %Y",
	"MMMM": "%B",
	"yyyy-MM-dd": "%Y-%m-%d"
}

def as_date(date_string: str, fmt: str = "%Y-%m-%d") -> str:
	try:
		return datetime.strptime(date_string, "%Y-%m-%d").strftime(fmt)
	except Exception:
		return date_string

with open("cv.json", "r", encoding="utf-8") as f:
	data = json.load(f)

env = Environment(
	loader=FileSystemLoader("."),
	autoescape=False
)

env.filters["as_date"] = as_date

template = env.get_template("cv.j2")
template.globals['now'] = datetime.now(timezone.utc)
rendered = template.render(**data)

with open("cv.tex", "w", encoding="utf-8") as f:
	f.write(rendered)

print("cv.tex has been generated successfully.")
