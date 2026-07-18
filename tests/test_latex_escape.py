import pytest

from generate_cv import latex_escape


@pytest.mark.parametrize(
	("raw", "escaped"),
	[
		("#", r"\#"),
		("$", r"\$"),
		("%", r"\%"),
		("&", r"\&"),
		("_", r"\_"),
		("{", r"\{"),
		("}", r"\}"),
		("^", r"\textasciicircum{}"),
		("~", r"\textasciitilde{}"),
		("\\", r"\textbackslash{}"),
	],
)
def test_special_characters(raw, escaped):
	assert latex_escape(raw) == escaped


def test_plain_text_untouched():
	assert latex_escape("Zürich, Switzerland") == "Zürich, Switzerland"


def test_non_string_passthrough():
	assert latex_escape(42) == 42
	assert latex_escape(None) is None


def test_single_pass_no_double_escaping():
	# The backslash introduced by escaping '%' must not itself be re-escaped,
	# and a literal backslash in the input becomes \textbackslash{} whose
	# braces are not escaped either.
	assert latex_escape("100% \\ done") == r"100\% \textbackslash{} done"


def test_mixed_text():
	assert latex_escape("C&A_shop") == r"C\&A\_shop"
