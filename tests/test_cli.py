from jquant.cli import build_parser


def test_check_data_supports_prompt_credentials() -> None:
    args = build_parser().parse_args(["check-data", "--prompt-credentials"])

    assert args.command == "check-data"
    assert args.prompt_credentials is True
