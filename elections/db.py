#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import traceback
import logging

import psycopg2
import psycopg2.extras

from elections import loggers
from elections import DB_DEBUG, DB_DEBUG_OUTPUT, READ_ONLY
from elections.log import AppLog

# Handle name: connection, error
dbh = {'global' : {'conn': None,
                   'cursor': None,
                   'error': False }
      }

# Unique value exception handler.
class UniqueValueException(Exception):
    def __init__ (self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg

    pass

# Convert to None if NULL.
def convert(a):
    if a == 'NULL':
        return None
    else:
        return a


# Connect to database.
def connect_to_database(handlekey, reconnected=False):
    try:
        # NOTE: You must have a password file.
        # In Windows, it's \Users\<user>\AppData\Roaming\postgresql\pgpass.conf
        # and in Linux, it's at /home/<user>/.pgpass.
        # Content should be:
        # localhost:5432:postgres:source:<password>
        conn = psycopg2.connect('dbname=elections user=elections host=localhost')

        # Disable autocomit = we'll commit ourselves.
        conn.autocommit = False

        loggers[AppLog.get_id()].debug("%sonnected to database as '%s'" % ("C" if reconnected is False else "Rec", handlekey))
        return conn

    except:
        loggers[AppLog.get_id()].error("Failed to connect to database for handle '%s'!" % handlekey)
        loggers[AppLog.get_id()].error(traceback.format_exc())
        raise


# Close database connection.
def close_database(handlekey='global'):
    global dbh

    try:
        conn = dbh[handlekey].get('conn', None)
        cursor = dbh[handlekey].get('cursor', None)

        if cursor is not None:
            cursor.close()

        if conn is not None:
            conn.close()
            dbh.pop(handlekey)

    except:
        loggers[AppLog.get_id()].error("Failed to close database connection!")
        loggers[AppLog.get_id()].error(traceback.format_exc())
        raise


# DUmp the query for logging.
def dump_query(query, data):
    querylines = query.split('\n')
    querylines = filter(None, querylines)
    for q in querylines:
        loggers[AppLog.get_id()].debug("---> %s" % q.strip(' ').replace("  ", ''), indent=1)

    if len(data) > 0:
        loggers[AppLog.get_id()].debug("---> Inputs: %s", data, indent=1)


# Dump the results for debug.
def dump_results(results):
    if len(results) == 0:
        loggers[AppLog.get_id()].debug("Result Data: (None)")
    else:
        loggers[AppLog.get_id()].debug("Result Data:")
        for index, result in enumerate(results):
            loggers[AppLog.get_id()].debug("Result %d:" % index)

            for rowindex, r in enumerate(result):
                loggers[AppLog.get_id()].debug("Row %d:" % rowindex, indent=1)
                for item in r:
                    loggers[AppLog.get_id()].debug('---> %16s: %s' % (item, str(r[item])), indent=2)


# Get the cursor from the given connection.
def get_cursor(dbconn):
    return dbconn.cursor(cursor_factory = psycopg2.extras.RealDictCursor)


# Rollback transaction and log the error with traceback.
def rollback_with_error(query, data, conn):
        # On error, rollback the transaction.
        loggers[AppLog.get_id()].error("Error on transaction:")

        # Dump query
        dump_query(query, data)

        loggers[AppLog.get_id()].error(traceback.format_exc())

        loggers[AppLog.get_id()].error("Rolling back transaction")
        conn.rollback()


# Execute a query/series of queries as one transaction.
def sql(queries, data=[], handlekey='global', autocommit=True):
    '''Run an SQL query and return the outcome'''

    global dbh
    dbres = []
    rows = []
    err = None

    # If the handle key is passed in as None, ensure a default.
    if handlekey is None:
        handlekey = 'global'

    # Make it possible to process multiple queries per transaction.
    if type(queries) is not list:
        queries = [queries]

    try:
        # loggers[AppLog.get_id()].debug("Transaction started")

        # Connect to the DB if we're not already.
        if dbh.get(handlekey) is None:
            conn = connect_to_database(handlekey)
            cursor = get_cursor(conn)

            dbh[handlekey] = {'conn': conn,
                              'cursor': cursor,
                              'error': False
                             }
        else:
            conn = dbh[handlekey].get('conn')

            # If the connection is closed, reopen it.
            if conn.closed > 0:
                conn.close()

                conn = connect_to_database(handlekey, reconnected=True)
                cursor = get_cursor(conn)

                dbh[handlekey] = {'conn': conn,
                                  'cursor': cursor,
                                  'error': False
                                 }

            cursor = dbh[handlekey].get('cursor')

        for query in queries:
            # Debug output
            if DB_DEBUG is True:
                dump_query(query, data)

            # If in read-only mode and the query alters data, disallow it.
            if any(q in query for q in ['INSERT', 'UPDATE', 'DELETE']) and READ_ONLY is True:
                err = "System is in read-only mode."
            else:
                # execute the query
                if len(data) > 0:
                    rowdata = (cursor.execute(query, data))
                else:
                    rowdata = (cursor.execute(query))

                if rowdata is not None:
                    rows.append(rowdata)

                # fetch the data
                if query.startswith('SELECT') or 'RETURNING' in query:
                    resdata = cursor.fetchall()
                    if resdata is not None:
                        dbres.append(resdata)

        # Debug output
        #dump_results(rows)
        if DB_DEBUG_OUTPUT is True:
            dump_results(dbres)

        # Close and commit or rollback if failed.
        if err is not None:
            rollback_with_error(query, data, conn)

        # If not autocommitting, we're running a multi-step transaction with a lock.
        # We need to complete the commit here to commit the data and close the lock.
        if autocommit is True:
            conn.commit()

        # log.logit(logger,"Transaction completed")

        # Queries that issue changes need to check for error (as read-only).
        return rows, dbres, err

    except psycopg2.errors.UniqueViolation as ue:
        rollback_with_error(query, data, conn)

        try:
            msg = ue.diag.message_detail
        except:
            msg = "Key value already exists."

        raise UniqueValueException(msg)

    # On operational error (connection closed), try again.
    # This will fetch a new handle and retry the transaction.
    # If it fails again, the error will get thrown.
    except psycopg2.OperationalError as oe:
        msg = str(oe)
        loggers[AppLog.get_id()].critical("Database operational error: %s" % msg)

        if dbh[handlekey]['error'] is False:
            loggers[AppLog.get_id()].critical("Retrying transaction...")
            dbh[handlekey]['error'] = True

            dump_query(query, data)

            return sql(queries, data, handlekey, autocommit)

        else:
            loggers[AppLog.get_id()].critical("Aborting transaction")

    # All other errors (including a failed transaction after attempting to reconnect).
    except Exception as e:
        rollback_with_error(query, data, conn)

        # The caller will handle the error.
        raise


def commit(handlekey):
    conn = dbh[handlekey].get('conn')
    loggers[AppLog.get_id()].debug("Committing previously opened transaction for user '%s'" % handlekey)
    conn.commit()