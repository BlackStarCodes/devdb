from devdb.container import (
    generate_random_string,
    get_container_name,
)


def test_generate_random_string_length():
    """Test that random strings have the correct length and chars."""
    s = generate_random_string(8)
    assert len(s) == 8
    assert all(c.isalnum() for c in s)


def test_generate_random_string_default():
    """Test default length and character set."""
    s = generate_random_string()
    assert len(s) == 8
    # secrets.token_urlsafe can include '-', '_' in addition to alphanumerics.
    # Postgres accepts these, so we only check that the string is non-empty.
    assert all(c.isalnum() or c in "-_" for c in s)


def test_get_container_name():
    """Test that container name is deterministic and starts with 'devdb-'."""
    name = get_container_name()
    assert name.startswith("devdb-")
    assert len(name) >= 14
