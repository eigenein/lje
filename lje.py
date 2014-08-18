#!/usr/bin/env python3
# coding: utf-8

import sys; sys.dont_write_bytecode = True

import collections
import contextlib
import datetime
import itertools
import logging
import os
import pathlib
import sqlite3
import tempfile

import click
import requests

__version__ = "0.1a"


# Database functions.
# ------------------------------------------------------------------------------

Post = collections.namedtuple("Post", ["key", "timestamp", "title", "text"])


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

    def upsert_option(self, name, value):
        "Inserts or updates option."
        logging.info("Setting option `%s` to `%s`.", name, value)
        row = self.make_option_row(name, value)
        try:
            self.cursor.execute("""
                insert into options (integer_value, real_value, text_value, blob_value, name)
                values (?, ?, ?, ?, ?)
            """, row)
        except sqlite3.IntegrityError:
            self.cursor.execute("""
                update options
                set integer_value = ?, real_value = ?, text_value = ?, blob_value = ? where name = ?
            """, row)

    def make_option_row(self, name, value):
        "Gets option row by value."
        return (as_(value, int), as_(value, float), as_(value, str), as_(value, bytes), name)

    def insert_post(self, post):
        "Insert new post."
        self.cursor.execute(
            "insert into posts values (?, ?, ?, ?)", (
            post.key, post.timestamp, post.title, post.text,
        ))

    def update_post(self, post):
        "Updates existing post."
        self.cursor.execute(
            "update posts set timestamp = ?, title = ?, text = ? where key = ?", (
            post.timestamp, post.title, post.text, post.key,
        ))

    def upsert_post(self, post):
        "Inserts new post or updates if exists."
        try:
            self.insert_post(post)
        except sqlite3.IntegrityError:
            self.update_post(post)

    def __exit__(self, exc_type, exc_value, traceback):
        if not exc_type:
            self.cursor.connection.commit()
        else:
            self.cursor.connection.rollback()
        self.cursor.connection.close()


# Utilities.
# ------------------------------------------------------------------------------

def as_(value, type):
    return value if isinstance(value, type) else None


def urlify(title):
    "Gets post key by title."
    return title.lower().replace(" ", "-")


def get_text(editor, key, text=""):
    "Execute editor and read user input."

    fd, path = tempfile.mkstemp(prefix="lje-{}-".format(key), suffix=".txt", text=True)
    try:
        with os.fdopen(fd, "wt", encoding="utf-8") as fp:
            fp.write(text)
        os.system("{0} \"{1}\"".format(editor, path))
        with open(path, "rt", encoding="utf-8") as fp:
            return fp.read()
    finally:
        pathlib.Path(path).unlink()


def get_timestamp():
    "Gets UTC timestamp."
    return int((datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds())


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

    def __init__(self, exists):
        super()
        self.exists = exists

    def convert(self, value, param, ctx):
        if pathlib.Path(value).exists():
            if not self.exists:
                raise click.UsageError("database already exists")
        else:
            if self.exists:
                raise click.UsageError("existing database is expected")
        return sqlite3.connect(value)


editor_option = click.option(
    "-e", "--editor",
    default="env editor",
    help="Editor command.",
    metavar="<editor>",
    show_default=True,
)


existing_database_argument = click.argument("database", metavar="<database>", type=SQLiteType(exists=True))
new_database_argument = click.argument("database", metavar="<database>", type=SQLiteType(exists=False))


# Build command.
# ------------------------------------------------------------------------------

@click.command(short_help="Build blog.")
@existing_database_argument
@click.argument("path", metavar="<path>")
def build(database, path):
    path = pathlib.Path(path)
    path.mkdir(parents=True)

    with ConnectionWrapper(database) as connection, connection.cursor() as cursor:
        BlogBuilder(cursor, path).build()


class BlogBuilder:
    "Builds blog."

    def __init__(self, cursor, path):
        self.cursor = cursor
        self.path = path

    def build(self):
        "Builds entire blog."
        pass

    def build_post(self, post):
        pass

    def build_index(self):
        pass

    def get_post_groups(self, post):
        "Gets post groups."

        dt = datetime.datetime.utcfromtimestamp(post.timestamp)
        yield []
        yield [dt.strftime("%Y")]
        yield [dt.strftime("%Y", dt.strftime("%m")]


# Init command.
# ------------------------------------------------------------------------------

@click.command(short_help="Initialize new blog.")
@new_database_argument
@click.option("--name", help="Your name.", metavar="<name>", prompt=True, required=True)
@click.option("--email", help="Your email.", metavar="<email>", prompt=True, required=True)
@click.option("--title", help="Blog title.", metavar="<title>", prompt=True, required=True)
@click.option("--url", help="Blog URL.", metavar="<url>", prompt=True, required=True)
def init(database, name, email, title, url):
    with ConnectionWrapper(database) as connection, connection.cursor() as cursor:
        cursor.initialize_database()
        cursor.upsert_option("author.email", email)
        cursor.upsert_option("author.name", name)
        cursor.upsert_option("blog.title", title)
        cursor.upsert_option("blog.url", url)


# Compose command.
# ------------------------------------------------------------------------------

@click.command(short_help="Compose new post.")
@existing_database_argument
@editor_option
@click.option("--key", default=None, help="Post key. Example: my-first-post.", metavar="<key>")
@click.option("--title", help="Post title.", metavar="<title>", prompt=True, required=True)
@click.option("--tag", help="Post tag.", metavar="<tag>", multiple=True)
def compose(database, editor, key, title, tag):
    key = key or urlify(title)
    text = get_text(editor, key)
    with ConnectionWrapper(database) as connection, connection.cursor() as cursor:
        cursor.insert_post(Post(key, get_timestamp(), title, text))


# Edit command.
# ------------------------------------------------------------------------------

@click.command(short_help="Edit existing post.")
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

@click.command(short_help="Unpublish post.")
def unpublish():
    pass

# List posts command.
# ------------------------------------------------------------------------------

@click.command("list", short_help="List posts.")
def list_posts():
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


# Import command group.
# ------------------------------------------------------------------------------

@click.group("import", short_help="Import blog.")
def import_():
    """
    Imports another source into a new Љ blog.
    """
    pass


# Import from Tumblr.
# ------------------------------------------------------------------------------

@click.command("tumblr", short_help="Import from tumblr.")
@new_database_argument
@click.argument("hostname", metavar="<hostname>")
def import_tumblr(database, hostname):
    """
    Imports blog from Tumblr.

    At the moment text posts are imported only.

    \b
    Example:
    \b
        lje.py import tumblr myblog.db eigenein.tumblr.com
    """

    session = requests.Session()
    imported_posts = 0

    with ConnectionWrapper(database) as connection, connection.cursor() as cursor:
        cursor.initialize_database()

        response = tumblr_get(session, "info", hostname)

        cursor.upsert_option("author.name", response["blog"]["name"])
        cursor.upsert_option("blog.title", response["blog"]["title"])
        cursor.upsert_option("blog.url", response["blog"]["url"])

        for offset in itertools.count(0, 20):
            response = tumblr_get(session, "posts/text", hostname, filter="raw", offset=offset, limit=20)
            if offset >= response["total_posts"]:
                break
            for post in response["posts"]:
                cursor.upsert_post(Post(post["slug"], post["timestamp"], post["title"], post["body"]))
                imported_posts += 1
                logging.info("Imported: %s.", post["slug"])

    logging.info("Imported posts: %d.", imported_posts)


def tumblr_get(session, method, hostname, **params):
    "Makes request to Tumblr API."

    params["api_key"] = "x4OpEVw3OfxdUXA46aCXh3M308SMRKCA6LklBnSzMNvKOCXMFD"
    url = "http://api.tumblr.com/v2/blog/{}/{}".format(hostname, method)
    response = session.get(url, params=params)
    response.raise_for_status()
    response = response.json()
    return response["response"]


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
    logging.basicConfig(format="%(message)s", level=logging.INFO, stream=sys.stderr)


if __name__ == "__main__":
    options.add_command(get_option)
    options.add_command(set_option)
    options.add_command(list_options)
    import_.add_command(import_tumblr)
    main.add_command(options)
    main.add_command(import_)
    main.add_command(build)
    main.add_command(init)
    main.add_command(compose)
    main.add_command(edit)
    main.add_command(publish)
    main.add_command(unpublish)
    main.add_command(list_posts)
    main.add_command(version)
    main()
