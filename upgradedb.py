#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import os, sys, shutil
import traceback
import random, string

import psycopg2
import psycopg2.extras

def connect_to_database():
    try:
        # NOTE: You must have a password file.
        # In Windows, it's \Users\<user>\AppData\Roaming\postgresql\pgpass.conf
        # and in Linux, it's at /home/<user>/.pgpass.
        # Content should be:
        # localhost:5432:postgres:elections:<password>
        conn = psycopg2.connect('dbname=elections user=elections host=localhost')

        # We will commit by ourselves.
        conn.autocommit = False

        return conn

    except:
        print("Failed to connect to database!")
        print(traceback.format_exc())
        sys.exit(1)


def close_database(conn):
    try:
        if conn is not None:
            conn.close()

    except:
        print("Failed to close database connection!")
        print(traceback.format_exc())
        sys.exit(1)


def get_cursor(dbconn):
    return dbconn.cursor(cursor_factory = psycopg2.extras.RealDictCursor)


def dump_exception(ex):
    linedata = ex.args[0]

    if type(linedata) is str:
        lines = linedata.split('\n')
        lines = list(filter(None, lines))

        message = "Exception %s: %s" % (type(ex).__name__, lines[0])
        for line in lines:
            message += "\n%s" % line

        print(message)

    else:
        print("Exception: %s" % str(ex))

    print(traceback.format_exc())


# Generic cleanup on exception.
def cleanup_exception_handler(conn, cursor):
    if conn is not None:
        conn.rollback()

    if cursor is not None:
        cursor.close()

    if conn is not None:
        conn.close()


# Fetch the newly installed config.  We might want this data to set defaults.
def fetch_config():

    # Convert the config to a dict.  The config is a class, so we need to make that
    # something parseable/iterable for use.
    def get_config_as_dict(config):
        configdata = {}
        members = [attr for attr in dir(config) if not callable(getattr(config, attr)) and not attr.startswith("__")]
        for m in members:
            configdata[m] = getattr(config, m)

        return configdata

    try:
        # Reload the module to be able to fetch the new config.
        import importlib
        import electomatic.config as config

        importlib.reload(config)

    except:
        try:
            # This is a fresh module load.
            import config

        except:
            # If we can't get any config, return a dummy.
            return {}

    # Get the config as a dict.
    configdata = get_config_as_dict(config.Config())

    return configdata


#=====================================================
# UPGRADE METHODS
#=====================================================

# Dummy function to skip upgrades.
def dummy(cursor):
    return 0


# List of upgrade functions, indexed by version.
UPGRADE_VERSION_FUNCS = [dummy,
                         dummy,
                        ]

# Execute an update from the previous to the new version.
def execute_update(new_version, configdata):
    conn = None
    cursor = None

    # Get the previous version for display.
    prev_version = new_version - 1

    try:
        print("\nUpdating from version %d to %d..." % (prev_version, new_version))

        # Call the upgrader for the new version that builds the SQL for the database update.
        UPGRADE_VERSION_FUNCS[new_version](configdata)

        # Set database version as the new version.
        conn = connect_to_database()
        cursor = get_cursor(conn)

        print("  Updating database version to %d..." % new_version)
        cursor.execute('''UPDATE dbversion SET dbversion=%d;''' % new_version)

        conn.commit()
        cursor.close()
        close_database(conn)

        return 0

    except Exception as ex:
        print("\nFailed to execute upgrade from version %d to %d:" % (prev_version, new_version))

        dump_exception(ex)
        cleanup_exception_handler(conn, cursor)
        return 1


def upgrade_database(installdir):
    conn = None
    cursor = None

    # The current version is equal to the last index in the upgrade functions table.
    CURRENT_DBVERSION = len(UPGRADE_VERSION_FUNCS) - 1

    try:
        # Fetch the config.
        configdata = fetch_config()

        # Add the installation directory to the data set.
        configdata['INSTALLDIR'] = installdir

        conn = connect_to_database()
        cursor = get_cursor(conn)

        # Fetch the database version.
        cursor.execute('''SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'dbversion');''')
        result = cursor.fetchone()
        if result is None:
            print("Failed to find version table in database")
            return 1

        # This will always return something, True or False.
        exists = result['exists']
        if exists is False:
            print("No version table present; installing...")

            cursor.execute('''CREATE TABLE dbversion (dbversion INTEGER NOT NULL);''')
            cursor.execute('''GRANT ALL PRIVILEGES ON TABLE dbversion to elections;''')
            cursor.execute('''INSERT INTO dbversion(dbversion) VALUES(1);''')
            conn.commit()

            print("Created version table at version 1.")

        # Fetch the installed database version.
        cursor.execute('''SELECT dbversion FROM dbversion;''')
        result = cursor.fetchone()
        if result is None:
            print("Failed to retrieve database version")
            return 1

        # Check what to do based on database version.
        version = result['dbversion']
        if version < CURRENT_DBVERSION:
            print("Database is at version %d (expected %d)." % (version, CURRENT_DBVERSION))

            # Execute the updates we require.
            # We start at the version after the one we found.
            # There must be at least one version upgrade to run since we got here.
            for v in range((version + 1), (CURRENT_DBVERSION + 1)):
                if execute_update(v, configdata) != 0:
                    cursor.close()
                    close_database(conn)
                    return 1

            # Grant privileges of everything to elections user.
            print("\nFinalizing privileges...")
            cursor.execute('''GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO elections;''')
            cursor.execute('''GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO elections;''')
            conn.commit()

        print("\nDatabase is up to date at version %d." % CURRENT_DBVERSION)

        cursor.close()
        close_database(conn)

        return 0

    except Exception:
        print("Failed to execute upgrade:")
        print(traceback.format_exc())

        if conn is not None:
            conn.rollback()

        if cursor is not None:
            cursor.close()

        close_database(conn)

        return 1


if __name__ == '__main__':

    if sys.platform == 'linux':
        # DO NOT RUN THIS AS SUDO!  IT WILL SET THE WRONG TABLE OWNERSHIP VALUES.
        if os.geteuid() == 0:
            exit("Do not run this script as sudo.")

    upgrade_database(installdir='.')
