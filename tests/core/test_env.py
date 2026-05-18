from fa.core.env import load_dotenv, strip_quotes


class TestStripQuotes:
    def test_no_quotes(self):
        assert strip_quotes("hello") == "hello"

    def test_single_quotes(self):
        assert strip_quotes("'hello'") == "hello"

    def test_double_quotes(self):
        assert strip_quotes('"hello"') == "hello"

    def test_mismatched_quotes(self):
        assert strip_quotes("\"hello'") == "\"hello'"

    def test_single_char(self):
        assert strip_quotes('"') == '"'

    def test_empty_string(self):
        assert strip_quotes("") == ""


class TestLoadDotenv:
    def test_nonexistent_file(self, tmp_path):
        result = load_dotenv(tmp_path / "nope.env")
        assert result == {}

    def test_valid_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('KEY=value\nOTHER="quoted"\n')
        result = load_dotenv(env_file)
        assert result == {"KEY": "value", "OTHER": "quoted"}

    def test_comments_and_blanks(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n\nKEY=val\n")
        result = load_dotenv(env_file)
        assert result == {"KEY": "val"}

    def test_no_equals_sign(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("NOEQUALS\nKEY=val\n")
        result = load_dotenv(env_file)
        assert result == {"KEY": "val"}
