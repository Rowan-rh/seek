"""CLI parser and capabilities contract tests."""

import argparse
import unittest
from unittest.mock import patch

from seek_cli.cli import _build_parser
from seek_cli.commands import capabilities


def _subparsers(parser):
    return next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))


def _parser_commands(parser):
    result = {}
    for name, command_parser in _subparsers(parser).choices.items():
        children = [action for action in command_parser._actions if isinstance(action, argparse._SubParsersAction)]
        if children:
            result[name] = {sub_name: sub_parser for sub_name, sub_parser in children[0].choices.items()}
        else:
            result[name] = command_parser
    return result


def _argument_names(parser):
    return {
        action.option_strings[0] if action.option_strings else action.dest
        for action in parser._actions
        # 排除结构性 dest：全局 --format、命令路由以及嵌套子命令组（如 db conn）
        if action.dest not in ("help", "command", "subcommand", "conn_subcommand", "func", "format")
    }


class CapabilitiesContractTest(unittest.TestCase):
    def test_capabilities_match_parser_command_and_argument_sets(self):
        with patch.object(capabilities.chain_engine, "list_chains", return_value=[]):
            data = capabilities.cmd_capabilities(None)["data"]
        parser_commands = _parser_commands(_build_parser())
        self.assertEqual(set(parser_commands), set(data["commands"]))
        for command, parser_or_subcommands in parser_commands.items():
            definition = data["commands"][command]
            if isinstance(parser_or_subcommands, dict):
                declared = {item["name"]: item for item in definition["subcommands"]}
                self.assertEqual(set(parser_or_subcommands), set(declared), command)
                for subcommand, parser in parser_or_subcommands.items():
                    actual = _argument_names(parser)
                    advertised = {arg["name"] for arg in declared[subcommand].get("args", [])} - {"--format", "--command"}
                    self.assertEqual(actual, advertised, f"{command} {subcommand}")
            else:
                actual = _argument_names(parser_or_subcommands)
                advertised = {arg["name"] for arg in definition.get("args", [])} - {"--format"}
                self.assertEqual(actual, advertised, command)


if __name__ == "__main__":
    unittest.main()
