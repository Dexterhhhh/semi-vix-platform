"""Create the application database safely after the embedded server starts."""

import os

import psycopg
from psycopg import sql


database = os.environ["POSTGRES_DB"]
username = os.environ["POSTGRES_USER"]
password = os.environ["POSTGRES_PASSWORD"]

with psycopg.connect(
    host="127.0.0.1",
    port=5432,
    dbname="postgres",
    user=username,
    password=password,
    autocommit=True,
) as connection:
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("ALTER ROLE {} WITH PASSWORD {}").format(
                sql.Identifier(username), sql.Literal(password)
            )
        )
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
        if cursor.fetchone() is None:
            cursor.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(database), sql.Identifier(username)
                )
            )
