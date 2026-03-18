import unittest

from mini_redis.cli.parser import parse_cli_command
from mini_redis.cli.parser import parse_cli_meta_command


class CLIParserTest(unittest.TestCase):
    def test_parse_cli_command_supports_quotes(self) -> None:
        command = parse_cli_command('SET profile "hello mini redis" TAGS user:1 demo')
        self.assertEqual(command["name"], "SET")
        self.assertEqual(
            command["args"],
            ["profile", "hello mini redis", "TAGS", "user:1", "demo"],
        )

    def test_parse_cli_command_ignores_blank_and_comment_lines(self) -> None:
        self.assertIsNone(parse_cli_command("   "))
        self.assertIsNone(parse_cli_command("   # presenter note"))

    def test_parse_cli_meta_command(self) -> None:
        command = parse_cli_meta_command(".demo")
        self.assertEqual(command, {"name": ".demo", "args": []})

    def test_parse_cli_command_raises_on_invalid_quotes(self) -> None:
        with self.assertRaises(ValueError):
            parse_cli_command('SET profile "oops')


if __name__ == "__main__":
    unittest.main()
