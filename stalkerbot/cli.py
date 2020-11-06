import webbrowser
from datetime import datetime
from http.cookiejar import CookieJar

import browser_cookie3
import click
import requests
from tqdm.asyncio import tqdm

from stalkerbot.stalker import Stalker

@click.Group
def cli():
    pass


@cli.command()
@click.option("--silent", is_flag=True, default=False)
@click.option("--no-auth", is_flag=True, default=False)
@click.option("-q", "--query", default="language:python3")
@click.option("-z", "--page-size", default=250)
@click.option("-c", "--continue-from", default=1)
@click.option("-e", "--early-stop", default=0)
@click.option("-s", "--sort", default="followers")
@click.option("-o", "--order", default="desc")
@click.option("-o", "--output", default="data.csv")
@click.option("-w", "--workers", default=4)
@click.option("-t", "--token", default=None, envvar="GITHUB_TOKEN")
@click.option("-u", "--username", default=None, envvar="GITHUB_USERNAME")
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
):
    if not no_auth:
        cookies = browser_cookie3.load(domain_name="github.com")
        if len(cookies) == 0:
            webbrowser.open_new("https://github.com/login")
            click.pause("Sign in then hit any key, ctrl+c or cmd+c to quit")
            cookies = browser_cookie3.load(domain_name="github.com")
        if len(cookies) == 0:
            click.echo("Can't load login info from github")
            raise click.exceptions.Exit(1)
    else:
        cookies = CookieJar()
    click.clear()

    if not username:
        cookie_dict = requests.utils.dict_from_cookiejar(cookies)
        if "dotcom_user" in cookie_dict:
            username = cookie_dict["dotcom_user"]
        else:
            click.echo(
                "Yes I know I'm making you enter this twice... you can set the GITHUB_USERNAME environment variable to skip this"
            )
            username = click.prompt("GitHub Username")

    if not username:
        click.echo("Username is invalid")
        raise click.exceptions.Exit(1)

    if not token:
        click.echo("(You can set the GITHUB_TOKEN environment variable to skip this)")
        token = click.prompt("GitHub Personal Access Token")
    if not token:
        click.echo("Token is invalid")
        raise click.exceptions.Exit(1)

    click.clear()

    if not silent:
        click.echo(f"current query is {query}")
        if click.confirm("enter new query? (y/N)"):
            query = click.prompt("query")

        click.echo(f"results will be sorted by {sort}")
        if click.confirm(
            "change? (y/N)",
        ):
            sort = str(
                click.prompt(
                    "sort value",
                    type=click.Choice(
                        ["followers", "stars", "repositories"], case_sensitive=True
                    ),
                    show_choices=True,
                )
            )

        click.echo(f"results will be in {order} order")
        if click.confirm(
            "change? (y/N)",
        ):
            order = str(
                click.prompt(
                    "direction",
                    type=click.Choice(["asc", "desc"], case_sensitive=True),
                    show_choices=True,
                )
            )

        click.echo(f"Handling {page_size} entries per page (max is 1000)")
        if click.confirm(
            "Change? (y/N)",
        ):
            page_size = int(click.prompt("page size"))

        click.echo(f"Starting from page {continue_from}")
        if click.confirm(
            "change? (y/N)",
        ):
            continue_from = int(click.prompt("page number"))

        click.echo(
            f"Early stop is {'disabled' if early_stop == 0 else f'enabled on page {early_stop}' }"
        )
        if click.confirm(
            "change? (y/N)",
        ):
            early_stop = int(click.prompt("page number, 0 to disable"))

        click.echo(f"stalker will start with {workers} workers")
        if click.confirm(
            "change? (y/N)",
        ):
            workers = int(click.prompt("workers"))

        click.echo(f"output directory is: {output}")
        if click.confirm(
            "change? (y/N)",
        ):
            output = str(click.prompt("filepath"))
        click.clear()
        click.echo(f"started at:  {datetime.now().isoformat()}")
        click.echo(f"user:  {username}")
        click.echo(f"query: {query}\n")
        click.echo(f"starting from: {continue_from}\n")
        click.echo(f"ending early: {f'page {early_stop}' if early_stop else 'no'}\n")

        tq = tqdm(desc="pages", unit="pg", initial=(continue_from - 1))
    else:
        tq = None

    stalker = Stalker(
        cookiejar=cookies,
        query=query,
        username=username,
        token=token,
        sort=sort,
        order=order,
        workers=workers,
        page_size=page_size,
        continue_from=continue_from,
        early_stop=early_stop,
        output_path=output,
        tqcb=tq,
    )
    try:
        stalker.start()
    except click.exceptions.Abort:
        click.echo("exiting...")
        stalker.stop()
    if tq:
        tq.write("")
