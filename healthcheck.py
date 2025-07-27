import sys
import urllib.request

import click


@click.command()
@click.option("--url", help="URL to check", required=True)
def check_health(url: str):
    try:
        response = urllib.request.urlopen(url)
        if response.getcode() == 200:
            print("Healthcheck passed")
            sys.exit(0)
        else:
            print("Healthcheck failed")
            sys.exit(1)
    except Exception as e:
        print(f"Healthcheck failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    check_health()
