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


class TestMarkets:
	def test_default_market_shows_everything(self, tmp_path, monkeypatch):
		tex = run_main(tmp_path, monkeypatch)
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
		assert "includegraphics" in tex

	def test_unknown_market_strict_fails(self, tmp_path, monkeypatch):
		with pytest.raises(SystemExit):
			run_main(tmp_path, monkeypatch, "--market", "XX", "--strict")


class TestPhotoResolution:
	def test_missing_photo_is_omitted(self, tmp_path, monkeypatch, capsys):
		empty_data_dir = tmp_path / "assets"
		empty_data_dir.mkdir()
		tex = run_main(tmp_path, monkeypatch, "--data-dir", str(empty_data_dir))
		assert "Photo not found" in capsys.readouterr().out
		assert "includegraphics" not in tex

	def test_missing_photo_strict_fails(self, tmp_path, monkeypatch):
		empty_data_dir = tmp_path / "assets"
		empty_data_dir.mkdir()
		with pytest.raises(SystemExit):
			run_main(tmp_path, monkeypatch, "--data-dir", str(empty_data_dir), "--strict")


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
