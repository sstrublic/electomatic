#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

# The shell that lets us serve our app using Waitress.

import waitress
from elections import app

# When running with HTTP, this is the port on which we listen (such as 1965).
# When running with HTTPS, the port is the one the application listens on (1966)
# with nginx acting as a proxy, listening on a different port (such as 1965).
# The url_scheme is also required.
waitress.serve(app, host='0.0.0.0', port=1986)
# waitress.serve(app, host='0.0.0.0', port=1987, url_scheme='https')
