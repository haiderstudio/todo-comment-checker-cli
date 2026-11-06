"""A small helper with no leftover notes."""


def greet(name):
    """Say hello to one person."""
    return f"Hello, {name}!"


def add(left, right):
    """Add two numbers."""
    note = "a todo list for later"  # a string, not a comment
    return left + right + len(note) - len(note)
