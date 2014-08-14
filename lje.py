#!/usr/bin/env python3
# coding: utf-8

import sys; sys.dont_write_bytecode = True

import logging

import click


__version__ = "0.1a"


@click.group()
def main():
    """
    Љ is a small and easy static blog generator.
    """
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
        stream=sys.stderr,
    )


editor_option = click.option(
    "-e", "--editor",
    default="env editor",
    help="Editor command.",
    metavar="<editor>",
    show_default=True,
)


@click.command(short_help="Compose new article.")
@editor_option
def compose(editor):
    pass


@click.command(short_help="Edit existing article.")
@editor_option
def edit(editor):
    pass


@click.command(short_help="Publish draft.")
def publish():
    pass


@click.command(short_help="Unpublish article.")
def unpublish():
    pass


@click.group(short_help="Get or set blog option.")
def option():
    pass


@click.command("get", short_help="Get option.")
def get_option():
    pass


@click.command("set", short_help="Set option.")
def set_option():
    pass


@click.command()
def version():
    """Print version and exit."""
    print(__version__)


if __name__ == "__main__":
    option.add_command(get_option)
    option.add_command(set_option)
    main.add_command(compose)
    main.add_command(edit)
    main.add_command(publish)
    main.add_command(unpublish)
    main.add_command(option)
    main.add_command(version)
    main()
