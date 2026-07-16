import argparse
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

def parse_duration(
  date_string_start: str,
  date_string_end: str,
  fmt_key = "yyyy-MM-dd") -> str:
	fmt = latex_format_map.get(fmt_key, fmt_key)
	try:
		start_date = datetime.strptime(date_string_start, fmt).date()
		if date_string_end:
			end_date = datetime.strptime(date_string_end, fmt).date()
		else:
			end_date = datetime.now(timezone.utc).date()

		# Exact calendar arithmetic, month granularity: days are too much
		# detail for a CV, and coarser rounding undersells tenure.
		months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
		if end_date.day < start_date.day:
			months -= 1
		years, months = divmod(max(months, 0), 12)

		parts = []
		if years:
			parts.append(f"{years} year{'s' if years != 1 else ''}")
		if months:
			parts.append(f"{months} month{'s' if months != 1 else ''}")
		if not parts:
			return "less than a month"
		return ", ".join(parts)

	except Exception:
		return "Unknown duration"


def as_date(date_string: str, fmt_key: str = "yyyy-MM-dd", consider_present_for_blank = True) -> str:
	fmt = latex_format_map.get(fmt_key, fmt_key)
	try:
		if consider_present_for_blank and not date_string:
			return "Present"
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
	parser.add_argument("--market", "-m", default="default", help="Target market code (e.g. CH, BR) selecting presentation rules")
	parser.add_argument("--market-rules", default="data/target_market_rules.json", help="Path to the market rules JSON file")
	args = parser.parse_args()

	# Load JSON data
	with open(args.input, encoding="utf-8") as f:
		data = json.load(f)

	# Market presentation rules: country-specific flags merged over defaults.
	# Templates read them via market.get("flag", true), so a missing file or
	# unknown market degrades to showing everything.
	market = {}
	try:
		with open(args.market_rules, encoding="utf-8") as f:
			rules = json.load(f)
		market = {**rules.get("default", {}), **rules.get(args.market, {})}
		if args.market != "default" and args.market not in rules:
			print(f"⚠️ Market '{args.market}' not found in {args.market_rules}; using defaults")
	except FileNotFoundError:
		print(f"⚠️ Market rules file not found: {args.market_rules}; showing all fields")

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
	env.globals["market"] = market

	# Render template
	template = env.get_template("cv.j2")
	rendered = template.render(**data)

	# Write output
	with open(args.output, "w", encoding="utf-8") as f:
		f.write(rendered)

	print(f"✅ CV generated at: {args.output}")

if __name__ == "__main__":
	main()
