from jquant.cli import build_parser


def test_check_data_supports_prompt_credentials() -> None:
    args = build_parser().parse_args(["check-data", "--prompt-credentials"])

    assert args.command == "check-data"
    assert args.prompt_credentials is True


def test_list_filters_accepts_config() -> None:
    args = build_parser().parse_args(["list-filters", "--config", "example.toml"])

    assert args.command == "list-filters"
    assert args.config == "example.toml"


def test_plot_accepts_input_and_output() -> None:
    args = build_parser().parse_args(
        ["plot", "--input", "outputs/run", "--output", "report.png"]
    )

    assert args.command == "plot"
    assert args.input == "outputs/run"
    assert args.output == "report.png"
