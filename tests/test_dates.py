import pytest

from generate_cv import as_date, parse_duration


class TestParseDuration:
	def test_exact_years(self):
		assert parse_duration("2020-01-15", "2022-01-15") == "2 years"

	def test_years_and_months(self):
		assert parse_duration("2020-01-15", "2022-03-20") == "2 years, 2 months"

	def test_day_underflow_drops_a_month(self):
		assert parse_duration("2020-01-15", "2020-03-10") == "1 month"

	def test_singular_forms(self):
		assert parse_duration("2020-01-01", "2021-02-05") == "1 year, 1 month"

	def test_same_date(self):
		assert parse_duration("2020-01-01", "2020-01-01") == "less than a month"

	def test_end_before_start_clamps_to_zero(self):
		assert parse_duration("2020-06-01", "2020-01-01") == "less than a month"

	def test_ongoing_role_uses_today(self):
		result = parse_duration("2020-01-01", "")
		assert result != "Unknown duration"
		assert "year" in result

	def test_garbage_input(self):
		assert parse_duration("not-a-date", "2020-01-01") == "Unknown duration"


class TestAsDate:
	def test_format_key_mapping(self):
		assert as_date("2023-06-01", "MMMM yyyy") == "June 2023"

	def test_raw_strftime_format_passthrough(self):
		assert as_date("2023-06-01", "%d.%m.%Y") == "01.06.2023"

	def test_blank_means_present(self):
		assert as_date("") == "Present"

	def test_blank_without_present_fallback(self):
		assert as_date("", consider_present_for_blank=False) == ""

	def test_unparseable_input_returned_as_is(self):
		assert as_date("junk") == "junk"
