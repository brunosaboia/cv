import argparse
import humanize
import json
import re
from datetime import datetime, timezone
from jinja2 import Environment, FileSystemLoader

latex_format_map = {
	"YYYY": "%Y",
	"MMMM yyyy": "%B %Y",
	"MMMM YYYY": "%B %Y",
	"MM-yyyy": "%m-%Y",
	"MMM yyyy": "%b %Y",
	"MMMM": "%B",
	"yyyy-MM-dd": "%Y-%m-%d"
}

def parse_duration(date_string_start: str, date_string_end: str, fmt_key = "yyyy-MM-dd") -> str:
	fmt = latex_format_map.get(fmt_key, fmt_key)
	try:
		start_date = datetime.strptime(date_string_start, fmt).date()
		end_date = datetime.strptime(date_string_end, fmt).date()

		duration = end_date - start_date

		humanized_delta = humanize.naturaldelta(value=duration)

		return humanized_delta.replace("a ", "1 ").replace("an ", "1 ")

	except Exception:
		return "unknown duration"


def as_date(date_string: str, fmt_key: str = "yyyy-MM-dd") -> str:
	fmt = latex_format_map.get(fmt_key, fmt_key)
	try:
		return datetime.strptime(date_string, "%Y-%m-%d").strftime(fmt)
	except Exception:
		return date_string

def latex_escape(text: str) -> str:
	if not isinstance(text, str):
		return text
	replacements = {
		'\\': r'\\',
		'{': r'\{',
		'}': r'\}',
		'#': r'\#',
		'$': r'\$',
		'%': r'\%',
		'&': r'\&',
		'_': r'\_',
		'^': r'\textasciicircum{}',
		'~': r'\textasciitilde{}',
	}
	pattern = re.compile('|'.join(re.escape(k) for k in replacements))
	return pattern.sub(lambda m: replacements[m.group()], text)

def main():
	parser = argparse.ArgumentParser(description="Generate CV from JSON using Jinja2 + LaTeX")
	parser.add_argument("--input", "-i", default="data/cv.json", help="Path to the input JSON file")
	parser.add_argument("--output", "-o", default="out/cv.tex", help="Path to the output LaTeX file")
	parser.add_argument("--template-dir", "-t", default="src/template", help="Path to the Jinja template directory")
	parser.add_argument("--commit-sha", "-c", default=None, help="The hash of the commit that generated the CV")
	args = parser.parse_args()

	# Load JSON data
	with open(args.input, encoding="utf-8") as f:
		data = json.load(f)

	# Setup Jinja environment
	env = Environment(
		loader=FileSystemLoader(args.template_dir),
		autoescape=False
	)

	env.filters["as_date"] = as_date
	env.filters["latex_escape"] = latex_escape
	env.globals["now"] = datetime.now(timezone.utc)
	env.globals["parse_duration"] = parse_duration
	env.globals["commit_sha"] = args.commit_sha

	# Render template
	template = env.get_template("cv.j2")
	rendered = template.render(**data)

	# Write output
	with open(args.output, "w", encoding="utf-8") as f:
		f.write(rendered)

	print(f"✅ CV generated at: {args.output}")

if __name__ == "__main__":
	main()
