import json

import click
from lido import Lido
from web3 import Web3
from web3.providers.auto import load_provider_from_uri

@click.group()
@click.option(
    "--max_multicall",
    type=int,
    required=False,
    help="Batch amount of function calls to fit into one RPC call.",
)
@click.option(
    "--lido_address",
    type=str,
    required=False,
    help="Address of the main contract.",
)
@click.option(
    "--lido_abi_path",
    type=str,
    required=False,
    help="ABI file path for the main contract.",
)
@click.option(
    "--registry_address",
    type=str,
    required=False,
    help="Address of the operator contract.",
)
@click.option(
    "--registry_abi_path",
    type=str,
    required=False,
    help="ABI file path for operators contract.",
)
@click.option(
    "--web3_provider_uri",
    type=str,
    required=True,
    help="Web3 provider uri.",
)
@click.pass_context
def cli(ctx, max_multicall, lido_address, lido_abi_path, registry_address, registry_abi_path, web3_provider_uri):
    """CLI utility to load Node Operators keys from file or network and check for duplicates and invalid signatures."""

    w3 = Web3(load_provider_from_uri(web3_provider_uri))
    if w3.eth.chainId == 5:
        from web3.middleware import geth_poa_middleware
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)

    lido = Lido(
        w3,
        lido_address=lido_address,
        max_multicall=max_multicall,
        lido_abi_path=lido_abi_path,
        registry_address=registry_address,
        registry_abi_path=registry_abi_path)

    operators_data = lido.get_operators_data()
    click.secho("Loaded operators", fg="green")

    data_with_keys = lido.get_operators_keys(operators_data)
    click.secho("Loaded operator keys", fg="green")

    click.secho("-")

    # Passing computed items as context to command functions
    ctx.ensure_object(dict)

    ctx.obj["lido"] = lido
    ctx.obj["operators"] = data_with_keys


@cli.command("validate_network_keys")
@click.pass_context
def validate_network_keys(ctx):
    """Checking node operator keys from network."""

    # Loading variables from context
    lido = ctx.obj["lido"]
    operators = ctx.obj["operators"]

    data_validated_keys = lido.validate_keys_multi(operators)
    click.secho("Done signature validation", fg="green")

    data_found_duplicates = Lido.find_duplicates(data_validated_keys)
    click.secho("Done duplicate checks", fg="green")

    click.secho("-")

    # Handling invalid signatures
    invalid_signatures = []

    for op in data_found_duplicates:
        for key in op["keys"]:
            if not key["valid_signature"]:
                invalid_signatures.append(
                    {
                        "key": key,
                        "op_id": op["id"],
                        "op_name": op["name"],
                        "op_staking_limit": bool(op["stakingLimit"]),
                    }
                )

    if not invalid_signatures:
        click.secho("No invalid signatures found", fg="green")
    else:
        click.secho("Invalid signatures found for keys:", fg="red")
        for item in invalid_signatures:
            click.secho(
                "%s (%s) key #%s - OP Active: %s, Used: %s:"
                % (
                    item["op_name"],
                    item["op_id"],
                    item["key"]["index"],
                    item["op_staking_limit"],
                    item["key"]["used"],
                )
            )
            click.secho(item["key"]["key"].hex(), fg="red")

    click.secho("-")

    # Handling duplicates
    with_duplicates = []

    for op in data_found_duplicates:
        for key in op["keys"]:
            if key["duplicate"]:
                with_duplicates.append(key)

    if not with_duplicates:
        click.secho("No duplicates found", fg="green")
    else:
        click.secho("Duplicates found for keys:", fg="red")
        for item_with_duplicates in with_duplicates:
            click.secho(item_with_duplicates["key"].hex(), fg="red")

            click.secho("Duplicates:")
            for dup in item_with_duplicates["duplicates"]:
                click.secho(
                    "- %s (%s) key #%s - Active: %s, Used: %s"
                    % (
                        dup["op"]["name"],
                        dup["op"]["id"],
                        dup["key"]["index"],
                        bool(dup["op"]["stakingLimit"]),
                        dup["key"]["used"],
                    )
                )

    click.secho("Finished")


@click.option(
    "--file",
    type=str,
    default="input.json",
    help="JSON input file with proposed keys",
)
@cli.command("validate_file_keys")
@click.pass_context
def validate_file_keys(ctx, file):
    """Checking node operator keys from input file."""

    # Loading variables from context
    lido = ctx.obj["lido"]
    operators = ctx.obj["operators"]

    # Load and format JSON file
    input_raw = json.load(open(file))

    # Formatting eth2deposit cli input fields
    input = []
    for item in input_raw:
        item["key"] = bytes.fromhex(item["pubkey"])
        item["depositSignature"] = bytes.fromhex(item["signature"])
        del item["pubkey"]
        del item["signature"]
        input.append(item)

    # Handling invalid signatures
    click.secho("Searching for invalid signatures")
    invalid_signatures = lido.validate_key_list_multi(input)

    if not invalid_signatures:
        click.secho("No invalid signatures found", fg="green")
    else:
        click.secho("Invalid signatures found for keys:", fg="red")
        for key in invalid_signatures:
            click.secho(key["key"].hex(), fg="red")

    click.secho("-")

    # Handling duplicates
    with_duplicates = []
    with click.progressbar(input, label="Searching for duplicates", show_eta=False) as keys:
        for key in keys:
            duplicates_found = Lido.spot_duplicates(operators, key)

            if duplicates_found:
                with_duplicates.append({"key": key["key"], "duplicates": duplicates_found})

    if not with_duplicates:
        click.secho("No duplicates found", fg="green")
    else:
        click.secho("Duplicates found for keys:", fg="red")
        for item_with_duplicates in with_duplicates:
            click.secho(item_with_duplicates["key"].hex(), fg="red")

            click.secho("Duplicate of:")
            for dup in item_with_duplicates["duplicates"]:
                click.secho(
                    "- %s (%s) key #%s - OP Active: %s, Used: %s"
                    % (
                        dup["op"]["name"],
                        dup["op"]["id"],
                        dup["key"]["index"],
                        bool(dup["op"]["stakingLimit"]),
                        dup["key"]["used"],
                    )
                )

    click.secho("Finished")


if __name__ == "__main__":
    cli(obj={})
