import json
import re
import sys
from pathlib import Path

import pytest

from generate_cv import available_layouts, main, parse_nationality, warn_or_fail

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
		assert rules["default"]["show_nationality"] is False
		assert rules["CH"]["show_nationality"] is True

	def test_every_declared_rule_is_read_by_a_template(self):
		# A flag nobody reads is dead configuration that reads as a feature.
		templates = (REPO_ROOT / "src" / "template").rglob("*.j2")
		rendered_by = "\n".join(t.read_text(encoding="utf-8") for t in templates)
		rules = json.loads((REPO_ROOT / "config" / "market_rules.json").read_text(encoding="utf-8"))
		declared = {flag for market in rules.values() for flag in market}
		assert {flag for flag in declared if flag not in rendered_by} == set()

	def test_ch_market_shows_everything(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch, "--market", "CH")
		photo = REPO_ROOT / "data" / "profile.png"
		assert f"\\includegraphics[width=1in]{{{photo}}}" in tex
		assert photo.is_absolute()
		assert "Date of birth:" in tex
		assert "Address:" in tex
		assert "Nationality:" in tex

	def test_br_market_hides_photo_dob_address(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch, "--market", "BR")
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
		tex = run_main(tmp_path, monkeypatch, "--market", "CH", input_json=specials)
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

		tex = run_main(tmp_path, monkeypatch, "--layout", "ats", "--market", "CH", input_json=minimal_json)
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
		txt = run_main(tmp_path, monkeypatch, "--layout", "txt", "--market", "CH")
		assert "Address: " in txt
		assert "Date of birth: " in txt


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
		tex = run_main(tmp_path, monkeypatch, "--layout", layout, "--market", "CH", "--no-links")
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
			"--layout", "classic", "--market", "CH",
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
		tex = run_main(tmp_path, monkeypatch, "--layout", "ats", "--market", "CH")
		assert "includegraphics" not in tex
		# The rest of the market's rules still apply.
		assert "Address: " in tex
		assert "Date of birth: " in tex

	def test_strict_does_not_demand_a_photo_the_layout_never_emits(self, tmp_path, monkeypatch, capsys):
		empty_data_dir = tmp_path / "assets"
		empty_data_dir.mkdir()
		run_main(
			tmp_path, monkeypatch,
			"--layout", "ats", "--market", "CH",
			"--data-dir", str(empty_data_dir), "--strict",
		)
		assert "Photo not found" not in capsys.readouterr().out


class TestPhotoResolution:
	def test_missing_photo_is_omitted(self, tmp_path, monkeypatch, capsys):
		empty_data_dir = tmp_path / "assets"
		empty_data_dir.mkdir()
		tex = run_main(tmp_path, monkeypatch, "--market", "CH", "--data-dir", str(empty_data_dir))
		assert "Photo not found" in capsys.readouterr().out
		assert "includegraphics" not in tex

	def test_missing_photo_ignored_when_market_hides_it(self, tmp_path, monkeypatch, capsys):
		empty_data_dir = tmp_path / "assets"
		empty_data_dir.mkdir()
		run_main(tmp_path, monkeypatch, "--market", "BR", "--data-dir", str(empty_data_dir), "--strict")
		assert "Photo not found" not in capsys.readouterr().out

	def test_missing_photo_strict_fails(self, tmp_path, monkeypatch):
		empty_data_dir = tmp_path / "assets"
		empty_data_dir.mkdir()
		with pytest.raises(SystemExit):
			run_main(tmp_path, monkeypatch, "--market", "CH", "--data-dir", str(empty_data_dir), "--strict")


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


class TestWellKnownCompanies:
	"""companies[].is_well_known marks a household-name employer (the
	sample's Swiss National Bank); --company-descriptions decides whether a
	build actually acts on that flag. mid (the default) hides only a
	well-known company's blurb, like NeuralCore's still needs; max shows
	every blurb regardless; min hides every blurb regardless. The flag is
	per-company, not per-role, and only ever touches company.description --
	the role's own description (the "my mission was..." text) always prints."""

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
			assert "help modernize the bank" in tex

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
