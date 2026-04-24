"""Storage layer: SQLite connection management and schema migrations.

Modules
-------
db          — Database class and shared `db` singleton; use db.connection() for all queries.
migrations/ — Numbered SQL files applied in order by db.init_db().
"""
