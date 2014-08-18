#!/usr/bin/env python3
# coding: utf-8

import sys; sys.dont_write_bytecode = True

import collections
import contextlib
import logging
import os
import pathlib
import sqlite3
import tempfile

import click

__version__ = "0.1a"


# Common options, arguments and types.
# ------------------------------------------------------------------------------

class AliasedGroup(click.Group):

    def get_command(self, ctx, name):
        command = click.Group.get_command(self, ctx, name)
        if command is not None:
            return command
        matches = [command for command in self.list_commands(ctx) if command.startswith(name)]
        if not matches:
            return None
        if len(matches) == 1:
            return click.Group.get_command(self, ctx, matches[0])
        ctx.fail("`{0}` is not a command. Did you mean one of these? {1}".format(
            name, ", ".join(matches)))


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


database_argument = click.argument("database", metavar="<database>", type=SQLiteType())


# Database functions.
# ------------------------------------------------------------------------------

class ConnectionWrapper:
    "Database connection wrapper."

    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def cursor(self):
        "Gets database cursor wrapper."

        return CursorWrapper(self.connection.cursor())

    def __exit__(self, exc_type, exc_value, traceback):
        self.connection.close()


class CursorWrapper:
    "Database cursor wrapper class."

    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self

    def initialize_database(self):
        "Initializes empty database."

        self.cursor.execute("""
            create table options (
                name text not null primary key,
                integer_value integer,
                real_value real,
                text_value text,
                blob_value blob
            )""")
        self.cursor.execute("""
            create table posts (
                key text not null primary key,
                timestamp integer not null,
                title text null,
                text_ text not null
            )""")

    def insert_option(self, name, value):
        "Inserts option into options table."

        self.cursor.execute("insert into options values (?, ?, ?, ?, ?)", (name, ) + self.make_option_row(value))

    def insert_post(self):
        pass

    def make_option_row(self, value):
        "Gets option row by value."

        return (self.as_(value, int), self.as_(value, float), self.as_(value, str), self.as_(value, bytes))

    def as_(self, value, type):
        return value if isinstance(value, type) else None

    def __exit__(self, exc_type, exc_value, traceback):
        if not exc_type:
            self.cursor.connection.commit()
        else:
            self.cursor.connection.rollback()
        self.cursor.connection.close()


# Build command.
# ------------------------------------------------------------------------------

@click.command(short_help="Builds blog.")
@database_argument
def build(database):
    pass


# Init command.
# ------------------------------------------------------------------------------

@click.command(short_help="Initialize new blog.")
@database_argument
@click.option("--name", help="Your name.", metavar="<name>", prompt=True, required=True)
@click.option("--email", help="Your email.", metavar="<email>", prompt=True, required=True)
@click.option("--title", help="Blog title.", metavar="<title>", prompt=True, required=True)
@click.option("--url", help="Blog URL.", metavar="<url>", prompt=True, required=True)
def init(database, name, email, title, url):
    with ConnectionWrapper(database) as connection, connection.cursor() as cursor:
        cursor.initialize_database()
        cursor.insert_option("user.name", name)
        cursor.insert_option("user.email", email)
        cursor.insert_option("blog.title", title)
        cursor.insert_option("blog.url", url)


# Compose command.
# ------------------------------------------------------------------------------

@click.command(short_help="Compose new article.")
@editor_option
@click.option("--key", default=None, help="Post key. Example: my-first-post.", metavar="<key>")
@click.option("--title", help="Post title.", metavar="<title>", prompt=True, required=True)
@click.option("--tag", help="Post tag.", metavar="<tag>", multiple=True)
def compose(editor, key, title, tag):
    key = key or urlify(title)
    fd, path = tempfile.mkstemp(prefix="lje-{}-".format(key), suffix=".txt", text=True)
    os.system("{0} \"{1}\"".format(editor, path))
    try:
        with os.fdopen(fd, "rt", encoding="utf-8") as fp:
            text = fp.read()
    finally:
        pathlib.Path(path).unlink()


def urlify(title):
    "Gets post key by title."
    return title.lower().replace(" ", "-")


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

@click.group(cls=AliasedGroup)
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
    main.add_command(build)
    main.add_command(init)
    main.add_command(compose)
    main.add_command(edit)
    main.add_command(publish)
    main.add_command(unpublish)
    main.add_command(options)
    main.add_command(version)
    main()
