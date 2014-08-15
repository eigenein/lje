#!/usr/bin/env python3
# coding: utf-8

import sys; sys.dont_write_bytecode = True

import collections
import contextlib
import logging
import sqlite3

import click

__version__ = "0.1a"


# Common options, arguments and types.
# ------------------------------------------------------------------------------

class SQLiteType(click.ParamType):
    name = "sqlite"

    def convert(self, value, param, ctx):
        return sqlite3.connect(value)


editor_option = click.option(
    "-e", "--editor",
    default="env editor",
    help="Editor command.",
    metavar="<editor>",
    show_default=True,
)


blog_argument = click.argument("blog", metavar="<blog db>", type=SQLiteType())


# Blog database functions.
# ------------------------------------------------------------------------------

@contextlib.contextmanager
def transaction(blog):
    "Yields a cursor with error handling."
    cursor = blog.cursor()
    try:
        yield cursor
    except:
        blog.rollback()
        raise
    else:
        blog.commit()
    finally:
        cursor.close()


def insert_options(cursor, options):
    "Inserts options into blog options table."
    for name, value in options:
        integer_value = real_value = text_value = blob_value = None
        if isinstance(value, int):
            integer_value = value
        elif isinstance(value, float):
            real_value = value
        elif isinstance(value, str):
            text_value = value
        elif isinstance(value, bytes):
            blob_value = value
        else:
            raise ValueError(value)
        cursor.execute("insert into options values (?, ?, ?, ?, ?)", (
            name, integer_value, real_value, text_value, blob_value))


# Init command.
# ------------------------------------------------------------------------------

@click.command(short_help="Initialize new blog.")
@blog_argument
@click.option("--name", help="Your name.", metavar="<name>", prompt=True, required=True)
@click.option("--email", help="Your email.", metavar="<email>", prompt=True, required=True)
@click.option("--title", help="Blog title.", metavar="<title>", prompt=True, required=True)
@click.option("--url", help="Blog URL.", metavar="<url>", prompt=True, required=True)
def init(blog, name, email, title, url):
    with transaction(blog) as cursor:
        cursor.execute("""create table options (
            name text not null primary key, integer_value integer, real_value real, text_value text, blob_value blob
        )""")
        insert_options(cursor, [
            ("user.name", name),
            ("user.email", email),
            ("blog.title", title),
            ("blog.url", url),
        ])


# Compose command.
# ------------------------------------------------------------------------------

@click.command(short_help="Compose new article.")
@editor_option
def compose(editor):
    pass


# Edit command.
# ------------------------------------------------------------------------------

@click.command(short_help="Edit existing article.")
@editor_option
def edit(editor):
    pass


# Publish command.
# ------------------------------------------------------------------------------

@click.command(short_help="Publish draft.")
def publish():
    pass


# Unpublish command.
# ------------------------------------------------------------------------------

@click.command(short_help="Unpublish article.")
def unpublish():
    pass


# Options command group.
# ------------------------------------------------------------------------------

@click.group(short_help="Get or set blog options.")
def options():
    pass


# Get option command.
# ------------------------------------------------------------------------------

@click.command("get", short_help="Get option.")
def get_option():
    pass


# Set option command.
# ------------------------------------------------------------------------------

@click.command("set", short_help="Set option.")
def set_option():
    pass


# List options command.
# ------------------------------------------------------------------------------

@click.command("list", short_help="List all options.")
def list_options():
    pass


# Version command.
# ------------------------------------------------------------------------------

@click.command()
def version():
    """Print version and exit."""
    print(__version__)


# Entry point.
# ------------------------------------------------------------------------------

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


if __name__ == "__main__":
    options.add_command(get_option)
    options.add_command(set_option)
    options.add_command(list_options)
    main.add_command(init)
    main.add_command(compose)
    main.add_command(edit)
    main.add_command(publish)
    main.add_command(unpublish)
    main.add_command(options)
    main.add_command(version)
    main()
