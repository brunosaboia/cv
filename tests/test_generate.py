import json
import re
import sys
from pathlib import Path

import pytest

from generate_cv import main, warn_or_fail

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_main(tmp_path, monkeypatch, *extra_args):
	output = tmp_path / "cv.tex"
	argv = [
		"generate_cv.py",
		"--input", str(REPO_ROOT / "data" / "cv.json"),
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

	def test_ch_market_shows_everything(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch, "--market", "CH")
		photo = REPO_ROOT / "data" / "profile.png"
		assert f"\\includegraphics[width=1in]{{{photo}}}" in tex
		assert photo.is_absolute()
		assert "Date of birth:" in tex
		assert "Address:" in tex

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


class TestLanguagesSection:
	"""Spoken languages are a top-level section, not a skills subsection."""

	def test_rendered_from_the_top_level_key(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch)
		assert "English" in tex and "Native" in tex

	def test_headers_order_places_it_after_skills(self):
		headers = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))["headers"]
		assert headers.index("languages") == headers.index("skills") + 1

	def test_data_no_longer_nests_it_under_skills(self):
		data = json.loads((REPO_ROOT / "data" / "cv.json").read_text(encoding="utf-8"))
		assert "languages" in data
		assert "languages" not in data["skills"]


class TestLinks:
	def test_links_are_on_by_default(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch)
		assert "\\href{mailto:john.doe@example.com}" in tex

	def test_no_links_defines_weburl_without_a_link(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch, "--no-links")
		assert "\\newcommand{\\weburl}[1]{{\\urlstyle{same}\\nolinkurl{#1}}}" in tex

	def test_no_links_leaves_no_href(self, tmp_path, monkeypatch):
		# \href is the only thing that emits a PDF link annotation, so one
		# unguarded call anywhere in a section template silently defeats the
		# whole option -- which is exactly how experience.j2 was first missed.
		tex = run_main(tmp_path, monkeypatch, "--market", "CH", "--no-links")
		assert "\\href" not in strip_latex_comments(tex)

	def test_no_links_promotes_labelled_urls_to_text(self, tmp_path, monkeypatch):
		# These four were reachable only through their link text, so dropping
		# the annotation has to surface the address instead of losing it.
		tex = run_main(tmp_path, monkeypatch, "--no-links")
		for url in (
			"https://github.com/johndoe",
			"https://linkedin.com/in/johndoe",
			"https://example.com/assets/pdf/transcripts/ethz-ms.pdf",
			"https://example.com/ai-prize-2022",
		):
			# \weburl inline, \weburlline where it gets a ragged line of its own.
			assert re.search(rf"\\weburl(?:line)?\{{{re.escape(url)}\}}", tex)

	def test_keeps_its_labels_when_linked(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch)
		assert "{GitHub}" in tex
		assert "{Transcript of records}" in tex
		assert "\\weburl" not in tex


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
