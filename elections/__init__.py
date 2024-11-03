#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

"""Initialize app."""
import os, sys
from datetime import datetime
import traceback

from flask import Flask
from flask_login import LoginManager
from werkzeug.serving import is_running_from_reloader

# Authorized users.
USERTYPES = ["Public", "Admin"]

# Users have a unique ID created from their club ID and username.  This dict contains all users for all clubs, for login purposes.
# user IDs have to be unique - but we want users with the same name for different Club IDs.
# Each login gets its own user oject within the namespace for that user.
# The objects are periodically aged and removed upon expiry.
# The session holds the unique ID for that user oject within the suer namespace.
ALLUSERS = {}

# Track all request sources for public vote management (when voting by public-key/QRcode).
# Each event entry gets a unique key for use when logging a people's choice vote.  If the public key
# is used, then that vote is entered and associated with the source on a timer to prevent refreshes
# from automatically logging more votes.
ALLSOURCES = {}

# Users are organized by club ID.

# Dicts for users:

# Users (public access)
USERS = {}

# Admins (everything)
ADMINS = {}

# The global event config instance.
EVENTCONFIG = None

# Debug flags.
DB_DEBUG = False
DB_DEBUG_OUTPUT = False
CONSOLE_ECHO = False

# Read-only status.
READ_ONLY = False


# Get the remote address from the 'access route' from the request,
# which allows us to untangle any proxy addressing.
def getRemoteAddr(request):
    access_route = request.access_route

    if len(access_route) == 0:
        remote_addr = '%s' % request.remote_addr
    else:
        remote_addr = '%s' % access_route[-1]

    return remote_addr


# Define the suffix for a place.
def placeSuffix(place):
    if place % 10 == 1 and place != 11:
        return 'st'
    elif place % 10 == 2 and place != 12:
        return 'nd'
    elif place % 10 == 3 and place != 13:
        return 'rd'
    else:
        return 'th'


"""Construct the core app object."""
app = Flask(__name__, instance_relative_config=False)

""" Load the Application Configuration """
app.config.from_object('config.Config')

# Get this once for efficiency
DB_DEBUG = app.config.get('DB_DEBUG')
DB_DEBUG_OUTPUT = app.config.get('DB_DEBUG_OUTPUT')
CONSOLE_ECHO = app.config.get('CONSOLE_ECHO')
READ_ONLY = app.config.get("READ_ONLY")

# Set up log file path and name.
logfile = app.config.get('LOG_BASENAME')
logpath = app.config.get('LOG_DOWNLOAD_FOLDER')

# Master logger dict with all events' loggers.
loggers = {}

# Fetch the environment to determine if we're running as a development server
# (prevent double-log files).
flaskenv = os.environ.get('FLASK_ENV')

# Create the login manager.
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'main_bp.login'

""" Log """
if flaskenv != 'development' or is_running_from_reloader():
    from elections.log import AppLog

    try:
        # Init the global log instance for when there are no users.
        loggers[AppLog.get_id()] = AppLog(0, 0, logfile, logpath)

        loggers[AppLog.get_id()].critical("System is starting...")

        # Fetch global event config (for when not logged in).
        from elections.events import EventConfig
        EVENTCONFIG = EventConfig(version=app.config.get('VERSION'))

        # If we couldn't retrieve the default event configuration, there's a fatal problem.
        if EVENTCONFIG is None:
            loggers[AppLog.get_id()].critical("System failed to start (no default event configuration!)")
            sys.exit(1)

        # Fetch all clubs so we can fetch logger handles for master system activity.
        # We use a global handle for system activities.
        from elections.clubs import fetchClubs
        clubdata = fetchClubs('system', fetchall=True)

        # Fetch all events so we can fetch logger handles for master system activity.
        eventdata = EventConfig._fetch_events()

        # Create the logger handles for each club and event.
        for c in clubdata:
            # Add the club's logger handle.
            log_id = AppLog.get_id(c['clubid'])
            loggers[log_id] = AppLog(c['clubid'], 0, logfile, logpath)

        for e in eventdata:
            # Add the event's logger handle.
            log_id = AppLog.get_id(e['clubid'], e['eventid'])
            loggers[log_id] = AppLog(e['clubid'], e['eventid'], logfile, logpath)

        # Tell all logs the system restarted.
        for l in loggers:
            loggers[l].critical(f"### Restarting @ {datetime.utcnow()} ###", propagate=False)

        # Load users.
        from elections.users import User
        User.fetch_users()

        loggers[AppLog.get_id()].critical("System initialization completed")
        for l in loggers:
            loggers[l].critical("System started", propagate=False)

    except Exception as e:
        print("Exception during startup: %s" % str(e))
        print(traceback.format_exc())


def shutdown_app():
    if flaskenv != 'development' or is_running_from_reloader():
        print("Shutting down")


"""Run"""
with app.app_context():
    from . import routes
    import atexit

    atexit.register(shutdown_app)

    # Remove the cache limit.
    app.jinja_env.cache = {}

    app.config['TEMPLATES_AUTO_RELOAD'] = True

    # Register Blueprints
    app.register_blueprint(routes.main_bp)
