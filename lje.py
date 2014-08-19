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
# import jinja2
# import markdown
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

        self.cursor.execute("""create table options (
            name text not null primary key, integer_value integer, real_value real, text_value text, blob_value blob)""")
        # TODO: draft, type
        self.cursor.execute("""create table posts (
            key text not null primary key, timestamp integer not null, title text null, text text not null)""")
        self.cursor.execute("create index ix_posts_timestamp on posts (timestamp)")
        # Insert default option values.
        self.upsert_option("author.email", None)
        self.upsert_option("author.name", None)
        self.upsert_option("blog.page_size", 10)
        self.upsert_option("blog.title", None)
        self.upsert_option("blog.url", None)

    def upsert_option(self, name, value):
        "Inserts or updates option."
        logging.info("Setting option `%s` to `%s`.", name, value)
        option_row = self.make_option_row(name, value)
        try:
            self.cursor.execute("""
                insert into options (integer_value, real_value, text_value, blob_value, name)
                values (?, ?, ?, ?, ?)
            """, option_row)
        except sqlite3.IntegrityError:
            self.cursor.execute("""
                update options
                set integer_value = ?, real_value = ?, text_value = ?, blob_value = ? where name = ?
            """, option_row)

    def make_option_row(self, name, value):
        "Gets option row by value."
        return (as_(value, int), as_(value, float), as_(value, str), as_(value, bytes), name)

    def get_option(self, name):
        "Gets option value."
        self.cursor.execute("""
            select coalesce(integer_value, real_value, text_value, blob_value)
            from options
            where name = ?
        """, (name, ))
        row = self.cursor.fetchone()
        return row[0]

    def insert_post(self, post):
        "Insert new post."
        self.cursor.execute(
            "insert into posts values (?, ?, ?, ?)",
            (post.key, post.timestamp, post.title, post.text),
        )

    def update_post(self, post):
        "Updates existing post."
        self.cursor.execute(
            "update posts set timestamp = ?, title = ?, text = ? where key = ?",
            (post.timestamp, post.title, post.text, post.key),
        )

    def upsert_post(self, post):
        "Inserts new post or updates if exists."
        try:
            self.insert_post(post)
        except sqlite3.IntegrityError:
            self.update_post(post)

    def get_posts(self):
        "Gets all posts."
        self.cursor.execute("""
            select key, timestamp, title, text from posts
            order by timestamp desc
        """)
        return [Post(*row) for row in self.cursor.fetchall()]

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


def paginate(items, page_size):
    "Splits items into list of pages."
    return [items[i:(i + page_size)] for i in range(0, len(items), page_size)]


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


class CommonOptions:
    "Common command options."

    editor = click.option(
        "-e", "--editor",
        default="env editor",
        help="Editor command.",
        metavar="<editor>",
        show_default=True,
    )

    key = click.option(
        "--key",
        default=None,
        help="Post key. Example: my-first-post.",
        metavar="<key>",
    )


class CommonArguments:
    "Common command arguments."

    existing_database = click.argument("database", metavar="<database>", type=SQLiteType(exists=True))
    new_database = click.argument("database", metavar="<database>", type=SQLiteType(exists=False))


# Build command.
# ------------------------------------------------------------------------------

@click.command(short_help="Build blog.")
@CommonArguments.existing_database
@click.argument("path", metavar="<path>")
def build(database, path):
    with ConnectionWrapper(database) as connection, connection.cursor() as cursor:
        BlogBuilder(cursor, pathlib.Path(path)).build()


class BlogBuilder:
    "Builds blog."

    def __init__(self, cursor, path):
        self.cursor = cursor
        self.path = path

    def build(self):
        "Build blog."

        self.initialize_index()
        self.page_size = self.cursor.get_option("blog.page_size")
        self.build_index(self.index, self.path)
        self.build_posts()

    def initialize_index(self):
        logging.info("Initializing index…")
        self.index = Index()
        posts = self.cursor.get_posts()
        for post in posts:
            self.index.append(post)

    def build_index(self, entry, path):
        logging.info("Building index pages in `%s`…", path)
        # Build pages at the current level.
        pages = paginate(entry.posts, self.page_size)
        for page, posts in enumerate(pages, 1):
            page_path = path / str(page) if page != 1 else path
            self.build_index_page(page_path / "index.html", posts)
        # Recursively build child index pages.
        for segment, child in entry.children.items():
            self.build_index(child, path / str(segment))

    def build_index_page(self, path, posts):
        logging.info("Building index page `%s`…", path)
        pass  # TODO

    def build_posts(self):
        "Builds single post pages."

        for post in self.index.posts:
            self.build_post_page(post)

    def build_post_page(self, post):
        "Builds post page."

        path = self.path / post.key / "index.html"
        logging.info("Building post page `%s`…", path)
        pass  # TODO


class Index:
    "Pages index."

    def __init__(self):
        self.posts = []
        self.children = collections.defaultdict(Index)

    def append(self, post):
        "Appends post to index."
        for key in self.get_keys(post):
            entry = self
            for segment in key:
                entry = entry.children[segment]
            entry.posts.append(post)

    def get_keys(self, post):
        timestamp = datetime.datetime.utcfromtimestamp(post.timestamp)
        yield [timestamp.strftime("%Y")]
        yield [timestamp.strftime("%Y"), timestamp.strftime("%m")]
        yield []


# Init command.
# ------------------------------------------------------------------------------

@click.command(short_help="Initialize new blog.")
@CommonArguments.new_database
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
@CommonArguments.existing_database
@CommonOptions.editor
@CommonOptions.key
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
@CommonOptions.editor
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
@CommonArguments.new_database
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
