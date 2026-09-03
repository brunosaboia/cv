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

# languages[].level is our own market-independent scale: 0 (native) plus the
# six CEFR letters in descending order, 1 (C2) through 6 (A1). Not a
# market_rules.json flag -- unlike show_photo/show_dob this doesn't toggle
# template content on or off, it picks which of these tables a level is
# translated through before templates ever see it, so there is nothing for a
# template itself to read (test_every_declared_rule_is_read_by_a_template
# only applies to flags templates branch on).
LANGUAGE_LEVEL_LABELS = {
	# Five wording tiers to seven levels: each label sits at the tier it has
	# always meant (C2 = full professional, B2 = professional working,
	# B1 = limited professional, A2 = basic), kept verbatim from the strings
	# both datasets used before this scale existed. The two tiers CEFR adds
	# between them (C1, A1) inherit their neighbour's wording rather than
	# invent new strings -- so renumbering the data onto the finer ladder
	# left every descriptive rendering byte-identical.
	"descriptive": {
		0: "Native",
		1: "Full professional proficiency",
		2: "Full professional proficiency",
		3: "Professional working proficiency",
		4: "Limited professional proficiency",
		5: "Basic",
		6: "Basic",
	},
	# Native stays its own label rather than folding into C2 (a native
	# speaker isn't merely "C2" -- CEFR has no tier for a mother tongue);
	# levels 1-6 are the six letters, C2 down to A1.
	"cefr": {
		0: "Native",
		1: "C2",
		2: "C1",
		3: "B2",
		4: "B1",
		5: "A2",
		6: "A1",
	},
}
DEFAULT_LANGUAGE_SCALE = "descriptive"
# Markets where a CEFR letter is the expected shorthand for language level.
LANGUAGE_SCALE_BY_MARKET = {
	"switzerland": "cefr",
	"continental_europe": "cefr",
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

def parse_rules_override(raw: str, valid_keys: set, strict: bool) -> dict:
	"""Parse --rules-override's "key=value,key=value" string into a flag dict.

	Applied after market rules and LAYOUT_RULE_OVERRIDES, so this always wins.
	Unknown keys and unparseable values follow the same warn_or_fail convention
	as an unknown market: skipped with a warning, fatal under --strict.
	"""
	overrides = {}
	for pair in raw.split(","):
		pair = pair.strip()
		if not pair:
			continue
		if "=" not in pair:
			warn_or_fail(f"Malformed --rules-override entry '{pair}' (expected key=value)", strict, "; skipping it")
			continue
		key, _, value = pair.partition("=")
		key = key.strip()
		value = value.strip().lower()
		if key not in valid_keys:
			warn_or_fail(f"Unknown --rules-override key '{key}'", strict, "; skipping it")
			continue
		if value not in ("true", "false"):
			warn_or_fail(f"Malformed --rules-override value '{value}' for key '{key}' (expected true/false)", strict, "; skipping it")
			continue
		overrides[key] = value == "true"
	return overrides

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

def simplify_remote_location(location: str) -> str:
	"""Collapse "Remote (Brazil -- US)" down to the bare "Remote".

	The parenthetical country pair helps a human reader; an ATS location
	field expects a single place name and doesn't parse a country pair
	correctly, so it reads as noise or a mis-parsed field instead of
	information. Any location string that already just says "Remote" (no
	parenthetical) passes through unchanged.
	"""
	if isinstance(location, str) and location.strip().lower().startswith("remote"):
		return "Remote"
	return location

# The fields that describe a position rather than the employer. Moving exactly
# these down a level is what makes a flat entry and a one-role group
# indistinguishable once normalized, which is what lets both spellings live in
# the data indefinitely -- most entries are written flat and there is no reason
# to rewrite them. "location" is deliberately not one of them: it belongs to
# the entry, and a role only ever overrides it (see flatten_roles).
ROLE_FIELDS = ("title", "duration", "description", "achievements", "technologies")

def _is_iso_date(value) -> bool:
	"""Whether a value is a yyyy-MM-dd string, i.e. safe to order lexically."""
	return isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None

def role_span(roles: list) -> dict:
	"""Earliest start and latest end across one company's roles.

	ISO dates sort correctly as plain strings, so this needs no date parsing
	and inherits none of strptime's failure modes. A blank or absent end means
	the role is current, and that dominates the whole group: you have not left
	a company you still work at, whatever the other roles say.

	A date that doesn't look like a date is left out of the comparison and the
	first role's raw value passed through instead. Malformed dates already
	print verbatim everywhere else in this pipeline (as_date hands them back
	unchanged, parse_duration says "Unknown duration"), and a derived span is a
	reading convenience, not a fact worth failing a build over.
	"""
	starts = [role.get("duration", {}).get("start") for role in roles]
	ends = [role.get("duration", {}).get("end") for role in roles]

	usable_starts = [start for start in starts if _is_iso_date(start)]
	start = min(usable_starts) if usable_starts else (starts[0] if starts else "")

	if any(not end for end in ends):
		end = ""
	else:
		usable_ends = [end for end in ends if _is_iso_date(end)]
		end = max(usable_ends) if usable_ends else (ends[0] if ends else "")

	return {"start": start, "end": end}

def normalize_experience(entry: dict, strict: bool = False) -> dict:
	"""Reshape one experience entry into a company node holding roles[].

	A promotion is one employer, not two, so an entry may carry several roles
	under a shared company and location. An entry written the older flat way --
	title/duration/description/technologies directly on the entry -- collapses
	to a one-role group here, so no template ever branches on which spelling
	the JSON used and no existing data has to be migrated.

	That backwards compatibility is load-bearing rather than merely polite:
	cv-data is deployed from a checkout of cv's default branch, so this
	generator has to keep rendering a cv.json that hasn't adopted roles[] yet.
	"""
	if isinstance(entry.get("roles"), list):
		roles = [dict(role) for role in entry["roles"]]
		# A role field left at the top level next to roles[] is an authoring
		# slip, and a silent one: nothing reads it, so whatever it says simply
		# never prints. Say so rather than let it vanish.
		stray = [field for field in ROLE_FIELDS if field in entry]
		if stray:
			warn_or_fail(
				f"Experience entry for '{entry.get('company')}' carries both roles[] and "
				f"top-level {', '.join(stray)}",
				strict, "; the top-level field(s) will not be rendered",
			)
	else:
		roles = [{field: entry[field] for field in ROLE_FIELDS if field in entry}]

	if not roles:
		warn_or_fail(
			f"Experience entry for '{entry.get('company')}' has no roles",
			strict, "; it will render as an employer with no positions",
		)

	group = {key: value for key, value in entry.items() if key not in ROLE_FIELDS and key != "roles"}
	group["roles"] = roles
	group["span"] = role_span(roles)
	return group

def flatten_roles(experience: list) -> list:
	"""Re-expand grouped entries into one self-contained block per role.

	classic prints a company header once and nests its roles under it. ats and
	txt deliberately do not: a resume parser keys on a company/title/dates
	triple appearing on consecutive lines, and a lone header with two roles
	beneath it is exactly the shape that makes it attribute both to the first
	title, or drop the earlier role entirely -- the failure the ats layout
	exists to avoid.

	Flattening here rather than nesting a second loop in each of those two
	templates keeps their bodies literally the markup they were before grouping
	existed, so their text layer is provably unchanged. That text layer is the
	whole artefact as far as a scanner is concerned.
	"""
	return [
		{
			**role,
			"company": entry.get("company"),
			"location": role.get("location") or entry.get("location"),
		}
		for entry in experience
		for role in entry.get("roles", [])
	]

# The legacy skills shape: three fixed buckets, the first two holding
# {name, years} objects, with each layout hardcoding its own three headings.
# The pairing is (data key, heading it becomes) -- ats/txt wording, since it
# is the more conventional phrasing of the two the layouts used to disagree on.
LEGACY_SKILL_GROUPS = (
	("programming", "Programming Languages"),
	("technologies", "Technologies"),
	("other", "Other Skills"),
)

def _legacy_skill_item(entry) -> str:
	"""One legacy {name, years} object as the text its item renders to.

	The years are folded into the string rather than dropped, so a dataset on
	the old shape renders exactly what it rendered before.
	"""
	if not isinstance(entry, dict):
		return str(entry)
	name = entry.get("name", "")
	years = entry.get("years")
	if years is None:
		return name
	return f"{name} ({years} yr{'' if years == 1 else 's'})"

def normalize_skills(skills) -> list:
	"""Reshape the skills block into an ordered list of {label, items} groups.

	Skills used to be three hardcoded buckets -- programming, technologies,
	other -- and every layout spelled its own headings inline. That fixed the
	categories in the templates, so grouping by domain (cloud, data, AI/ML)
	meant editing three templates rather than the data. The list-of-groups
	shape moves both the categories and their order into the JSON, where they
	belong, and leaves the templates a single loop.

	The old dict is still accepted and still prints its years, because cv is
	deployed from its default branch against whatever cv-data is live: in the
	window between a generator push and the data push that follows it, this
	function is the only thing standing between the old data and an empty
	Skills section. It reads exactly the three keys the old shape had -- it is
	a shim for a closed format, not a second format to maintain.

	Empty groups are dropped rather than rendered as a heading with nothing
	under it, which is what the old templates' per-bucket `{% if %}` did.
	"""
	if isinstance(skills, list):
		return [group for group in skills if group.get("items")]
	if not isinstance(skills, dict):
		return []

	groups = []
	for key, label in LEGACY_SKILL_GROUPS:
		items = [_legacy_skill_item(entry) for entry in skills.get(key) or []]
		if items:
			groups.append({"label": label, "items": items})
	return groups

def main():
	parser = argparse.ArgumentParser(description="Generate CV from JSON using Jinja2 + LaTeX")
	parser.add_argument("--input", "-i", default="data/cv.json", help="Path to the input JSON file")
	parser.add_argument("--output", "-o", default="out/cv.tex", help="Path to the output LaTeX file")
	parser.add_argument("--template-dir", "-t", default="src/template", help="Path to the Jinja template directory holding the layouts")
	parser.add_argument("--layout", "-l", default=DEFAULT_LAYOUT, help="Layout to render: a directory under --template-dir (e.g. classic, ats)")
	parser.add_argument("--commit-sha", "-c", default=None, help="The hash of the commit that generated the CV")
	parser.add_argument("--market", "-m", default="international", help="Target market (e.g. switzerland, continental_europe) selecting presentation rules")
	parser.add_argument("--market-rules", default="config/market_rules.json", help="Path to the market rules JSON file")
	parser.add_argument("--data-dir", "-d", default=None, help="Directory relative asset paths in the JSON (e.g. the photo) resolve against; defaults to the input file's directory")
	parser.add_argument("--links", action=argparse.BooleanOptionalAction, default=True,
		help="Emit clickable PDF link annotations. --no-links keeps the URL as text but drops the annotation, for employers whose systems object to them")
	parser.add_argument("--company-descriptions", choices=("min", "mid", "max"), default="mid",
		help="How many employer blurbs to print: min hides every companies[].description, "
		     "mid (default) hides only a company flagged is_well_known, max shows them all")
	parser.add_argument("--strict", action="store_true", help="Fail on unknown market, missing rules file, or missing assets instead of warning")
	parser.add_argument("--rules-override", default=None,
		help="Comma-separated key=value overrides applied after market/layout rules, "
		     "e.g. show_photo=false,show_address=true")
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

	# An entry may hold several roles at one employer (a promotion), or the
	# older flat one-role-per-entry shape. Collapse both to the same company
	# node here, before anything below reads the list, so every later step and
	# every template sees exactly one shape.
	# Guarded rather than data.get(..., []): a dataset with no experience at all
	# (the ats contact-block test builds one) should stay without the key rather
	# than gain an empty list nothing asked for.
	# Skills are an ordered list of {label, items} groups. The legacy
	# three-bucket dict normalizes to the same thing here, so no template
	# branches on which shape the JSON used.
	if "skills" in data:
		data["skills"] = normalize_skills(data["skills"])

	if "experience" in data:
		data["experience"] = [
			normalize_experience(entry, args.strict)
			for entry in data["experience"]
		]

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
		# The build-wide --company-descriptions level wins over what an
		# individual company declares about itself: min hides every blurb
		# regardless, max shows every blurb regardless, and only mid (the
		# default) defers to companies[].is_well_known. Resolved once here so
		# every layout's template reads a single flag instead of repeating
		# this three-way choice in three places.
		company["show_description"] = {
			"min": False,
			"mid": not company.get("is_well_known", False),
			"max": True,
		}[args.company_descriptions]
		entry["company"] = company

	# Absolute so the rendered .tex is independent of pdflatex's working directory.
	data_dir = os.path.abspath(args.data_dir) if args.data_dir else os.path.dirname(os.path.abspath(args.input))

	# Market presentation rules: one fully-spelled-out flag set per named
	# market (e.g. "switzerland"), keyed under "markets". Templates read them
	# via market.get("flag", true), so a missing file or unknown market
	# degrades to showing everything — unless --strict.
	market = {}
	valid_rule_keys = set()
	for flags in LAYOUT_RULE_OVERRIDES.values():
		valid_rule_keys.update(flags)
	try:
		with open(args.market_rules, encoding="utf-8") as f:
			rules = json.load(f)
		markets = rules.get("markets", {})
		default_market = rules.get("default_market", "international")
		for flags in markets.values():
			valid_rule_keys.update(flags)
		if args.market not in markets:
			warn_or_fail(f"Market '{args.market}' not found in {args.market_rules}", args.strict, "; using defaults")
			market = dict(markets.get(default_market, {}))
		else:
			market = dict(markets[args.market])
	except FileNotFoundError:
		warn_or_fail(f"Market rules file not found: {args.market_rules}", args.strict, "; showing all fields")

	# Applied after the market so a layout that cannot render a field wins over
	# a market that asks for it (e.g. CH wants a photo, the ATS layout has none).
	market.update(LAYOUT_RULE_OVERRIDES.get(args.layout, {}))

	# Applied last so an explicit CLI override always wins over both the named
	# market and the layout's own overrides.
	if args.rules_override:
		market.update(parse_rules_override(args.rules_override, valid_rule_keys, args.strict))

	# languages[].level is data as a 0-6 integer; resolve it to the display
	# string here so every layout's template just reads a plain value, the
	# same shape it always has.
	language_scale = LANGUAGE_LEVEL_LABELS[LANGUAGE_SCALE_BY_MARKET.get(args.market, DEFAULT_LANGUAGE_SCALE)]
	for lang in data.get("languages", []):
		level = lang.get("level")
		label = language_scale.get(level)
		if label is None:
			warn_or_fail(
				f"Unknown language level {level!r} for '{lang.get('name')}' (expected an integer 0-6)",
				args.strict, "; showing the raw value",
			)
			label = str(level)
		lang["level"] = label

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
	env.filters["simplify_remote_location"] = simplify_remote_location
	env.filters["flatten_roles"] = flatten_roles
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
