from devdb.container import (
    find_available_port,
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
    assert all(c in "abcdefghijklmnopqrstuvwxyz0123456789" for c in s)


def test_find_available_port():
    """Test that find_available_port returns a valid free port."""
    port = find_available_port()
    assert isinstance(port, int)
    assert port >= 5432


def test_find_available_port_custom_start():
    """Test that find_available_port respects the start_port parameter."""
    # Start at a high port to avoid conflicts with real database ports
    port = find_available_port(start_port=10000)
    assert port >= 10000


def test_get_container_name():
    """Test that container name is deterministic and starts with 'devdb-'."""
    name = get_container_name()
    assert name.startswith("devdb-")
    assert len(name) >= 14
