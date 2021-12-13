import webbrowser
from datetime import datetime
from http.cookiejar import CookieJar

import click
import requests
from tqdm.asyncio import tqdm
import os
from stalkerbot.stalker import Stalker
import pickle


@click.Group
def cli():
    pass


@cli.command()
@click.option("--silent", is_flag=True, default=False)
@click.option("--no-auth", is_flag=True, default=False)
@click.option("-q", "--query", default="language:python3")
@click.option("-z", "--page-size", default=250)
@click.option("-c", "--continue-from", default=None)
@click.option("-e", "--early-stop", default=0)
@click.option("-s", "--sort", default="followers")
@click.option("-o", "--order", default="desc")
@click.option("-o", "--output", default="data/users.csv")
@click.option("-w", "--workers", default=4)
@click.option("-t", "--token", default=None, envvar="GITHUB_TOKEN")
@click.option("-u", "--username", default=None, envvar="GITHUB_USERNAME")
@click.option("-o", "--org", default=False, is_flag=True)
def start(
    query,
    page_size,
    continue_from,
    early_stop,
    sort,
    order,
    output,
    workers,
    token,
    username,
    silent,
    no_auth,
    org,
):
    click.clear()

    if not token:
        click.echo("(You can set the GITHUB_TOKEN environment variable to skip this)")
        token = click.prompt("GitHub Personal Access Token")
    if not token:
        click.echo("Token is invalid")
        raise click.exceptions.Exit(1)

    click.clear()

    state = None

    if os.path.exists(".state"):
        if click.confirm("Continue from last saved state? (Y/n)"):
            with open(".state", "rb") as fp:
                state = pickle.load(fp)
                continue_from = state.continue_from
                query = state.query
    if not silent:
        if not state:
            click.echo(f"current query is {query}")
            if click.confirm("enter new query? (y/N)"):
                query = click.prompt("query")

            click.echo(f"continue from {continue_from}")
            if click.confirm(
                "change? (y/N)",
            ):
                continue_from = int(click.prompt("page number"))

        click.echo(f"stopping after adding {early_stop}? (0 runs until completion)")
        if click.confirm(
            "change? (y/N)",
        ):
            early_stop = int(click.prompt("number of entries"))

        click.echo(f"output directory is: {output}")
        if click.confirm(
            "change? (y/N)",
        ):
            output = str(click.prompt("filepath"))
    if org:
        query = "type:org " + query
    if not silent:
        click.clear()
        click.echo(f"started at:  {datetime.now().isoformat()}")
        click.echo(f"user:  {username}")
        click.echo(f"query: {query}\n")
        click.echo(f"starting from: {continue_from}\n")
        click.echo(
            f"ending early: {f'minimum {early_stop} entries' if early_stop else 'no'}\n"
        )
    stalker = Stalker(
        query=query,
        token=token,
        continue_from=continue_from,
        output_path=output,
        silent=silent,
        state=state,
        early_stop=early_stop,
        org_flag=org,
    )
    try:
        stalker.start()
    except click.exceptions.Abort:
        click.echo("exiting...")
        stalker.stop()
    if not silent:
        tq = tqdm()
        tq.write(f"saved state to .state")
    else:
        print(f"saved state to .state")
