from generate_cv import parse_address


class TestAddressFormats:
	"""parse_address assembles the address line from a country-specific pattern
	selected by the optional "format" key. Missing fields drop out of the line
	instead of leaving dangling punctuation behind."""

	def test_default_format_is_swiss_ordering(self):
		address = {
			"street": "Musterstrasse",
			"number": "1",
			"postal_code": "8000",
			"city": "Zürich",
			"country": "CH",
		}
		assert parse_address(address) == "Musterstrasse 1, 8000 Zürich, CH"

	def test_missing_format_falls_back_to_swiss(self):
		# Existing data has no "format" key; it must render exactly as before.
		address = {"street": "Musterstrasse", "number": "1", "postal_code": "8000", "city": "Zürich"}
		assert parse_address(address) == "Musterstrasse 1, 8000 Zürich"

	def test_us_format_puts_number_first_and_state_before_zip(self):
		address = {
			"format": "us",
			"number": "1",
			"street": "Musterstrasse",
			"city": "Zürich",
			"state": "ZH",
			"postal_code": "8000",
			"country": "CH",
		}
		assert parse_address(address) == "1 Musterstrasse, Zürich, ZH 8000, CH"

	def test_br_format_uses_city_state_pair(self):
		address = {
			"format": "br",
			"street": "Av. Paulista",
			"number": "1000",
			"city": "São Paulo",
			"state": "SP",
			"postal_code": "01310-100",
			"country": "BR",
		}
		assert parse_address(address) == "Av. Paulista 1000, São Paulo - SP, 01310-100, BR"

	def test_us_without_state_degrades_to_city_zip(self):
		address = {"format": "us", "number": "1", "street": "Musterstrasse", "city": "Zürich", "postal_code": "8000"}
		assert parse_address(address) == "1 Musterstrasse, Zürich, 8000"

	def test_missing_state_in_br_drops_the_dangling_separator(self):
		address = {"format": "br", "street": "Av. Paulista", "number": "1000", "city": "São Paulo"}
		assert parse_address(address) == "Av. Paulista 1000, São Paulo"

	def test_street_alone_still_renders(self):
		assert parse_address({"street": "Musterstrasse"}) == "Musterstrasse"

	def test_unknown_format_falls_back_to_swiss(self):
		address = {"format": "jp", "street": "Musterstrasse", "number": "1", "postal_code": "8000", "city": "Zürich"}
		assert parse_address(address) == "Musterstrasse 1, 8000 Zürich"

	def test_format_key_is_case_insensitive(self):
		address = {"format": "US", "street": "Musterstrasse", "number": "1", "city": "Zürich", "postal_code": "8000"}
		assert parse_address(address) == "1 Musterstrasse, Zürich, 8000"

	def test_non_dict_address_renders_empty(self):
		# The historical failure mode: an address that is a plain string used to
		# render a bare "Address:" label. It must neither crash nor leak text.
		assert parse_address("Musterstrasse 1, 8000 Zürich") == ""
		assert parse_address(None) == ""
