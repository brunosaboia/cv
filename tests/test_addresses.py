from generate_cv import parse_address


class TestAddressFormats:
	"""parse_address assembles the address line from a country-specific pattern
	selected by the optional "format" key. Missing fields drop out of the line
	instead of leaving dangling punctuation behind."""

	def test_default_format_is_swiss_ordering(self):
		address = {
			"street": "Aeschengraben",
			"number": "17",
			"postal_code": "4051",
			"city": "Basel",
			"country": "CH",
		}
		assert parse_address(address) == "Aeschengraben 17, 4051 Basel, CH"

	def test_missing_format_falls_back_to_swiss(self):
		# Existing data has no "format" key; it must render exactly as before.
		address = {"street": "Aeschengraben", "number": "17", "postal_code": "4051", "city": "Basel"}
		assert parse_address(address) == "Aeschengraben 17, 4051 Basel"

	def test_us_format_puts_number_first_and_state_before_zip(self):
		address = {
			"format": "us",
			"number": "17",
			"street": "Aeschengraben",
			"city": "Basel",
			"state": "BS",
			"postal_code": "4051",
			"country": "CH",
		}
		assert parse_address(address) == "17 Aeschengraben, Basel, BS 4051, CH"

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
		address = {"format": "us", "number": "17", "street": "Aeschengraben", "city": "Basel", "postal_code": "4051"}
		assert parse_address(address) == "17 Aeschengraben, Basel, 4051"

	def test_missing_state_in_br_drops_the_dangling_separator(self):
		address = {"format": "br", "street": "Av. Paulista", "number": "1000", "city": "São Paulo"}
		assert parse_address(address) == "Av. Paulista 1000, São Paulo"

	def test_street_alone_still_renders(self):
		assert parse_address({"street": "Aeschengraben"}) == "Aeschengraben"

	def test_unknown_format_falls_back_to_swiss(self):
		address = {"format": "jp", "street": "Aeschengraben", "number": "17", "postal_code": "4051", "city": "Basel"}
		assert parse_address(address) == "Aeschengraben 17, 4051 Basel"

	def test_format_key_is_case_insensitive(self):
		address = {"format": "US", "street": "Aeschengraben", "number": "17", "city": "Basel", "postal_code": "4051"}
		assert parse_address(address) == "17 Aeschengraben, Basel, 4051"

	def test_non_dict_address_renders_empty(self):
		# The historical failure mode: an address that is a plain string used to
		# render a bare "Address:" label. It must neither crash nor leak text.
		assert parse_address("Aeschengraben 17, 4051 Basel") == ""
		assert parse_address(None) == ""
