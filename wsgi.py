#!/usr/bin/python3

#   Copyright 2021-2024 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

"""Application entry point."""
from elections import app

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=1986)
