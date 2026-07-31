"""Legacy bot entrypoint.

This file delegates to the current checkout_bot implementation so the
old entrypoint remains runnable.
"""

from checkout_bot import main as bot_main


def main():
    bot_main()


if __name__ == "__main__":
    main()
