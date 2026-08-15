import typer

app = typer.Typer(help="DevDB - Instant Isolated Postgres Test Databases")


@app.callback()
def main():
    """DevDB main entry point."""


if __name__ == "__main__":
    app()
