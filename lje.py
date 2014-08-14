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


@click.command()
def version():
    """Print version and exit."""
    print(__version__)


main.add_command(version)


if __name__ == "__main__":
    main()
