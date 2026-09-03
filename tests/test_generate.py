import json
import re
import sys
from pathlib import Path

import pytest

from generate_cv import (
	available_layouts,
	flatten_roles,
	main,
	normalize_experience,
	normalize_skills,
	parse_nationality,
	role_span,
	simplify_remote_location,
	warn_or_fail,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# The sample's current role is open-ended, so parse_duration measures it against
# today and the rendered string grows by a month every month. Match its shape,
# not one month's arithmetic. Only classic prints this parenthetical at all
# (see TestClassicLayout) -- ats/txt deliberately omit it, see their layout
# test classes below.
ONGOING_DURATION = re.compile(r"\{\\sl \(\d+ years?(?:, \d+ months?)?\)\}")


def run_main(tmp_path, monkeypatch, *extra_args, input_json=None):
	output = tmp_path / "cv.tex"
	argv = [
		"generate_cv.py",
		"--input", str(input_json or REPO_ROOT / "data" / "cv.json"),
		"--output", str(output),
		"--template-dir", str(REPO_ROOT / "src" / "template"),
		"--market-rules", str(REPO_ROOT / "config" / "market_rules.json"),
		*extra_args,
	]
	monkeypatch.setattr(sys, "argv", argv)
	main()
	return output.read_text(encoding="utf-8")


def strip_latex_comments(tex: str) -> str:
	"""Drop whole-line % comments, so asserting a command is absent isn't
	defeated by a comment explaining why it is absent."""
	return "\n".join(line for line in tex.splitlines() if not line.lstrip().startswith("%"))


class TestMarkets:
	def test_default_market_is_conservative(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch)
		assert "includegraphics" not in tex
		assert "Date of birth:" not in tex
		assert "Address:" not in tex
		assert "Nationality:" not in tex

	def test_nationality_is_a_declared_rule_not_a_get_default(self, tmp_path, monkeypatch):
		# Templates probe show_nationality with market.get(..., true), so an
		# undeclared flag would silently mean "show it" and leak nationality
		# into every market. It has to be spelled out in the rules file.
		rules = json.loads((REPO_ROOT / "config" / "market_rules.json").read_text(encoding="utf-8"))
		assert rules["markets"]["international"]["show_nationality"] is False
		assert rules["markets"]["switzerland"]["show_nationality"] is True

	def test_every_declared_rule_is_read_by_a_template(self):
		# A flag nobody reads is dead configuration that reads as a feature.
		templates = (REPO_ROOT / "src" / "template").rglob("*.j2")
		rendered_by = "\n".join(t.read_text(encoding="utf-8") for t in templates)
		rules = json.loads((REPO_ROOT / "config" / "market_rules.json").read_text(encoding="utf-8"))
		declared = {flag for market in rules["markets"].values() for flag in market}
		assert {flag for flag in declared if flag not in rendered_by} == set()

	def test_ch_market_shows_everything(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch, "--market", "switzerland")
		photo = REPO_ROOT / "data" / "profile.png"
		assert f"\\includegraphics[width=1in]{{{photo}}}" in tex
		assert photo.is_absolute()
		assert "Date of birth:" in tex
		assert "Address:" in tex
		assert "Nationality:" in tex

	def test_br_market_hides_photo_dob_address(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch, "--market", "international")
		assert "includegraphics" not in tex
		assert "Date of birth:" not in tex
		assert "Address:" not in tex

	def test_unknown_market_warns_and_uses_defaults(self, tmp_path, monkeypatch, capsys):
		tex = run_main(tmp_path, monkeypatch, "--market", "XX")
		assert "not found" in capsys.readouterr().out
		assert "includegraphics" not in tex

	def test_unknown_market_strict_fails(self, tmp_path, monkeypatch):
		with pytest.raises(SystemExit):
			run_main(tmp_path, monkeypatch, "--market", "XX", "--strict")


class TestNationalities:
	"""personal.nationality accepts a single string or a list of them, so a
	person with several nationalities can list them all in one field."""

	def test_single_string_passes_through(self):
		assert parse_nationality("Swiss") == "Swiss"

	def test_list_joins_in_given_order(self):
		assert parse_nationality(["Swiss", "Italian"]) == "Swiss, Italian"

	def test_blank_forms_render_nothing(self):
		assert parse_nationality("") == ""
		assert parse_nationality(None) == ""
		assert parse_nationality([]) == ""

	def test_list_members_are_stringified(self):
		# The schema says strings; a stray non-string in the list must not
		# crash the build.
		assert parse_nationality([42]) == "42"

	def test_ch_market_renders_multiple_nationalities(self, tmp_path, monkeypatch):
		data = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))
		data["personal"]["nationality"] = ["Swiss", "Italian"]
		specials = tmp_path / "specials.json"
		specials.write_text(json.dumps(data), encoding="utf-8")
		tex = run_main(tmp_path, monkeypatch, "--market", "switzerland", input_json=specials)
		assert "Nationality: Swiss, Italian" in tex


class TestLayouts:
	def test_default_layout_is_classic(self, tmp_path, monkeypatch):
		assert "\\documentclass[margin]{res}" in run_main(tmp_path, monkeypatch)

	def test_ats_layout_selected_explicitly(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch, "--layout", "ats")
		assert "\\documentclass[11pt,a4paper]{article}" in tex

	def test_unknown_layout_always_fails_and_lists_the_real_ones(self, tmp_path, monkeypatch):
		# Fatal with or without --strict: there is no template to fall back to.
		with pytest.raises(SystemExit) as exc_info:
			run_main(tmp_path, monkeypatch, "--layout", "nope")
		message = str(exc_info.value)
		assert "Unknown layout 'nope'" in message
		assert "ats, classic, txt" in message

	def test_txt_layout_selected_explicitly(self, tmp_path, monkeypatch):
		txt = run_main(tmp_path, monkeypatch, "--layout", "txt")
		assert "\\documentclass" not in txt
		assert "John Doe" in txt

	def test_available_layouts_lists_directories_holding_a_root_template(self):
		assert available_layouts(str(REPO_ROOT / "src" / "template")) == ["ats", "classic", "txt"]

	def test_available_layouts_of_a_missing_directory_is_empty(self, tmp_path):
		assert available_layouts(str(tmp_path / "nowhere")) == []


class TestClassicLayout:
	"""classic is the human-facing layout: unlike ats/txt, it keeps the
	computed "(X years, Y months)" next to the date range as a readability
	aid, since a person reading the PDF benefits from it in a way a parser
	that already has both exact dates does not."""

	def test_dates_include_the_computed_duration(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch)
		assert ONGOING_DURATION.search(tex)


class TestAtsLayoutIsParseable:
	"""The properties an ATS layout exists for: everything a résumé scanner
	reads back out of the PDF text layer has to survive extraction."""

	@pytest.fixture
	def tex(self, tmp_path, monkeypatch):
		return run_main(tmp_path, monkeypatch, "--layout", "ats")

	def test_no_second_column(self, tex):
		# \hfill is what pushes dates away from their heading in the content
		# stream, so a scanner reads them as unrelated fragments.
		assert "\\hfill" not in strip_latex_comments(tex)

	def test_hyphenation_is_disabled(self, tex):
		# Extractors do not rejoin a word split across lines: "Kuber-\nnetes"
		# stops matching the keyword "Kubernetes".
		assert "\\hyphenpenalty=10000" in tex

	def test_no_page_furniture(self, tex):
		# A page number lands in the text stream between two entries.
		assert "\\pagestyle{empty}" in tex

	def test_headings_use_conventional_section_names(self, tex):
		for heading in ("Professional Summary", "Work Experience", "Education", "Skills", "Languages"):
			assert f"\\cvsection{{{heading}}}" in tex

	def test_unmapped_heading_falls_back_to_the_data_key(self, tmp_path, monkeypatch):
		assert "\\cvsection{Publications}" in run_main(tmp_path, monkeypatch, "--layout", "ats")

	def test_contact_urls_are_their_own_link_text(self, tex):
		# A link labelled "LinkedIn" keeps its address in the annotation layer,
		# which text extraction never sees.
		assert "LinkedIn: \\weburl{https://linkedin.com/in/johndoe}" in tex
		assert "GitHub: \\weburl{https://github.com/johndoe}" in tex

	def test_dates_stay_next_to_their_employer(self, tex):
		assert "Swiss National Bank, Zürich, CH" in tex
		# ats prints the bare start/end range, unlike classic/txt: an ATS parser
		# computes tenure itself from the two dates, so the appended "(X years,
		# Y months)" is redundant text a parser might misread as its own field.
		assert "June 2023 - Present" in tex

	def test_labelled_contact_fields(self, tex):
		assert "Email: " in tex
		assert "Phone: " in tex

	def test_contact_block_survives_missing_optional_fields(self, tmp_path, monkeypatch):
		# The contact lines are one \\-separated paragraph, so every optional
		# field has to *lead* with its \\. A field appended with a trailing one
		# instead would leave a dangling \\ before the blank line and pdflatex
		# would stop with "There's no line here to end".
		data = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))
		minimal = {
			"headers": ["summary"],
			"summary": data["summary"],
			"personal": {k: data["personal"][k] for k in ("name", "email", "phone", "cv_url")},
		}
		minimal_json = tmp_path / "minimal.json"
		minimal_json.write_text(json.dumps(minimal), encoding="utf-8")

		tex = run_main(tmp_path, monkeypatch, "--layout", "ats", "--market", "switzerland", input_json=minimal_json)
		assert "LinkedIn" not in tex
		assert re.search(r"\\\\\s*\n\s*\n", tex) is None


class TestTxtLayout:
	"""The plain-text layout has no markup at all: what Jinja renders is the
	final artefact, so there is nothing between the data and the reader."""

	@pytest.fixture
	def txt(self, tmp_path, monkeypatch):
		return run_main(tmp_path, monkeypatch, "--layout", "txt")

	def test_no_latex_markup(self, txt):
		assert "\\" not in txt
		assert "\\documentclass" not in txt

	def test_headings_use_conventional_section_names(self, txt):
		for heading in ("PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "EDUCATION", "SKILLS", "LANGUAGES"):
			assert heading in txt

	def test_dates_stay_next_to_their_employer(self, txt):
		# Like ats: the reader already has both dates and can work out tenure
		# itself, so the exact line has no "(X years, Y months)" suffix -- that
		# readability aid is classic's job.
		lines = txt.splitlines()
		company_line = next(i for i, l in enumerate(lines) if l.startswith("Swiss National Bank"))
		assert lines[company_line + 2] == "June 2023 - Present"

	def test_labelled_contact_fields(self, txt):
		assert "Email: john.doe@example.com" in txt
		assert "Phone: " in txt

	def test_urls_are_plain_text(self, txt):
		assert "LinkedIn: https://linkedin.com/in/johndoe" in txt
		assert "GitHub: https://github.com/johndoe" in txt

	def test_no_photo_even_for_a_photo_market(self, tmp_path, monkeypatch):
		txt = run_main(tmp_path, monkeypatch, "--layout", "txt", "--market", "switzerland")
		assert "Address: " in txt
		assert "Date of birth: " in txt

	def test_remote_location_collapses_to_the_bare_word(self, txt):
		# GlobalTech's location in the sample data is "Remote (CH -- UK)" --
		# an ATS location field expects a single place name and doesn't parse
		# a country pair correctly, so it reads as noise there.
		assert "GlobalTech Solutions, Remote" in txt
		assert "Remote (CH -- UK)" not in txt

	def test_non_remote_location_is_unaffected(self, txt):
		assert "Swiss National Bank, Zürich, CH" in txt


class TestSimplifyRemoteLocation:
	"""Unit tests for the function TestTxtLayout exercises end to end."""

	def test_collapses_a_parenthetical_country_pair(self):
		assert simplify_remote_location("Remote (Brazil -- US)") == "Remote"

	def test_bare_remote_passes_through(self):
		assert simplify_remote_location("Remote") == "Remote"

	def test_case_insensitive(self):
		assert simplify_remote_location("remote (Brazil -- US)") == "Remote"

	def test_non_remote_location_is_untouched(self):
		assert simplify_remote_location("Zürich, CH") == "Zürich, CH"

	def test_a_city_that_merely_contains_remote_is_not_matched(self):
		# startswith, not a substring search: a location would have to open
		# with the word "Remote" to be treated as one.
		assert simplify_remote_location("Fort Remote, US") == "Fort Remote, US"


class TestLanguagesSection:
	"""Spoken languages are a top-level section, not a skills subsection."""

	@pytest.mark.parametrize("layout", ["classic", "ats", "txt"])
	def test_rendered_from_the_top_level_key(self, tmp_path, monkeypatch, layout):
		tex = run_main(tmp_path, monkeypatch, "--layout", layout)
		assert "English" in tex and "Native" in tex

	def test_ats_heading_is_the_conventional_name(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch, "--layout", "ats")
		assert "\\cvsection{Languages}" in tex
		# The disambiguating label is gone with the subsection it belonged to,
		# but the programming one stays labelled under Skills.
		assert "Spoken Languages" not in tex
		assert "\\textbf{Programming Languages:}" in tex

	def test_headers_order_places_it_after_skills(self):
		headers = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))["headers"]
		assert headers.index("languages") == headers.index("skills") + 1

	def test_data_no_longer_nests_it_under_skills(self):
		data = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))
		assert "languages" in data
		assert "languages" not in data["skills"]


class TestLanguageLevels:
	"""languages[].level is our own scale: 0 native plus the six CEFR letters,
	1 (C2) through 6 (A1), translated to a display string per market: CEFR
	letters for switzerland/continental_europe, the descriptive wording every
	other market (and the data itself, before this scale existed) already used.
	Sample data: English=0, French=1, German=2."""

	@pytest.mark.parametrize("market", ["international"])
	def test_non_european_markets_use_the_descriptive_wording(self, tmp_path, monkeypatch, market):
		tex = run_main(tmp_path, monkeypatch, "--market", market)
		assert "English — Native" in tex
		assert "French — Full professional proficiency" in tex
		# C1 has no descriptive wording of its own: it repeats C2's.
		assert "German — Full professional proficiency" in tex

	@pytest.mark.parametrize("market", ["switzerland", "continental_europe"])
	def test_ch_de_use_cefr_letters(self, tmp_path, monkeypatch, market):
		tex = run_main(tmp_path, monkeypatch, "--market", market)
		assert "English — Native" in tex  # native has no CEFR letter
		assert "French — C2" in tex
		assert "German — C1" in tex

	@pytest.mark.parametrize("market,expected", [
		("international", [
			"Native",
			"Full professional proficiency",
			"Full professional proficiency",
			"Professional working proficiency",
			"Limited professional proficiency",
			"Basic",
			"Basic",
		]),
		("switzerland", ["Native", "C2", "C1", "B2", "B1", "A2", "A1"]),
	])
	def test_every_level_maps_to_exactly_one_label(self, tmp_path, monkeypatch, market, expected):
		data = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))
		data["languages"] = [{"name": f"L{level}", "level": level} for level in range(7)]
		specials = tmp_path / "specials.json"
		specials.write_text(json.dumps(data), encoding="utf-8")
		tex = run_main(tmp_path, monkeypatch, "--market", market, input_json=specials)
		for level, label in enumerate(expected):
			assert f"L{level} — {label}" in tex

	def test_unknown_level_warns_and_shows_the_raw_value(self, tmp_path, monkeypatch, capsys):
		data = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))
		data["languages"][0]["level"] = 7
		specials = tmp_path / "specials.json"
		specials.write_text(json.dumps(data), encoding="utf-8")
		tex = run_main(tmp_path, monkeypatch, input_json=specials)
		assert "Unknown language level 7" in capsys.readouterr().out
		assert "English — 7" in tex

	def test_unknown_level_strict_fails(self, tmp_path, monkeypatch):
		data = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))
		data["languages"][0]["level"] = 7
		specials = tmp_path / "specials.json"
		specials.write_text(json.dumps(data), encoding="utf-8")
		with pytest.raises(SystemExit):
			run_main(tmp_path, monkeypatch, "--strict", input_json=specials)


class TestLinks:
	def test_links_are_on_by_default(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch, "--layout", "ats")
		assert "\\newcommand{\\weburl}[1]{\\href{#1}{\\nolinkurl{#1}}}" in tex
		assert "\\href{mailto:john.doe@example.com}" in tex

	def test_no_links_defines_weburl_without_a_link(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch, "--layout", "ats", "--no-links")
		assert "\\newcommand{\\weburl}[1]{\\nolinkurl{#1}}" in tex

	def test_no_links_keeps_the_address_as_text(self, tmp_path, monkeypatch):
		# The point of the option: drop the annotation, never the URL.
		tex = run_main(tmp_path, monkeypatch, "--layout", "ats", "--no-links")
		assert "LinkedIn: \\weburl{https://linkedin.com/in/johndoe}" in tex
		assert "GitHub: \\weburl{https://github.com/johndoe}" in tex
		assert "Email: john.doe@example.com" in tex

	@pytest.mark.parametrize("layout", ["classic", "ats", "txt"])
	def test_no_links_leaves_no_href_in_any_layout(self, tmp_path, monkeypatch, layout):
		# \href is the only thing that emits a PDF link annotation, so one
		# unguarded call anywhere in a section template silently defeats the
		# whole option -- which is exactly how experience.j2 was first missed.
		tex = run_main(tmp_path, monkeypatch, "--layout", layout, "--market", "switzerland", "--no-links")
		assert "\\href" not in strip_latex_comments(tex)

	def test_classic_no_links_promotes_labelled_urls_to_text(self, tmp_path, monkeypatch):
		# These four were reachable only through their link text, so dropping
		# the annotation has to surface the address instead of losing it.
		tex = run_main(tmp_path, monkeypatch, "--layout", "classic", "--no-links")
		for url in (
			"https://github.com/johndoe",
			"https://linkedin.com/in/johndoe",
			"https://example.com/assets/pdf/transcripts/ethz-ms.pdf",
			"https://example.com/ai-prize-2022",
		):
			# \weburl inline, \weburlline where it gets a ragged line of its own.
			assert re.search(rf"\\weburl(?:line)?\{{{re.escape(url)}\}}", tex)

	def test_classic_keeps_its_labels_when_linked(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch, "--layout", "classic")
		assert "{GitHub}" in tex
		assert "{Transcript of records}" in tex
		assert "\\weburl" not in tex

	def test_txt_no_links_warns_it_is_a_noop(self, tmp_path, monkeypatch, capsys):
		# txt has no PDF and no template reads the links global, so --no-links
		# changes nothing in its output; a warning catches the invocation that
		# carried the flag over from a PDF layout out of habit.
		run_main(tmp_path, monkeypatch, "--layout", "txt", "--no-links")
		assert "--no-links" in capsys.readouterr().out

	def test_pdf_layouts_do_not_warn_for_no_links(self, tmp_path, monkeypatch, capsys):
		# The flag is meaningful (and consumed) for the PDF layouts, so it must
		# not raise the no-op warning there.
		run_main(tmp_path, monkeypatch, "--layout", "ats", "--no-links")
		assert "--no-links" not in capsys.readouterr().out


class TestClassicEscaping:
	"""Every text field the classic layout prints has to go through
	latex_escape. An unescaped '&' aborts pdflatex, which is merely annoying;
	an unescaped '%' is the dangerous one -- it comments out the rest of the
	line, pdflatex still exits 0, and a silently truncated CV deploys."""

	SENTINEL = "R&D 100%"
	ESCAPED = r"R\&D 100\%"
	# phone, address.street, nationality, 3 experience fields, 2 company
	# fields, 4 education fields, 2 award fields, 1 certification field --
	# plus the name, which classic prints twice (the pdftitle metadata and
	# the visible heading).
	INJECTIONS = 17

	@pytest.fixture
	def tex(self, tmp_path, monkeypatch):
		data = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))
		data["personal"]["name"] = self.SENTINEL
		data["personal"]["phone"] = self.SENTINEL
		data["personal"]["nationality"] = self.SENTINEL
		data["personal"]["address"]["street"] = self.SENTINEL
		data["companies"][0]["name"] = self.SENTINEL
		data["companies"][0]["description"] = self.SENTINEL
		# companies[0] (SNB) is_well_known in the sample data, which would
		# otherwise suppress the description this test injects -- see
		# TestWellKnownCompanies. Escaping and the well-known toggle are
		# orthogonal; this test isn't about the toggle.
		data["companies"][0]["is_well_known"] = False
		for field in ("location", "title", "description"):
			data["experience"][0][field] = self.SENTINEL
		for field in ("institution", "location", "degree", "field"):
			data["education"][0][field] = self.SENTINEL
		data["awards"][0]["title"] = self.SENTINEL
		data["awards"][0]["place"] = self.SENTINEL
		data["certifications"][0]["title"] = self.SENTINEL

		specials = tmp_path / "specials.json"
		specials.write_text(json.dumps(data), encoding="utf-8")
		return run_main(
			tmp_path, monkeypatch,
			"--layout", "classic", "--market", "switzerland",
			"--data-dir", str(REPO_ROOT / "data"),
			input_json=specials,
		)

	def test_no_field_reaches_the_document_unescaped(self, tex):
		assert self.SENTINEL not in strip_latex_comments(tex)

	def test_every_field_survives_in_escaped_form(self, tex):
		# Counting, not just presence: a field that lost its text entirely
		# would still pass an "is it escaped" check.
		assert strip_latex_comments(tex).count(self.ESCAPED) == self.INJECTIONS

	@pytest.mark.parametrize("layout", ["ats", "txt"])
	def test_the_other_layouts_were_already_safe(self, tmp_path, monkeypatch, layout):
		data = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))
		data["companies"][0]["name"] = self.SENTINEL
		specials = tmp_path / "specials.json"
		specials.write_text(json.dumps(data), encoding="utf-8")
		tex = run_main(tmp_path, monkeypatch, "--layout", layout, input_json=specials)
		# txt is plain text and needs no escaping at all; ats escapes everything.
		expected = self.SENTINEL if layout == "txt" else self.ESCAPED
		assert expected in tex


class TestPdfMetadata:
	def test_classic_pdftitle_is_braced(self, tmp_path, monkeypatch):
		# "pdftitle={" written flush against the Jinja delimiters would open a
		# Jinja tag instead of a LaTeX group, and the value would reach
		# hyperref unbraced -- fragile, and it silently swallowed the brace.
		tex = run_main(tmp_path, monkeypatch)
		assert "pdftitle={John Doe - CV}," in tex


class TestLayoutRuleOverrides:
	def test_ats_drops_the_photo_even_for_a_photo_market(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch, "--layout", "ats", "--market", "switzerland")
		assert "includegraphics" not in tex
		# The rest of the market's rules still apply.
		assert "Address: " in tex
		assert "Date of birth: " in tex

	def test_strict_does_not_demand_a_photo_the_layout_never_emits(self, tmp_path, monkeypatch, capsys):
		empty_data_dir = tmp_path / "assets"
		empty_data_dir.mkdir()
		run_main(
			tmp_path, monkeypatch,
			"--layout", "ats", "--market", "switzerland",
			"--data-dir", str(empty_data_dir), "--strict",
		)
		assert "Photo not found" not in capsys.readouterr().out


class TestRulesOverride:
	def test_override_flips_a_single_flag_and_leaves_the_rest(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch, "--market", "switzerland", "--rules-override", "show_photo=false")
		assert "includegraphics" not in tex
		assert "Address: " in tex
		assert "Date of birth: " in tex

	def test_override_wins_over_layout_override(self, tmp_path, monkeypatch):
		# ats normally forces show_photo=False (LAYOUT_RULE_OVERRIDES), which is
		# also why --strict doesn't demand a photo file for it (see
		# TestLayoutRuleOverrides). Overriding it back to True should make
		# --strict demand the photo again, proving the override applied after
		# and won over the layout's own override.
		empty_data_dir = tmp_path / "assets"
		empty_data_dir.mkdir()
		with pytest.raises(SystemExit):
			run_main(
				tmp_path, monkeypatch,
				"--layout", "ats", "--market", "switzerland", "--rules-override", "show_photo=true",
				"--data-dir", str(empty_data_dir), "--strict",
			)

	def test_unknown_key_warns_and_is_ignored(self, tmp_path, monkeypatch, capsys):
		tex = run_main(tmp_path, monkeypatch, "--rules-override", "show_unicorn=true")
		assert "Unknown --rules-override key" in capsys.readouterr().out
		assert "includegraphics" not in tex

	def test_unknown_key_strict_fails(self, tmp_path, monkeypatch):
		with pytest.raises(SystemExit):
			run_main(tmp_path, monkeypatch, "--rules-override", "show_unicorn=true", "--strict")

	def test_malformed_pair_warns_and_is_skipped(self, tmp_path, monkeypatch, capsys):
		run_main(tmp_path, monkeypatch, "--rules-override", "show_photo")
		assert "Malformed --rules-override entry" in capsys.readouterr().out

	def test_malformed_value_warns_and_is_skipped(self, tmp_path, monkeypatch, capsys):
		run_main(tmp_path, monkeypatch, "--rules-override", "show_photo=maybe")
		assert "Malformed --rules-override value" in capsys.readouterr().out

	def test_no_override_is_a_no_op(self, tmp_path, monkeypatch):
		with_override = run_main(tmp_path, monkeypatch, "--market", "switzerland", "--rules-override", "")
		without_override = run_main(tmp_path, monkeypatch, "--market", "switzerland")
		assert with_override == without_override


class TestPhotoResolution:
	def test_missing_photo_is_omitted(self, tmp_path, monkeypatch, capsys):
		empty_data_dir = tmp_path / "assets"
		empty_data_dir.mkdir()
		tex = run_main(tmp_path, monkeypatch, "--market", "switzerland", "--data-dir", str(empty_data_dir))
		assert "Photo not found" in capsys.readouterr().out
		assert "includegraphics" not in tex

	def test_missing_photo_ignored_when_market_hides_it(self, tmp_path, monkeypatch, capsys):
		empty_data_dir = tmp_path / "assets"
		empty_data_dir.mkdir()
		run_main(tmp_path, monkeypatch, "--market", "international", "--data-dir", str(empty_data_dir), "--strict")
		assert "Photo not found" not in capsys.readouterr().out

	def test_missing_photo_strict_fails(self, tmp_path, monkeypatch):
		empty_data_dir = tmp_path / "assets"
		empty_data_dir.mkdir()
		with pytest.raises(SystemExit):
			run_main(tmp_path, monkeypatch, "--market", "switzerland", "--data-dir", str(empty_data_dir), "--strict")


class TestCompanyResolution:
	"""experience[].company is a short_name key into companies[]; a dangling
	reference should degrade like a missing photo does, not crash the build."""

	def _with_broken_company(self, tmp_path):
		data = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))
		data["experience"][0]["company"] = "does-not-exist"
		specials = tmp_path / "specials.json"
		specials.write_text(json.dumps(data), encoding="utf-8")
		return specials

	def test_unknown_company_warns_and_falls_back_to_the_short_name(self, tmp_path, monkeypatch, capsys):
		tex = run_main(tmp_path, monkeypatch, input_json=self._with_broken_company(tmp_path))
		assert "Unknown company 'does-not-exist'" in capsys.readouterr().out
		assert "does-not-exist" in tex

	def test_unknown_company_omits_its_url_line(self, tmp_path, monkeypatch):
		# Classic used to print the company URL unconditionally -- a dangling
		# reference resolved to an empty url and rendered a bare, broken
		# \href{ }{ } instead of just dropping the line.
		tex = run_main(tmp_path, monkeypatch, input_json=self._with_broken_company(tmp_path))
		assert "\\href{  }{  }" not in tex

	def test_unknown_company_strict_fails(self, tmp_path, monkeypatch):
		with pytest.raises(SystemExit):
			run_main(tmp_path, monkeypatch, "--strict", input_json=self._with_broken_company(tmp_path))


class TestRoleGrouping:
	"""One employer, several roles. A promotion is not a change of employer,
	so experience[] entries carry a company plus a roles[] list; the older
	flat spelling (title/duration/... directly on the entry) normalizes to a
	one-role group, which is what lets both live in the data indefinitely and
	what lets cv render a cv-data that hasn't adopted roles[] yet.

	The sample's NeuralCore entry is the grouped one -- deliberately, because
	it is the only sample company that is not is_well_known, so its blurb
	prints at the default level and these tests can assert it appears once in
	classic and once per role in ats/txt."""

	COMPANY = "NeuralCore AG"
	BLURB = "machine learning solutions for healthcare"
	TITLES = ("Machine Learning Engineer", "Data Engineer")

	def test_a_flat_entry_normalizes_to_a_single_role(self):
		entry = normalize_experience({
			"company": "acme", "location": "Bern, CH", "title": "Engineer",
			"duration": {"start": "2020-01-01", "end": "2021-01-01"},
			"description": "Did the thing.", "technologies": ["Python"],
		})
		# The role fields move down; company and location stay put, because
		# they describe the employer and not the position.
		assert entry["company"] == "acme"
		assert entry["location"] == "Bern, CH"
		assert entry["roles"] == [{
			"title": "Engineer",
			"duration": {"start": "2020-01-01", "end": "2021-01-01"},
			"description": "Did the thing.", "technologies": ["Python"],
		}]
		assert not any(field in entry for field in ("title", "duration", "description", "technologies"))

	def test_a_grouped_entry_keeps_its_roles_in_the_authored_order(self):
		# Nothing in this pipeline sorts experience, and this change does not
		# start: the file's order is the rendered order.
		entry = normalize_experience({
			"company": "acme",
			"roles": [{"title": "Senior"}, {"title": "Junior"}],
		})
		assert [role["title"] for role in entry["roles"]] == ["Senior", "Junior"]

	def test_the_span_covers_every_role(self):
		span = role_span([
			{"duration": {"start": "2022-03-01", "end": "2023-06-01"}},
			{"duration": {"start": "2021-01-01", "end": "2022-03-01"}},
		])
		assert span == {"start": "2021-01-01", "end": "2023-06-01"}

	def test_an_ongoing_role_makes_the_whole_span_present(self):
		# You have not left a company you still work at, whatever the other
		# roles say -- a blank end dominates the group.
		span = role_span([
			{"duration": {"start": "2022-03-01", "end": ""}},
			{"duration": {"start": "2021-01-01", "end": "2022-03-01"}},
		])
		assert span == {"start": "2021-01-01", "end": ""}

	def test_a_malformed_role_date_does_not_break_the_span(self):
		# Malformed dates already print verbatim everywhere else here (as_date
		# hands them back, parse_duration says "Unknown duration"); a derived
		# span is a reading convenience, not a fact worth failing a build over.
		span = role_span([{"duration": {"start": "someday", "end": "2023-06-01"}}])
		assert span == {"start": "someday", "end": "2023-06-01"}

	def test_flatten_repeats_the_employer_and_keeps_each_role_whole(self):
		flat = flatten_roles([{
			"company": "acme", "location": "Bern, CH",
			"roles": [
				{"title": "Senior", "technologies": ["Rust"]},
				{"title": "Junior", "technologies": ["Python"]},
			],
		}])
		assert [role["company"] for role in flat] == ["acme", "acme"]
		assert [role["location"] for role in flat] == ["Bern, CH", "Bern, CH"]
		# Per-role, not merged: a scanner reading one block must see the stack
		# that block's title was actually held with.
		assert [role["technologies"] for role in flat] == [["Rust"], ["Python"]]

	def test_a_role_location_overrides_the_entrys(self, tmp_path, monkeypatch):
		# A promotion that came with a move. Falls out of flatten_roles rather
		# than being a feature of its own, but it is reachable, so it is tested.
		data = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))
		data["experience"][1]["roles"][1]["location"] = "Lausanne, CH"
		specials = tmp_path / "specials.json"
		specials.write_text(json.dumps(data), encoding="utf-8")
		txt = run_main(tmp_path, monkeypatch, "--layout", "txt", input_json=specials)
		assert f"{self.COMPANY}, Bern, CH" in txt
		assert f"{self.COMPANY}, Lausanne, CH" in txt

	def test_classic_prints_the_employer_once(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch, "--layout", "classic", "--company-descriptions", "max")
		assert tex.count(f"{{\\bf {self.COMPANY}}}") == 1
		assert tex.count(self.BLURB) == 1
		assert tex.count("https://neuralcore.ch") == 2  # \href{ url }{ url }, one line
		for title in self.TITLES:
			assert f"\\hspace*{{\\cvroleindent}}{{\\sl {title} }}" in tex

	def test_classic_shows_the_combined_span_and_total_tenure(self, tmp_path, monkeypatch):
		# The number the two-entry spelling never stated: the reader had to
		# add the roles up themselves. Span and tenure share the header line --
		# on separate lines the tenure read as a wrapped continuation of the
		# span rather than as the employer's total, so this asserts the one
		# line, not the two figures independently.
		tex = run_main(tmp_path, monkeypatch, "--layout", "classic")
		assert (
			f"{{\\bf {self.COMPANY}}}, {{\\sl Bern, CH}} \\hfill "
			"{\\sl January 2021 -- June 2023 (2 years, 5 months)}"
		) in tex

	def test_classic_keeps_each_role_dated_in_its_own_right(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch, "--layout", "classic")
		assert "March 2022 -- June 2023 (1 year, 3 months)" in tex
		assert "January 2021 -- March 2022 (1 year, 2 months)" in tex

	@pytest.mark.parametrize("layout", ["ats", "txt"])
	def test_ats_and_txt_repeat_the_employer_per_role(self, tmp_path, monkeypatch, layout):
		# The opposite of classic, on purpose: a résumé parser keys on a
		# company/title/dates triple on consecutive lines, and a lone header
		# with two roles under it is what makes it attribute both to the first
		# title or drop the earlier one.
		rendered = run_main(tmp_path, monkeypatch, "--layout", layout)
		assert rendered.count(f"{self.COMPANY}, Bern, CH") == 2
		for title in self.TITLES:
			assert title in rendered

	def test_a_grouped_employer_without_a_url_still_gets_its_tenure(self, tmp_path, monkeypatch):
		# The tenure rides on the header line, so a URL-less employer keeps it
		# and simply drops the line below -- no stray empty link, and no line
		# holding nothing but a right-aligned number. No sample or real
		# employer is URL-less, so nothing else would catch that.
		data = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))
		data["companies"][1]["url"] = ""
		specials = tmp_path / "specials.json"
		specials.write_text(json.dumps(data), encoding="utf-8")
		tex = run_main(tmp_path, monkeypatch, "--layout", "classic", input_json=specials)
		assert "January 2021 -- June 2023 (2 years, 5 months)" in tex
		assert "\\href{  }{  }" not in tex
		assert "{\\sl — }" not in tex

	def test_grouped_role_fields_are_escaped(self, tmp_path, monkeypatch):
		# The grouped branch of classic/sections/experience.j2 is new markup,
		# so it needs its own escaping check -- TestClassicEscaping counts
		# injections along the flat path and would not cover it.
		data = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))
		data["experience"][1]["roles"][0]["title"] = TestClassicEscaping.SENTINEL
		data["experience"][1]["roles"][0]["description"] = TestClassicEscaping.SENTINEL
		specials = tmp_path / "specials.json"
		specials.write_text(json.dumps(data), encoding="utf-8")
		tex = strip_latex_comments(run_main(tmp_path, monkeypatch, "--layout", "classic", input_json=specials))
		assert TestClassicEscaping.SENTINEL not in tex
		# Counting, not just presence: a field that lost its text entirely
		# would still pass an "is it escaped" check.
		assert tex.count(TestClassicEscaping.ESCAPED) == 2

	def _with_a_stray_top_level_field(self, tmp_path):
		data = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))
		data["experience"][1]["title"] = "Never Rendered"
		specials = tmp_path / "specials.json"
		specials.write_text(json.dumps(data), encoding="utf-8")
		return specials

	def test_a_stray_top_level_role_field_warns(self, tmp_path, monkeypatch, capsys):
		# Nothing reads it once roles[] is present, so it would vanish in
		# silence -- exactly the class of authoring slip worth naming.
		tex = run_main(tmp_path, monkeypatch, input_json=self._with_a_stray_top_level_field(tmp_path))
		assert "carries both roles[] and top-level title" in capsys.readouterr().out
		assert "Never Rendered" not in tex

	def test_a_stray_top_level_role_field_is_fatal_under_strict(self, tmp_path, monkeypatch):
		with pytest.raises(SystemExit):
			run_main(tmp_path, monkeypatch, "--strict", input_json=self._with_a_stray_top_level_field(tmp_path))


class TestSkillGroups:
	"""Skills are an ordered list of {label, items} groups, so the categories
	and their order live in the data instead of being hardcoded three times,
	once per layout. The legacy three-bucket dict still normalizes to the same
	shape, which is what lets cv render a cv-data that hasn't migrated yet --
	the deploy checks cv out at its default branch, unpinned, so that window
	is real rather than theoretical."""

	LEGACY = {
		"programming": [{"name": "C#", "years": 20}, {"name": "React", "years": 1}],
		"technologies": [{"name": "DevOps", "years": 10}],
		"other": ["Networking", "LaTeX"],
	}

	def _with_skills(self, tmp_path, skills):
		data = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))
		data["skills"] = skills
		specials = tmp_path / "skills.json"
		specials.write_text(json.dumps(data), encoding="utf-8")
		return specials

	def test_the_new_shape_passes_through_in_the_authored_order(self):
		groups = [
			{"label": "Cloud & Infrastructure", "items": ["Azure", "Kubernetes"]},
			{"label": "Programming Languages", "items": ["C#"]},
		]
		# Nothing here sorts skills: the file's order is the rendered order,
		# the same contract experience[] has.
		assert [group["label"] for group in normalize_skills(groups)] == [
			"Cloud & Infrastructure", "Programming Languages",
		]

	def test_an_empty_group_is_dropped_rather_than_rendered_as_a_bare_heading(self):
		# What the old templates' per-bucket {% if %} did, kept.
		groups = [{"label": "Empty", "items": []}, {"label": "Real", "items": ["C#"]}]
		assert [group["label"] for group in normalize_skills(groups)] == ["Real"]

	def test_the_legacy_dict_becomes_three_labelled_groups(self):
		assert [group["label"] for group in normalize_skills(self.LEGACY)] == [
			"Programming Languages", "Technologies", "Other Skills",
		]

	def test_the_legacy_dict_keeps_its_years_in_the_item_text(self):
		# A dataset on the old shape renders what it rendered before, not a
		# silently de-yeared version of itself.
		groups = normalize_skills(self.LEGACY)
		assert groups[0]["items"] == ["C# (20 yrs)", "React (1 yr)"]
		assert groups[2]["items"] == ["Networking", "LaTeX"]

	def test_a_legacy_bucket_that_is_absent_produces_no_group(self):
		assert [group["label"] for group in normalize_skills({"other": ["Networking"]})] == [
			"Other Skills",
		]

	def test_a_skills_block_that_is_neither_shape_yields_nothing(self):
		assert normalize_skills(None) == []
		assert normalize_skills("Python, C#") == []

	@pytest.mark.parametrize("layout", ("classic", "ats", "txt"))
	def test_every_layout_renders_the_label_and_its_items(self, tmp_path, monkeypatch, layout):
		rendered = run_main(
			tmp_path, monkeypatch, "--layout", layout,
			input_json=self._with_skills(tmp_path, [
				{"label": "Data & Events", "items": ["Kafka", "Elasticsearch"]},
			]),
		)
		assert "Data" in rendered and "Events" in rendered
		assert "Kafka" in rendered and "Elasticsearch" in rendered

	@pytest.mark.parametrize("layout", ("classic", "ats", "txt"))
	def test_items_is_read_as_a_key_and_never_as_the_dict_method(self, tmp_path, monkeypatch, layout):
		# Jinja resolves attributes before keys, so `group.items` on a dict is
		# the built-in method, not the list -- it renders as a bound-method
		# repr instead of the skills, in every layout at once. The templates
		# subscript instead; this is the guard that keeps them doing so.
		rendered = run_main(
			tmp_path, monkeypatch, "--layout", layout,
			input_json=self._with_skills(tmp_path, [
				{"label": "Programming Languages", "items": ["Kotlin"]},
			]),
		)
		assert "built-in method" not in rendered
		assert "dict_items" not in rendered
		assert "Kotlin" in rendered

	def test_an_ampersand_in_a_label_is_escaped_for_latex(self, tmp_path, monkeypatch):
		# Domain headings are prose now, so they hit the escaper like any other
		# free text: an unescaped & is a LaTeX alignment character and aborts
		# the pdflatex run.
		tex = run_main(
			tmp_path, monkeypatch,
			input_json=self._with_skills(tmp_path, [
				{"label": "Cloud & Infrastructure", "items": ["Azure"]},
			]),
		)
		assert "Cloud \\& Infrastructure" in tex


class TestWellKnownCompanies:
	"""companies[].is_well_known marks a household-name employer (the
	sample's Swiss National Bank); --company-descriptions decides whether a
	build actually acts on that flag. mid (the default) hides only a
	well-known company's blurb, like NeuralCore's still needs; max shows
	every blurb regardless; min hides every blurb regardless. The flag is
	per-company, not per-role, and only ever touches company.description --
	the role's own description (the "my mission was..." text) always prints.
	Grouping (see TestRoleGrouping) makes that structural rather than merely
	conventional: several roles at one employer share one company node, so
	there is no per-role blurb for the flag to disagree with."""

	SNB_BLURB = "central bank of Switzerland"
	NEURALCORE_BLURB = "machine learning solutions for healthcare"

	@pytest.mark.parametrize("layout", ["classic", "ats", "txt"])
	def test_mid_level_omits_only_the_well_known_blurb(self, tmp_path, monkeypatch, layout):
		# mid is the default -- no --company-descriptions flag needed here.
		tex = run_main(tmp_path, monkeypatch, "--layout", layout)
		assert self.SNB_BLURB not in tex
		assert self.NEURALCORE_BLURB in tex

	@pytest.mark.parametrize("layout", ["classic", "ats", "txt"])
	def test_max_level_shows_every_blurb(self, tmp_path, monkeypatch, layout):
		tex = run_main(tmp_path, monkeypatch, "--layout", layout, "--company-descriptions", "max")
		assert self.SNB_BLURB in tex
		assert self.NEURALCORE_BLURB in tex

	@pytest.mark.parametrize("layout", ["classic", "ats", "txt"])
	def test_min_level_hides_every_blurb(self, tmp_path, monkeypatch, layout):
		tex = run_main(tmp_path, monkeypatch, "--layout", layout, "--company-descriptions", "min")
		assert self.SNB_BLURB not in tex
		assert self.NEURALCORE_BLURB not in tex

	def test_the_roles_own_description_always_prints_regardless_of_level(self, tmp_path, monkeypatch):
		# Only company.description is gated; item.description (this role's own
		# text) is unrelated data and must survive at every level, including min.
		for level in ("min", "mid", "max"):
			tex = run_main(tmp_path, monkeypatch, "--company-descriptions", level)
			assert "modernize the bank" in tex

	def test_missing_flag_defaults_to_printing_the_blurb_at_mid(self, tmp_path, monkeypatch):
		# is_well_known is optional; a company that omits it entirely (as
		# opposed to declaring it false) must not lose its description at the
		# default level -- Jinja's Undefined is falsy, so
		# "not company.get('is_well_known', False)" holds and the omission
		# alone must not read as "well known".
		data = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))
		del data["companies"][0]["is_well_known"]
		specials = tmp_path / "specials.json"
		specials.write_text(json.dumps(data), encoding="utf-8")
		tex = run_main(tmp_path, monkeypatch, input_json=specials)
		assert self.SNB_BLURB in tex

	def test_unknown_level_is_rejected(self, tmp_path, monkeypatch):
		# A closed set of levels: argparse validates it up front rather than
		# warn_or_fail degrading at render time, since there's no sane
		# "unknown level" fallback the way an unknown market has one.
		with pytest.raises(SystemExit):
			run_main(tmp_path, monkeypatch, "--company-descriptions", "nope")


REAL_DATA_DIR = REPO_ROOT.parent / "cv-data"
REAL_DATA = REAL_DATA_DIR / "cv.json"


@pytest.mark.skipif(not REAL_DATA.exists(), reason="cv-data not checked out as a sibling of this checkout")
class TestRealWellKnownCompanies:
	"""TestWellKnownCompanies proves the mechanism on the fictional sample;
	this proves the real data actually uses it -- a company can be flagged
	is_well_known and still leak its blurb if, say, the flag gets flipped back
	or a future template regresses. Runs whenever cv-data sits next to this
	checkout as ../cv-data: true for a local dev workspace, and true for
	cv-data's deploy pipeline, which checks out both repos as siblings under
	$GITHUB_WORKSPACE and runs `make -C cv-repo test` before building anything.
	No pipeline change was needed -- this rides that existing gate, so a
	regression fails `make test` locally (before you'd ever push) exactly the
	same way it fails the deploy. Skips cleanly on cv's own public CI, which
	has no cv-data checkout and shouldn't need the private data to pass."""

	@pytest.fixture
	def companies(self):
		return json.loads(REAL_DATA.read_text(encoding="utf-8"))["companies"]

	@pytest.mark.parametrize("layout", ["classic", "ats", "txt"])
	def test_mid_level_omits_well_known_blurbs(self, tmp_path, monkeypatch, companies, layout):
		# mid is the default -- what every deployed build actually uses today.
		tex = run_main(
			tmp_path, monkeypatch,
			"--layout", layout, "--data-dir", str(REAL_DATA_DIR),
			input_json=REAL_DATA,
		)
		leaked = [
			c["name"] for c in companies
			if c.get("is_well_known") and c.get("description") and c["description"] in tex
		]
		assert not leaked, f"{layout}: blurb leaked into the build for {leaked}"

	def test_max_level_shows_a_well_known_blurb(self, tmp_path, monkeypatch, companies):
		# Proves the override actually reaches the real data, not just the
		# sample: --company-descriptions max must surface a blurb mid hides.
		well_known = next((c for c in companies if c.get("is_well_known") and c.get("description")), None)
		if well_known is None:
			pytest.skip("no well-known company with a description in the real data")
		tex = run_main(
			tmp_path, monkeypatch,
			"--data-dir", str(REAL_DATA_DIR), "--company-descriptions", "max",
			input_json=REAL_DATA,
		)
		assert well_known["description"] in tex

	def test_min_level_hides_every_real_blurb(self, tmp_path, monkeypatch, companies):
		tex = run_main(
			tmp_path, monkeypatch,
			"--data-dir", str(REAL_DATA_DIR), "--company-descriptions", "min",
			input_json=REAL_DATA,
		)
		leaked = [c["name"] for c in companies if c.get("description") and c["description"] in tex]
		assert not leaked, f"blurb leaked at min level for {leaked}"


class TestCommitSha:
	def test_sha_stamped_when_given(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch, "--commit-sha", "abc1234")
		assert "Commit SHA: abc1234" in tex

	def test_sha_omitted_when_absent(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch)
		assert "Commit SHA" not in tex


class TestWarnOrFail:
	def test_strict_exits_with_error(self):
		with pytest.raises(SystemExit) as exc_info:
			warn_or_fail("boom", strict=True, fallback="; ignored")
		assert "❌ boom" in str(exc_info.value)

	def test_non_strict_warns_with_fallback(self, capsys):
		warn_or_fail("boom", strict=False, fallback="; carrying on")
		assert "⚠️ boom; carrying on" in capsys.readouterr().out
