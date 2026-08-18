import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from jinja2 import Environment, FileSystemLoader

# Each layout is a self-contained directory under --template-dir holding a root
# cv.j2 plus its own sections/: same data, a different rendering contract.
# "classic" is the typographic one; "ats" trades density for a linear,
# single-column text layer that résumé parsers can read back correctly; "txt"
# goes further still and skips PDF entirely, for portals that take a plain
# text upload or whose extraction is too crude to trust with a PDF at all.
DEFAULT_LAYOUT = "classic"

# Presentation rules a layout overrides regardless of market, because the
# layout deliberately cannot express them. Applied last, so they win.
LAYOUT_RULE_OVERRIDES = {
	# A photo carries nothing a parser can read, and the floating box it needs
	# is exactly the overlapping geometry that derails page segmentation.
	# Forcing it off here also keeps --strict from demanding a photo file for a
	# layout that would never emit it.
	"ats": {"show_photo": False},
	# Plain text has no way to embed an image at all.
	"txt": {"show_photo": False},
}

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

def warn_or_fail(message: str, strict: bool, fallback: str = "") -> None:
	if strict:
		sys.exit(f"❌ {message}")
	print(f"⚠️ {message}{fallback}")

def latex_escape(text: str) -> str:
	if not isinstance(text, str):
		return text
	replacements = {
		'\\': r'\textbackslash{}',
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

def available_layouts(template_dir: str) -> list[str]:
	"""Subdirectories of template_dir that carry a root cv.j2, i.e. are layouts."""
	try:
		entries = os.listdir(template_dir)
	except OSError:
		return []
	return sorted(e for e in entries if os.path.isfile(os.path.join(template_dir, e, "cv.j2")))

# Address rendering is country-specific: the same fields assemble differently
# in each market. "street + number" is "Aeschengraben 17" in Switzerland but
# "17 Aeschengraben" in the US; the postal code precedes the city in CH but
# trails the state in the US. The data carries an optional "format" key on the
# address object selecting one of these patterns; absent, it falls back to the
# historical Swiss ordering so existing data renders exactly as it always has.
# Each format is a list of segments; a segment renders only the fields it has
# -- a missing field collapses to nothing and dangling punctuation is trimmed,
# so "Basel - SP" without a postal code stays "Basel - SP", but a missing
# state renders "Basel" rather than "Basel -".
ADDRESS_FORMATS = {
	"ch": [
		"{street} {number}",
		"{postal_code} {city}",
		"{country}",
	],
	"us": [
		"{number} {street}",
		"{city}",
		"{state} {postal_code}",
		"{country}",
	],
	"br": [
		"{street} {number}",
		"{city} - {state}",
		"{postal_code}",
		"{country}",
	],
}

def _render_address_segment(template: str, address: dict) -> str:
	"""Fill a segment, dropping whatever a missing field leaves behind."""
	fields = re.findall(r"\{(\w+)\}", template)
	values = {field: address.get(field, "") for field in fields}
	return re.sub(r"\s+", " ", template.format_map(values)).strip(" -")

def parse_address(address) -> str:
	if not isinstance(address, dict):
		return ""
	style = ADDRESS_FORMATS.get(str(address.get("format", "ch")).lower(), ADDRESS_FORMATS["ch"])
	return ", ".join(
		segment
		for template in style
		if (segment := _render_address_segment(template, address))
	)

def parse_nationality(nationality) -> str:
	"""Accept a single nationality or a list of them, joined with ", ".

	The data contract historically carried one string; a person can hold
	several nationalities, and the data may carry them as a list. Normalizing
	here keeps every template reading a plain value, and a list joins in the
	order the person listed it, so the rendered line reads naturally.
	"""
	if isinstance(nationality, list):
		return ", ".join(str(n) for n in nationality)
	return nationality or ""

def main():
	parser = argparse.ArgumentParser(description="Generate CV from JSON using Jinja2 + LaTeX")
	parser.add_argument("--input", "-i", default="data/cv.json", help="Path to the input JSON file")
	parser.add_argument("--output", "-o", default="out/cv.tex", help="Path to the output LaTeX file")
	parser.add_argument("--template-dir", "-t", default="src/template", help="Path to the Jinja template directory holding the layouts")
	parser.add_argument("--layout", "-l", default=DEFAULT_LAYOUT, help="Layout to render: a directory under --template-dir (e.g. classic, ats)")
	parser.add_argument("--commit-sha", "-c", default=None, help="The hash of the commit that generated the CV")
	parser.add_argument("--market", "-m", default="default", help="Target market code (e.g. CH, BR) selecting presentation rules")
	parser.add_argument("--market-rules", default="config/market_rules.json", help="Path to the market rules JSON file")
	parser.add_argument("--data-dir", "-d", default=None, help="Directory relative asset paths in the JSON (e.g. the photo) resolve against; defaults to the input file's directory")
	parser.add_argument("--links", action=argparse.BooleanOptionalAction, default=True,
		help="Emit clickable PDF link annotations. --no-links keeps the URL as text but drops the annotation, for employers whose systems object to them")
	parser.add_argument("--strict", action="store_true", help="Fail on unknown market, missing rules file, or missing assets instead of warning")
	args = parser.parse_args()

	# An unknown layout is fatal with or without --strict: unlike a market, there
	# is no sane fallback — without a root template there is nothing to render.
	layout_dir = os.path.join(args.template_dir, args.layout)
	if not os.path.isfile(os.path.join(layout_dir, "cv.j2")):
		available = ", ".join(available_layouts(args.template_dir)) or "none"
		sys.exit(f"❌ Unknown layout '{args.layout}' in {args.template_dir}; available: {available}")

	# LINKS only controls PDF link annotations, and the txt layout has no PDF at
	# all — no txt template even reads the links global, so --no-links changes
	# nothing in its output. It is not an error, but it is almost never a
	# deliberate request: the flag usually arrives as a habit carried over from
	# a PDF layout, and silently doing nothing while claiming to have done
	# something is exactly the failure mode this codebase warns about.
	if args.layout == "txt" and not args.links:
		print("⚠️ --no-links (LINKS=0) has no effect on the txt layout; its output is already plain text")

	# Load JSON data
	with open(args.input, encoding="utf-8") as f:
		data = json.load(f)

	# Nationality is a single string in the data contract, but a person can
	# hold several: the data may carry a list, joined in the order given.
	# Normalize once here so all three layouts keep reading a plain value and
	# their truthiness guards still agree on both shapes.
	if isinstance(data.get("personal"), dict):
		data["personal"]["nationality"] = parse_nationality(data["personal"].get("nationality"))

	# Companies are declared once in a top-level list and referenced from each
	# experience entry by short_name, so the same employer isn't duplicated
	# when it appears in more than one role. Resolve the reference here so
	# every template just reads item.company.name/.url/.description.
	companies = {c["short_name"]: c for c in data.get("companies", [])}
	for entry in data.get("experience", []):
		short_name = entry.get("company")
		company = companies.get(short_name)
		if company is None:
			warn_or_fail(
				f"Unknown company '{short_name}' referenced in experience (no matching companies[].short_name)",
				args.strict, "; using the short_name as a literal display name",
			)
			company = {
				"short_name": short_name, "name": short_name,
				"description": "", "url": "", "is_well_known": False,
			}
		entry["company"] = company

	# Absolute so the rendered .tex is independent of pdflatex's working directory.
	data_dir = os.path.abspath(args.data_dir) if args.data_dir else os.path.dirname(os.path.abspath(args.input))

	# Market presentation rules: country-specific flags merged over defaults.
	# Templates read them via market.get("flag", true), so a missing file or
	# unknown market degrades to showing everything — unless --strict.
	market = {}
	try:
		with open(args.market_rules, encoding="utf-8") as f:
			rules = json.load(f)
		market = {**rules.get("default", {}), **rules.get(args.market, {})}
		if args.market != "default" and args.market not in rules:
			warn_or_fail(f"Market '{args.market}' not found in {args.market_rules}", args.strict, "; using defaults")
	except FileNotFoundError:
		warn_or_fail(f"Market rules file not found: {args.market_rules}", args.strict, "; showing all fields")

	# Applied after the market so a layout that cannot render a field wins over
	# a market that asks for it (e.g. CH wants a photo, the ATS layout has none).
	market.update(LAYOUT_RULE_OVERRIDES.get(args.layout, {}))

	# Resolve the photo against the data directory so the data repo stays
	# self-contained wherever the pipeline checks it out, and fail fast here
	# rather than deep inside pdflatex.
	personal = data.get("personal", {})
	photo = personal.get("photo")
	if photo and market.get("show_photo", True):
		photo_path = photo if os.path.isabs(photo) else os.path.join(data_dir, photo)
		if os.path.isfile(photo_path):
			personal["photo"] = photo_path
		else:
			warn_or_fail(f"Photo not found: {photo_path}", args.strict, "; omitting it")
			personal.pop("photo", None)

	# Rooted at the layout directory so every layout refers to its own
	# "cv.j2" and "sections/*.j2" by the same names.
	# trim_blocks/lstrip_blocks swallow the newline and leading whitespace a
	# {% %} tag leaves on its own line. LaTeX shrugs that whitespace off, so the
	# other layouts don't need it, but in a plain-text layout it would otherwise
	# come straight out as blank lines and stray indentation in the artefact.
	env = Environment(
		loader=FileSystemLoader(layout_dir),
		autoescape=False,
		trim_blocks=(args.layout == "txt"),
		lstrip_blocks=(args.layout == "txt"),
	)

	env.filters["as_date"] = as_date
	env.filters["latex_escape"] = latex_escape
	env.globals["now"] = datetime.now(timezone.utc)
	env.globals["parse_duration"] = parse_duration
	env.globals["commit_sha"] = args.commit_sha
	env.globals["market"] = market
	env.globals["layout"] = args.layout
	env.globals["links"] = args.links
	env.globals["parse_address"] = parse_address

	# Render template
	template = env.get_template("cv.j2")
	rendered = template.render(**data)

	# Write output
	with open(args.output, "w", encoding="utf-8") as f:
		f.write(rendered)

	print(f"✅ CV generated at: {args.output} (layout: {args.layout}, market: {args.market})")

if __name__ == "__main__":
	main()
