#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import os, traceback

from flask import redirect, render_template, url_for, request, session
from flask_login import current_user

from elections import app, loggers
from elections import ADMINS
from elections import loghelpers

# Show and download the system log.
def showLog(user):
    try:
        event = current_user.event

        # Fetch the appropriate log file.
        if event.clubid == 0:
            filename = '%s.log' % app.config.get('LOG_BASENAME')
        elif event.eventid == 0:
            filename = '%s.%d.log' % (app.config.get('LOG_BASENAME'), event.clubid)
        else:
            filename = '%s.%d.%d.log' % (app.config.get('LOG_BASENAME'), event.clubid, event.eventid)

        filepath = url_for('main_bp.logfile', filename=filename)
        logfile = current_user.logger.logfile

        # Fetch the log file offsets from the logger.
        fileoffsets = current_user.logger.get_offsets()

        # If we don't have a stashed offset, set it up as 'first'.
        browse = request.values.get('browse', 'first')
        if browse == 'first' or session.get('logfile_offset', None) is None:
            session['logfile_offset'] = 0

        # Get the page size and the number of lines in the log
        # (its offset file is smaller and has the same number of lines).
        pagesize = app.config.get('LOGPAGE_SIZE')
        linecount = current_user.logger.count_logfile_lines(offsetfile=True)

        loglines = []
        logdata = []

        # Parse the given input line tuple of (line index, line data).
        def parse_line(linedata):
            index, line = linedata

            # Split into elements at the semicolon.
            splitline = line.split(';')

            try:
                # Extract log date, time, and level.
                logdate, logtime = splitline[0].split(' ')

                loglevel = splitline[1].strip()

                # Get clubid/eventid/userid
                logclubid, logeventid, loguser = splitline[2].split('/')

                # Extract the IP address if present.
                ipaddr = splitline[3]

                # Extract the message.
                linedata = ' '.join(splitline[4:])

                # Add the data for rendering.
                logdata.append([index, logdate, logtime, loglevel, logclubid, logeventid, loguser, ipaddr, linedata])

            except:
                # When dumping things like tracebacks to log, they don't have any of our stuff.
                linedata = line

                # Add the data for rendering.
                logdata.append([index, '', '', 'ERROR', '', '', '', '', linedata])


        # Read and set up filters.

        # Fetch any log level filtering from the form.
        loglevel = request.values.get('loglevel', '0')
        loglevel = int(loglevel)
        logstr = request.values.get('logstr', '')

        # Fetch the previously remembered offset for the session.
        offset = session['logfile_offset']

        try:
            # If a line was specified as a filter, fetch it.
            # Actual line offset is this - 1.
            # Bound to the valid range and ignore if not an integer.
            gotoline = request.values.get('gotoline', '')
            if len(gotoline) > 0:
                gotoline = int(gotoline) - 1
                gotoline = max(0, min(gotoline, (linecount - 1)))

        except:
            gotoline = ''

        if gotoline != '':
            offset = gotoline
        else:
            # Special cases: first and last.
            if browse == 'first':
                # Beginning.
                offset = 0

            elif browse == 'last':
                # Last line.
                offset = linecount - 1

        # Fetch the lines.
        # If we got none, it's almost certainly because we tried to view beyond the last page,
        # try again.  The fetcher will set the offset appropriately in that case.
        loglines, offset = loghelpers.fetch_loglines(logfile, browse, pagesize, linecount, fileoffsets, offset, loglevel, logstr)
        if len(loglines) == 0:
            loglines, offset = loghelpers.fetch_loglines(logfile, browse, pagesize, linecount, fileoffsets, offset, loglevel, logstr)

        # Parse the lines we found.
        for linedata in loglines:
            parse_line(linedata)

        # If we are viewing the last page, we need to overide what we calculated (back to)
        # with the end-of-file as having shown the 'last page'.
        if browse == 'last':
            offset = linecount - 1

        # Save the offset change here to ensure we opened and read the file.
        session['logfile_offset'] = offset

        return render_template('config/showlog.html', user=user, admins=ADMINS[event.clubid],
                            filepath=filepath, filename=filename, logdata=logdata,
                            loglevel=loglevel, loglevels=loghelpers.loglevels, logstr=logstr,
                            configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Show Log failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Clear/reset the log, or all logs if requested.
def clearLogs(user, alllogs=False):
    try:
        # Clear any session flags.
        def clear_session_flags():
            for flag in ['logreset', 'logconfirm']:
                if flag in session:
                    current_user.logger.debug("Event data reset: Clearing session flag '%s'" % flag, indent=1)
                    session.pop(flag, None)

        allstr = ('all ' if all is True else '')
        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Clear log operation canceled.", 'info')
            clear_session_flags()
            return redirect(url_for('main_bp.clearlogs'))

        current_user.logger.info("Displaying: Clear %slogs" % allstr)

        # The process is:
        # - Initiate via 'Submit'
        #   - Set a 'set' flag in the session
        # - Confirm via 'Confirm'
        #   - Set a 'confirm' flag in the session
        # - Execute the reset
        # - Confirm one more time as it's totally destructive
        reset_request = False
        confirm_request = False
        saving = False

        savebutton = request.values.get('savebutton', None)
        if savebutton is not None:

            if savebutton == 'reset':
                current_user.logger.debug("Clearing %slogs: Reset requested" % allstr, propagate=True)
                session['logreset'] = True

                # Force reaquiring of confirmation.
                if 'logconfirm' in session:
                    session.pop('logconfirm', None)

                reset_request = True

            elif savebutton == 'confirm' and 'logreset' in session:
                current_user.logger.debug("Clearing %slogs: Confirm requested" % allstr, propagate=True)
                session['logconfirm'] = True

                reset_request = True
                confirm_request = True

            else:
                if all(x in session for x in ['logreset', 'logconfirm']):
                    saving = True
        else:
            # Force-clear session flags on fresh page load.
            clear_session_flags()

        if saving is True:
            current_user.logger.info("Clearing %slogs" % allstr, propagate=True)

            # Force-clear session flags since we're done.
            clear_session_flags()
            reset_request = False
            confirm_request = False

            if alllogs is False:
                # Reset the current user's log.  The reset will log the action.
                current_user.logger.reset()
                current_user.votelogger.reset()
                current_user.logger.flashlog(None, "Logs cleared.", level='info', propagate=True)

            else:
                # Reset each log.  The reset will log the action.
                for l in loggers:
                    loggers[l].reset()

                current_user.logger.flashlog(None, "Cleared all system, club and event logs.", level='info', propagate=True)

            current_user.logger.info("Clearing %slogs: Operation completed" % allstr)
            return redirect(url_for('main_bp.clearlogs'))

        return render_template('config/clearlogs.html', user=user, admins=ADMINS[current_user.event.clubid],
                            reset_request=reset_request, confirm_request=confirm_request,
                            configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Clear Log failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))
