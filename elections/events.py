#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import os, traceback, re
import shutil, copy
import threading
import elections.images as images

from flask import redirect, render_template, url_for, request, session
from flask_login import current_user

from elections import db, app
from elections import loggers
from elections import ALLUSERS, ADMINS

from elections.log import AppLog

# Mutex to serialize access to changes to event configs in database and caches.
events_mutex = threading.Lock()

# Class to manage event config information.
class EventConfig:
    def __init__(self, fetchconfig=True, version=None, user=None, clubid=0, eventid=0, eventdatetime='',
                       locked=False):
        self.locked = locked

        self.title = app.config.get('DEFAULT_EVENT_TITLE')
        self.icon = app.config.get('DEFAULT_APPICON')
        self.homeimage = app.config.get('DEFAULT_HOMEIMAGE')

        self.eventdatetime = eventdatetime

        self.version = version
        self.clubid = clubid
        self.eventid = eventid

        # Normally, we want to read the event config from database.
        # If importing data, we want a default template.
        if fetchconfig is True:
            # Read out the data.
            r = EventConfig._fetch_config(self.clubid, self.eventid, (user if user is not None else 'system'))
            if r is None:
                return None

            if len(r) > 0:
                # Indicates the event is locked (cannot be modified).
                self.locked = r['locked']

                # App information.
                self.title = r['title']
                self.icon = r['icon']
                self.homeimage = r['homeimage']
                self.eventdatetime = r['eventdatetime']

                # Club and event information.
                self.clubid = int(r['clubid'])
                self.eventid = int(r['eventid'])

        # Get the logid for this event, based on club and event Id.
        # This is useful when dealing with the system logger,
        self.logid = AppLog.get_id(self.clubid, self.eventid)


    # Get the event config mutex to serialize readers/writers.
    def _get_events_lock(user):
        #loggers[AppLog.get_id()].debug("Acquiring events mutex: %s" % ('system' if user is None else user))

        events_mutex.acquire()

        # Temporary for testing locks
        #import time
        #time.sleep(5)

        #loggers[AppLog.get_id()].debug("Acquired events mutex: %s" % ('system' if user is None else user))


    # Let go of the event config mutex.
    def _release_events_lock(user):
        #loggers[AppLog.get_id()].debug("Releasing events mutex: %s" % ('system' if user is None else user))

        events_mutex.release()

        #loggers[AppLog.get_id()].debug("Released events mutex: %s" % ('system' if user is None else user))


    # Fetch events from the database.  Used during init.  Therefore, we don't bother with a mutex check here.
    def _fetch_events(dbuser='system'):
        logger = loggers[AppLog.get_id()]
        logger.debug("Fetching events: %s" % dbuser)

        outsql = ['''SELECT clubid, eventid
                     FROM events;
                  ''']
        _, results, err = db.sql(outsql, handlekey=dbuser)

        # Log errors to the master log, 0/0.
        if err is not None:
            loggers[AppLog.get_id()].critical("Failed to fetch events: %s" % err)
            return None

        logger.debug("Fetched event config")

        events = results[0]
        return events


    # Fetch the event config data from the database.
    def _fetch_config(clubid, eventid, dbuser='system'):
        logger = loggers[AppLog.get_id(clubid, eventid)]
        logger.debug("Fetching event config: %s" % dbuser)

        try:
            EventConfig._get_events_lock(dbuser)

            outsql = ['''SELECT *
                        FROM events
                        WHERE clubid='%d' AND eventid='%d';
                    ''' % (clubid, eventid)]
            _, results, err = db.sql(outsql, handlekey=dbuser)

            EventConfig._release_events_lock(dbuser)

            # Log errors to the club or event's log.
            if err is not None:
                logger.critical("Failed to fetch event config: %s" % err)
                return None

            # The events data is the first 'dbresults' in the list.
            appdata = results[0]

            r = []
            if len(appdata) > 0:
                r = appdata[0]

            logger.debug("Fetched event config")

            # Return the data set.
            return r

        except:
            # On exception, release the mutex and re-raise it.
            EventConfig._release_events_lock(dbuser)
            raise


    # Set the config based on the current object's contents.
    # Creating the object populates the initial data; this way, the complete
    # data set gets included.
    def save_config(self, user):
        try:
            loggers[self.logid].info("Saving event config: %s" % user)

            EventConfig._get_events_lock(user)

            outsql = '''UPDATE events
                        SET locked=%s, title='%s', icon='%s', homeimage='%s', eventdatetime='%s'
                        WHERE clubid='%d' AND eventid='%d';
                    ''' % (self.locked, self.title, self.icon, self.homeimage, self.eventdatetime,
                           self.clubid, self.eventid)

            _, _, err = db.sql(outsql, handlekey=user)

            EventConfig._release_events_lock(user)

            # Log errors to the event's log.
            if err is not None:
                loggers[self.logid].error("Failed to save event config: %s" % err)
                return err

            loggers[self.logid].info("Saved event config: %s" % user)

            return None

        except:
            # On exception, release the mutex and re-raise it.
            EventConfig._release_events_lock(user)
            raise

    # Reset the config for the club and event to defaults.
    def reset_config(self, user):
        self.locked = False
        self.title = app.config.get('DEFAULT_EVENT_TITLE')
        self.icon = app.config.get('DEFAULT_APPICON')
        self.homeimage = app.config.get('DEFAULT_HOMEIMAGE')
        self.eventdatetime = ''

        # Note: We deliberately do not reset the club and event ID here
        # since those are to be preserved across resets.

        try:
            loggers[self.logid].info("Resetting event config: %s" % user)

            EventConfig._get_events_lock(user)

            # Reset and insert defaults.
            outsql = ['''DELETE FROM events
                        WHERE clubid='%d' AND eventid='%d';
                    ''' % (self.clubid, self.eventid)]

            outsql.append('''DELETE FROM vote_ballotid
                            WHERE clubid='%d' AND eventid='%d';
                        ''' % (self.clubid, self.eventid))

            outsql.append('''INSERT INTO events (locked, title, icon, homeimage, eventdatetime,
                                                clubid, eventid)
                            VALUES (%s, '%s', '%s', '%s', '%s', '%d', '%d');
                        ''' % (self.locked, self.title, self.icon, self.homeimage, self.eventdatetime,
                               self.clubid, self.eventid))
            outsql.append('''INSERT INTO vote_ballotid
                            VALUES('%d', '%d', 0);
                        ''' % (self.clubid, self.eventid))

            _, _, err = db.sql(outsql, handlekey=user)

            # Update all other user caches.
            EventConfig.update_event_caches(user, self, lock=False)

            EventConfig._release_events_lock(user)

            # Log errors to the event's log.
            if err is not None:
                loggers[self.logid].error("Failure to reset event config: %s" % err)
                return err

            loggers[self.logid].info("Reset event config: %s" % user)

            return None

        except:
            # On exception, release the mutex and re-raise it.
            EventConfig._release_events_lock(user)
            raise


    # Walk all of the user caches and update them with the contents of the given club config.
    def update_club_caches(user, clubdata):
        try:
            clubid = clubdata['clubid']
            clubname = clubdata['clubname']

            logger = loggers[AppLog.get_id(clubid=clubid)]
            logger.info("Updating club caches for users of Club %d (%s)" % (clubid, clubname), indent=1, propagate=True)

            EventConfig._get_events_lock(user)

            # Walk the all-users cache, finding all events with the club and event ID, and
            # copy this info into them.
            for u in ALLUSERS:
                # The users are represented by UUIDs in the cache.
                uuids = ALLUSERS[u]

                # If the user is logged in, there will be one or more UUIDs, each representing a User object.
                if len(uuids) > 0:
                    for uuid in uuids:
                        cacheduser = uuids[uuid]

                        # Update all users with this Event ID.
                        if cacheduser.event.clubid == clubid:
                            logger.info("Updating club cache for user '%s' (%s)" % (cacheduser.id, cacheduser.get_userid()), indent=2, propagate=True)

                            # If the incoming data includes an icon and/or home image, update those attributes.
                            for attr in ['icon', 'homeimage']:
                                value = clubdata.get(attr, None)

                                if value is not None:
                                    # If the event is referencing the club's image(s), continue that reference.
                                    if '../' in getattr(cacheduser.event, attr):
                                        value = '%s%s' % ('../', clubdata[attr])

                                    setattr(cacheduser.event, attr, value)

                            for attr in ['clubname']:
                                setattr(cacheduser, attr, clubdata[attr])

            EventConfig._release_events_lock(user)

            logger.info("Updated club caches for users of Club %d (%s)" % (clubid, clubname), indent=1, propagate=True)

        except:
            # On exception, release the mutex and re-raise it.
            EventConfig._release_events_lock(user)
            raise


    # Walk all of the user caches and update them with the contents of the given event config.
    def update_event_caches(user, newconfig, lock=True):
        try:
            logger = loggers[AppLog.get_id(clubid=newconfig.clubid, eventid=newconfig.eventid)]
            logger.info("Updating event caches for users of Event %d (%s)" % (newconfig.eventid, newconfig.title), indent=1, propagate=True)

            if lock is True:
                EventConfig._get_events_lock(user)

            # Walk the all-users cache, finding all events with the club and event ID, and
            # copy this info into them.
            for u in ALLUSERS:
                # The users are represented by UUIDs in the cache.
                uuids = ALLUSERS[u]

                # If the user is logged in, there will be one or more UUIDs, each representing a User object.
                if len(uuids) > 0:
                    for uuid in uuids:
                        cacheduser = uuids[uuid]

                        # Update all users with this Event ID.
                        if cacheduser.event.eventid == newconfig.eventid:
                            logger.info("Updating event cache for user '%s' (%s)" % (cacheduser.id, cacheduser.get_userid()), indent=2, propagate=True)

                            for attr in ['version', 'title', 'locked']:
                                setattr(cacheduser.event, attr, getattr(newconfig, attr))

                            for attr in ['icon', 'homeimage']:
                                try:
                                    # Try to get these attributes.  If they don't exist, that's okay (like during a restore).
                                    # In that case, just set the value.
                                    value = getattr(newconfig, '%s_changed' % attr)
                                    if value is True:
                                        setattr(cacheduser.event, attr, getattr(newconfig, attr))
                                except:
                                    setattr(cacheduser.event, attr, getattr(newconfig, attr))

            if lock is True:
                EventConfig._release_events_lock(user)

            logger.info("Updated event caches for users of Event %d (%s)" % (newconfig.eventid, newconfig.title), indent=1, propagate=True)

        except:
            # On exception, release the mutex and re-raise it.
            if lock is True:
                EventConfig._release_events_lock(user)
            raise


    # Get the new ballot ID to use and update the database with the next one.
    # Sets both in the object and the database together.
    def get_vote_ballotid(self, user):
        try:
            loggers[self.logid].info("Fetching new ballot ID: %s" % user)

            EventConfig._get_events_lock(user)

            # Get the next ballotid by selecting the current largest value and adding 1, and return it.
            # This updates the databse and then provides teh value that was updated, making it atomic
            # across users.
            outsql = '''UPDATE vote_ballotid
                        SET ballotid=(SELECT COALESCE(MAX(ballotid), 0) AS max FROM vote_ballotid WHERE clubid='%d' AND eventid='%d') + 1
                        WHERE clubid='%d' AND eventid='%d'
                        RETURNING ballotid;
                    ''' % (self.clubid, self.eventid, self.clubid, self.eventid)
            _, data, err = db.sql(outsql, handlekey=user)

            # Log errors to the event's log.
            if err is not None:
                loggers[self.logid].error(err)
                EventConfig._release_events_lock(user)
                return 0, err

            ballotid = int(data[0][0]['ballotid'])

            loggers[self.logid].info("Fetched new ballot ID %d" % ballotid)

            EventConfig._release_events_lock(user)
            return ballotid, None

        except:
            # On exception, release the mutex and re-raise it.
            EventConfig._release_events_lock(user)
            raise


    # Fetch configuration/display data as a common item for rendering.
    # This is generally used for defaults only (login/logout/unauthorized) since the user object
    # will have an event, and can access these directly.
    def get_event_render_data(self):
        # version   = data[0]
        # title     = data[1]
        # icon      = data[2]
        # homeimage = data[3]
        # clubid    = data[4]
        # eventid   = data[5]
        # The rest are defaulted blank, but should not be needed:
        # siteadmin   = data[6]
        # clubname    = data[7]
        # tenancy     = data[8]
        # event_login = data[9]
        # public_login = data[10]
        # clubadmin   = data[11]
        # event locked = data[12]

        return [self.version,
                self.title.replace("''", "'"),
                self.icon,
                self.homeimage,
                str(self.clubid),
                str(self.eventid),
                False,
                '',
                app.config.get("MULTI_TENANCY"),
                session.get('event_login', False),
                session.get('public_login', False),
                False,
                self.locked,
                ]


# Handlers for event management.

# Remove event data.
def remove_event_data(user, clubid, eventid, clear_config=True, votes_only=False):
    try:
        EventConfig._get_events_lock(user)

        # Wipe out the tables for this club/event.
        outsql = []

        import elections.configdata as configdata

        # Make a copy of all the sheets to read so we don't modify it.
        # We always use the latest 'version' as the currently implemented one.
        sheets = copy.copy(configdata.ALL_SHEETS[configdata.EXPORT_VERSION])

        # If not clearing out event data, take it out of the sheets list.
        if clear_config is False:
            current_user.logger.debug("Skipping removal of event config data", indent=2)
            sheets.pop(sheets.index('events'))

        # If only removing votes, keep the non-voting sheet tables.
        if votes_only is True:
            current_user.logger.debug("Skipping removal of event entry data", indent=2)
            for sheet in ['events', 'ballotitems', 'candidates', 'voters']:
                if sheet in sheets:
                    sheets.pop(sheets.index(sheet))

            # Remove any write-in candidates.
            current_user.logger.info("Remmoving write-in candidates", indent=2)
            outsql.append('''DELETE FROM candidates
                            WHERE clubid='%d' AND eventid='%d' AND writein=True;
                            ''' % (clubid, eventid))

            # Reset any 'voted' flags.
            current_user.logger.info("Clearing voter voted flags", indent=2)
            outsql.append('''UPDATE voters
                             SET voted=False
                             WHERE clubid='%d' AND eventid='%d';
                            ''' % (clubid, eventid))

        # Remove all data from the tables to be cleared.
        for table in sheets:
            outsql.append('''DELETE FROM %s
                            WHERE clubid='%d' AND eventid='%d';
                        ''' % (table, clubid, eventid))

        # If not clearing the config, we are resetting the event (not removing it) and as such need an initial vote ballot id.
        if clear_config is False:
            # Add the initial vote ballot ID of 0.
            current_user.logger.debug("Resetting ballot ID", indent=2)
            outsql.append('''INSERT INTO vote_ballotid
                            VALUES(%d, %d, 0);
                        ''' % (clubid, eventid))

        _, _, err = db.sql(outsql, handlekey=user)

        # On error to update the database, return and print out the error (like "System is in read only mode").
        if err is not None:
            EventConfig._release_events_lock(user)
            return err

        EventConfig._release_events_lock(user)
        return None

    except:
        # On exception, release the mutex and re-raise it.
        EventConfig._release_events_lock(user)
        raise


# Nicely format a datetime-local format string.
def formatDateTime(eventdatetime):
    try:
        if len(eventdatetime) > 0:
            edt = eventdatetime.split('T')
            return '%s %s %s' % (edt[0], edt[1], 'AM' if int(edt[1].split(':')[0]) < 12 else 'PM')
        else:
            return ''
    except:
        current_user.logger.error("Failed to format date/time string '%s'" % eventdatetime)
        return ''


# Fetch events data.
def fetchEvents(user, clubid, sortby='eventid', sortdir='up'):
    try:
        outsql = '''SELECT *
                    FROM events
                    WHERE clubid='%d'
                    ORDER BY %s %s;
                 ''' % (clubid, sortby, 'ASC' if sortdir == 'up' else 'DESC')
        _, data, _ = db.sql(outsql, handlekey=current_user.get_userid())
        events = data[0]

        eventdata = []
        for e in events:
            eventdatetime = formatDateTime(e['eventdatetime'])
            eventdata.append([e['clubid'], e['eventid'], e['title'], eventdatetime, e['locked']])

        return eventdata

    except Exception as e:
        current_user.logger.flashlog("Fetch Events failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

    return None


# Show the list of clubs.
def showEvents(user):
    try:
        clubid = current_user.clubid

        current_user.logger.info("Displaying: Show events list")

        # Fetch all of the events.
        current_user.logger.debug("Showing events list: Fetching events", indent=1)

        # Stash an initial value for sorting.
        if session.get('eventsort') is None:
            session['eventsort'] = ['eventid', 'up']

        # Fetch session sort information.
        eventsort = session.get('eventsort')
        sorttype = eventsort[0]
        sortdir = eventsort[1]

        # Set new direction.
        sortby = request.values.get('sortby', None)
        if sortby is None:
            # Default to cached info on fresh page load.
            sortby = sorttype

        elif sortby != sorttype:
            # Default to 'up' when changing sort types.
            sortdir = 'up'

        else:
            # Flip direction if there's something from the page (button was pushed).
            if sortdir == 'up':
                sortdir = 'down'
            else:
                sortdir = 'up'

        eventdata = fetchEvents(user, clubid, sortby, sortdir)

        # Remember for next time.
        session['eventsort'] = [sortby, sortdir]

        # Check the value of all select buttons for clubs.
        for e in eventdata:
            eventid = int(e[1])

            eventselect = request.values.get("select_%d" % eventid, None)
            viewselect = request.values.get("view_%d" % eventid, None)
            editselect = request.values.get("edit_%d" % eventid, None)

            if eventselect is not None:
                current_user.logger.info("Showing events list: Selecting Event ID '%s' (%s)" % (eventid, e[2]), indent=1)

                # Fetch the event config for the event ID and assign to the user.
                current_user.set_event(eventid)

                # Update the cached event ID in the session.
                session['eventid'] = eventid

                # Reset session's logfile offset.
                session['logfile_offset'] = 0

                # Redirect to the main page.
                current_user.logger.info("Showing events list: User transitioned to Event ID '%s' (%s)" % (eventid, e[2]), indent=1)
                return redirect(url_for('main_bp.index'))

            if viewselect is not None:
                current_user.logger.info("Showing events list: Viewing Event ID '%s' (%s)" % (eventid, e[2]), indent=1)

                # Redirect to the view page for that event.
                return redirect(url_for('main_bp.showevent', eventid=eventid))

            if editselect is not None:
                current_user.logger.info("Showing events list: Editing Event ID '%s' (%s)" % (eventid, e[2]), indent=1)

                # Redirect to the edit page for that event.
                return redirect(url_for('main_bp.editevent', eventid=eventid))


        # There are no voters or admins that apply for site-admin functions.
        return render_template('events/showevents.html', user=user, admins=ADMINS[current_user.clubid],
                                eventdata=eventdata,
                                sortby=sortby, sortdir=sortdir,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("View Events failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# View an event for a club.
def showEvent(user):
    try:
        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "View event operation canceled.", 'info')
            return redirect(url_for('main_bp.showevent'))

        current_user.logger.info("Displaying: View an event")

        # If the current user's club and event information are nonzero, then an event is being managed
        # and we can shortcut directly to that.  This also sets up viewing the only event in a standalone environment.
        if current_user.clubid != 0 and current_user.event.eventid != 0:
            eventid = str(current_user.event.eventid)
            search = None
        else:
            # Get the entry ID to look up who to edit.
            eventid = request.values.get('eventid', '')
            search = request.values.get('namesearch', '')

            if len(eventid) == 0:
                eventid = None
            else:
                eventid = eventid.strip()

            if len(search) == 0:
                search = None
            else:
                search = search.strip()

        # If the club name is provided, do a lookup and build a table to feed back to the form.
        if eventid is None and search is not None and len(search) > 0:
            current_user.logger.debug("Viewing an event: Searching by event name with '%s'" % search, indent=1)

            # Special keyword - this lets the user see them all.
            if search == '*':
                searchclause = ""
            else:
                searchclause = "AND LOWER(title) LIKE '%s%%'" % search.lower()

            outsql = '''SELECT eventid, title
                        FROM events
                        WHERE clubid='%d' AND eventid > 1 %s
                        ORDER BY title ASC;
                        ''' % (current_user.clubid, searchclause)
            _, result , _ = db.sql(outsql, handlekey=current_user.get_userid())

            # The return data is the first 'dbresults' in the list.
            result = result[0]

            events = []
            for r in result:
                events.append([r['eventid'], r['title']])

            # Nothing found.
            if len(events) == 0:
                current_user.logger.flashlog('View Event failure', "No Events with a name matching '%s' were found." % search)
                # Redirect to the edit page so we don't save the previous entry data.
                return redirect(url_for('main_bp.showevent'))

        else:
            events = None

        # If an club ID has been specified, verify it and get the record.
        if eventid is not None and len(eventid) > 0:
            # Verify the format (numeric).
            try:
                eventid = int(eventid)
            except:
                current_user.logger.flashlog("View Event failure", "Event ID must be a number.")
                return redirect(url_for('main_bp.showevent'))

            current_user.logger.debug("Viewing an event: Viewing Event ID %s" % eventid, indent=1)

            # Fetch the event matching the event ID.  Event ID is unique.
            outsql = '''SELECT *
                        FROM events
                        WHERE eventid='%d';
                        ''' % eventid
            _, result , _ = db.sql(outsql, handlekey=current_user.get_userid())

            # The return data is the first 'dbresults' in the list.
            result = result[0]
            if len(result) == 0:
                current_user.logger.flashlog("View Event failure", "Event ID %s was not found." % eventid)

                # Redirect to the edit page so we don't save the previous entry data.
                return redirect(url_for('main_bp.showevent'))

            event = result[0]

            return render_template('events/showevent.html', user=user, admins=ADMINS[current_user.clubid],
                                eventid=eventid, search=search, events=events,
                                title=event['title'], icon=event['icon'], homeimage=event['homeimage'], eventdatetime=event['eventdatetime'],
                                locked=event['locked'],
                                configdata=current_user.get_render_data())
        else:
            return render_template('events/showevent.html', user=user, admins=ADMINS[current_user.clubid],
                                eventid=eventid, search=search, events=events,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("View Event failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Add an event for a club.
def addEvent(user):
    try:
        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Add event operation canceled.", 'info')
            return redirect(url_for('main_bp.showevents'))

        clubid = current_user.clubid

        current_user.logger.info("Displaying: Add a event")

        # If saving the information, set this for later.
        saving = False
        if request.values.get('savebutton'):
            current_user.logger.debug("Adding a event: Saving changes requested", indent=1)
            saving = True

        # Fetch the club's name for display.
        outsql = '''SELECT clubname
                    FROM clubs
                    WHERE clubid='%d';
                 ''' % clubid
        _, data, _ = db.sql(outsql, handlekey=current_user.get_userid())

        # THe club data is the first 'dbresults' in the list.
        club = data[0]
        if len(club) == 0:
            current_user.logger.flashlog("Add Event failure", "Failed to locate CLub with Club ID %d." % clubid)
            return redirect(url_for('main_bp.addevent'))

        club = club[0]
        clubname = club['clubname']

        if saving is True:
            appfile = None
            homefile = None

            title = request.values.get("title", '').replace("'", "''")
            icon = app.config.get('DEFAULT_APPICON')
            homeimage = app.config.get('DEFAULT_HOMEIMAGE')
            eventdatetime = request.values.get("eventdatetime", "")

            locked = request.values.get("locked", False)
            if locked == 'True':
                locked = True

            if len(title) == 0:
                current_user.logger.flashlog("Add Event failure", "Event Name cannot be empty.")
                return redirect(url_for("main_bp.addevent"))

            if len(eventdatetime) == 0:
                current_user.logger.flashlog("Add Event failure", "Event Date/Time cannot be blank.")
                return redirect(url_for("main_bp.addevent"))

            # If there was an event icon selected, fetch and verify.
            if 'appfile' in request.files:
                appfile = request.files.get('appfile')
                if appfile.filename != '':
                    # Verify the file is an icon of specific size.
                    if appfile.mimetype != "image/x-icon":
                        current_user.logger.flashlog("Add Event failure", "Unsupported browser icon type (not an icon).")
                        return render_template('events/addevent.html', user=user,  admins=ADMINS[current_user.clubid],
                                            title=title, icon=icon, homeimage=homeimage, locked=locked, votekey_timeout=votekey_timeout,
                                            public_votes=public_votes, enable_votes=enable_votes, single_popvote=single_popvote,
                                            clubid=clubid, clubname=clubname,
                                            configdata=current_user.get_render_data())

                    icon = appfile.filename
                else:
                    appfile = None

            # If there was a home image selected, fetch and verify.
            if 'homefile' in request.files:
                homefile = request.files.get('homefile')
                if homefile.filename != '':
                    # Verify the file is a specific type and size.
                    SUPPORTED_FILETYPES = ["image/jpeg", "image/png"]
                    if homefile.mimetype not in SUPPORTED_FILETYPES:
                        current_user.logger.flashlog("Add Event failure", "Unsupported home image type (must be PNG or JPEG).")
                        return render_template('events/addevent.html', user=user,  admins=ADMINS[current_user.clubid],
                                            title=title, icon=icon, homeimage=homeimage, locked=locked, votekey_timeout=votekey_timeout,
                                            public_votes=public_votes, single_popvote=single_popvote,
                                            clubid=clubid, clubname=clubname,
                                            configdata=current_user.get_render_data())

                    homeimage = homefile.filename
                else:
                    homefile = None

            # We need the highest event ID from the database.
            current_user.logger.debug("Adding an event: Searching for highest event ID", indent=1)
            outsql = '''SELECT MAX(eventid)
                        FROM events
                        WHERE clubid='%d';
                      ''' % clubid
            _, result, _ = db.sql(outsql, handlekey=current_user.get_userid())

            # We will always get a result, even if it is None (not found).
            maxid = result[0][0]['max']
            if maxid is None:
                # Generate an event ID for direct login to the event.
                # The formula is: clubid and eventid, like '10011'.  it's unique across clubs since the club Id is unique,
                # and within events for that club, so there is no chance of cross linking to another club's event.
                eventid = int('%d1' % clubid)
                current_user.logger.debug("Adding an event: No events, so event ID = %d" % eventid, indent=1)
            else:
                # When events reach xxxx9, they need to roll to xxxx10, and xxxx99 to xxxx100, etc.
                # We do this by removing the club ID from the event ID, incrementing the remaining value,
                # and then appending it to the club ID.
                maxidstr = str(maxid)
                eventno = int(maxidstr.replace('%s' % clubid, '')) + 1
                eventid = int('%d%d' % (clubid, eventno))
                current_user.logger.debug("Adding an event: Found event ID %d, so event ID = %d" % (maxid, eventid), indent=1)

            # Add the event to the database with an initial vate_ballotid value of 1.
            current_user.logger.info("Adding an event: Saving event '%s'" % title, indent=1)
            outsql = ['''INSERT INTO events (clubid, eventid, locked, title, icon, homeimage, eventdatetime)
                            VALUES ('%d', '%d', %s, '%s', '%s', '%s', '%s');
                      ''' % (clubid, eventid, locked, title, icon, homeimage, eventdatetime)]

            outsql.append('''INSERT INTO vote_ballotid
                            VALUES(%d, %d, 1);
                        ''' % (clubid, eventid))
            _, _, err = db.sql(outsql, handlekey=current_user.get_userid())

            # On error to update the database, return and print out the error (like "System is in read only mode").
            if err is not None:
                current_user.logger.flashlog("Add Event failure:", err, propagate=True)
                return render_template('config/editevent.html', user=user, admins=ADMINS[current_user.clubid],
                                    title=title, icon=icon, homeimage=homeimage, eventdatetime=eventdatetime, locked=locked,
                                    clubid=clubid, clubname=clubname,
                                    configdata=current_user.get_render_data())

            # Save the image files.
            images.save_image_file("Adding an event", appfile, icon, clubid, eventid)
            images.save_image_file("Adding an event", homefile, homeimage, clubid, eventid)

            # Create the log for this event.
            logid = AppLog.get_id(current_user.clubid, eventid)
            loggers[logid] = AppLog(current_user.clubid, eventid, app.config.get('LOG_BASENAME'), app.config.get('LOG_DOWNLOAD_FOLDER'), user)
            loggers[logid].info("### Event created ###")

            current_user.logger.flashlog(None, "Added Event:", 'info', propagate=True)
            current_user.logger.flashlog(None, "Event ID: %d" % eventid, 'info', propagate=True)
            current_user.logger.flashlog(None, "Event Name: %s" % title.replace("''", "'"), 'info', highlight = False, indent=True, propagate=True)
            current_user.logger.flashlog(None, "Event Locked: %s" % ('Yes' if locked is True else 'No'), 'info', highlight = False, indent=True, propagate=True)
            current_user.logger.flashlog(None, "Event Date/Time: %s" % formatDateTime(eventdatetime), 'info', highlight = False, indent=True)

            current_user.logger.info("Adding an event: Operation completed")

            # Show the events page with the new event.
            return redirect(url_for('main_bp.showevents'))

        else:
            title = app.config.get('DEFAULT_EVENT_TITLE')
            icon = app.config.get('DEFAULT_APPICON')
            homeimage = app.config.get('DEFAULT_HOMEIMAGE')
            eventdatetime = ''
            votekey_timeout = app.config.get('VOTE_DEFAULT_REVOTE_TIME')
            locked = False

            # Default public access to People's Choice to 'True'.
            public_votes = [False, True, False]
            enable_votes = [True, True, True]
            single_popvote = False

        return render_template('events/addevent.html', user=user, admins=ADMINS[current_user.clubid],
                            title=title, icon=icon, homeimage=homeimage, eventdatetime=eventdatetime, locked=locked,
                            clubid=clubid, clubname=clubname,
                            configdata=current_user.get_render_data())

    except db.UniqueValueException as ue:
        # Special case where the event ID is reused somehow - infrequent but possible without a bit of tricky work.
        # So the simple answer for now is to look for a 'duplicate key value' string in the error, and publish a nicer
        # message.
        # The duplicate key is in the exception's string value.
        msg = str(ue)
        x = re.search("=\(", msg)
        res = msg[x.span()[1]:]
        eventid = res[0:res.find(')')]

        err = "Duplicate Event ID '%s' was created: please re-enter this Event." % eventid
        current_user.logger.flashlog("Add Event failure", err, propagate=True)

        # Redirect to the edit page so we don't save the previous entry data.
        return redirect(url_for('main_bp.addevent'))

    except Exception as e:
        current_user.logger.flashlog("Add Event failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Edit an event for a club.
def editEvent(user):
    try:
        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Edit event operation canceled.", 'info')
            return redirect(url_for('main_bp.editevent'))

        current_user.logger.info("Displaying: Edit an event")

        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        # If saving, set this for later.
        saving = False
        if request.values.get('savebutton'):
            current_user.logger.debug("Editing an event: Saving changes requested", indent=1)
            saving = True

        # If the current user's club and event information are nonzero, then an event is being managed
        # and we can shortcut directly to that.  This also sets up editing the only event in a standalone environment.
        if current_user.clubid != 0 and current_user.event.eventid != 0:
            eventid = str(current_user.event.eventid)
            search = None
        else:
            # Get the entry ID to look up who to edit.
            eventid = request.values.get('eventid', '')
            search = request.values.get('namesearch', '')

            if len(eventid) == 0:
                eventid = None
            else:
                eventid = eventid.strip()

            if len(search) == 0:
                search = None
            else:
                search = search.strip().replace("'", "''")

        # If the club name is provided, do a lookup and build a table to feed back to the form.
        if eventid is None and search is not None and len(search) > 0:
            current_user.logger.debug("Editing an event: Searching by event name with '%s'" % search, indent=1)

            # Special keyword - this lets the user see them all.
            if search == '*':
                searchclause = ""
            else:
                searchclause = "AND LOWER(title) LIKE '%s%%'" % search.lower()

            outsql = '''SELECT eventid, title
                        FROM events
                        WHERE clubid='%d' AND eventid > 1 %s
                        ORDER BY title ASC;
                        ''' % (current_user.clubid, searchclause)
            _, result , _ = db.sql(outsql, handlekey=current_user.get_userid())

            # The return data is the first 'dbresults' in the list.
            result = result[0]

            events = []
            for r in result:
                events.append([r['eventid'], r['title']])

            # Nothing found.
            if len(events) == 0:
                current_user.logger.flashlog('Edit Event failure', "No Events with a name matching '%s' were found." % search.replace("''", "'"))
                # Redirect to the edit page so we don't save the previous entry data.
                return redirect(url_for('main_bp.editevent'))

        else:
            events = None

        # If an club ID has been specified, verify it and get the record.
        if eventid is not None and len(eventid) > 0:
            # Verify the format (numeric).
            try:
                eventid = int(eventid)
            except:
                current_user.logger.flashlog("Edit Event failure", "Event ID must be a number.")
                return redirect(url_for('main_bp.editevent'))

            current_user.logger.info("Editing an event: Editing Event ID %s" % eventid, indent=1)

            # Fetch the event matching the event ID.  Event ID is unique.
            outsql = '''SELECT *
                        FROM events
                        WHERE eventid='%d';
                        ''' % eventid
            _, result , _ = db.sql(outsql, handlekey=current_user.get_userid())

            # The return data is the first 'dbresults' in the list.
            result = result[0]
            if len(result) == 0:
                current_user.logger.flashlog("Edit Event failure", "Event ID %s was not found." % eventid)

                # Redirect to the edit page so we don't save the previous entry data.
                return redirect(url_for('main_bp.editevent'))

            event = result[0]

            title = event['title']
            icon = event['icon']
            homeimage = event['homeimage']
            eventdatetime = event['eventdatetime']
            locked = event['locked']

            if saving is True:
                appfile = None
                homefile = None
                changed = False
                appfile_changed = False
                homefile_changed = False

                # Create a bucket to hold the event changes.
                new_event = EventConfig(version=app.config.get('VERSION'), clubid=current_user.clubid, eventid=eventid)

                locked = request.values.get('locked', False)
                if locked is not False:
                    locked = True

                if locked != event['locked']:
                    new_event.locked = locked
                    current_user.logger.debug("Updated event lock as '%s'" % new_event.locked, indent=1)
                    changed = True

                title = request.values.get("title", "").replace("'", "''")
                eventdatetime = request.values.get("eventdatetime", "")

                if len(title) == 0:
                    current_user.logger.flashlog("Edit Event failure", "Event Name cannot be empty.")
                    return redirect(url_for("main_bp.editevent"))

                if title != event['title']:
                    new_event.title = title
                    current_user.logger.debug("Updated event title as '%s'" % new_event.title, indent=1)
                    changed = True

                if len(eventdatetime) == 0:
                    current_user.logger.flashlog("Edit Event failure", "Event Date/Time cannot be blank.")
                    return redirect(url_for("main_bp.editevent"))

                if eventdatetime != event['eventdatetime']:
                    new_event.eventdatetime = eventdatetime
                    current_user.logger.debug("Updated event date/time as '%s'" % formatDateTime(new_event.eventdatetime), indent=1)
                    changed = True

                # If there was an event icon selected, fetch and verify.
                if 'appfile' in request.files:
                    appfile = request.files.get('appfile')
                    if appfile.filename != '':
                        # Verify the file is an icon of specific size.
                        if appfile.mimetype not in ["image/x-icon", "image/vnd.microsoft.icon"]:
                            current_user.logger.flashlog("Edit Event failure", "Unsupported browser icon type (not an icon).")
                            return render_template('events/editevent.html', user=user, admins=ADMINS[current_user.clubid],
                                                title=title, icon=icon, homeimage=homeimage, eventdatetime=eventdatetime, locked=locked,
                                                configdata=current_user.get_render_data())

                        new_event.icon = appfile.filename
                        icon = new_event.icon

                        current_user.logger.debug("Updated event icon as '%s'" % new_event.icon, indent=1)
                        changed = True
                        appfile_changed = True

                # If there was a home image selected, fetch and verify.
                if 'homefile' in request.files:
                    homefile = request.files.get('homefile')
                    if homefile.filename != '':
                        # Verify the file is a specific type and size.
                        SUPPORTED_FILETYPES = ["image/jpeg", "image/png"]
                        if homefile.mimetype not in SUPPORTED_FILETYPES:
                            current_user.logger.flashlog("Edit Event failure", "Unsupported home image type (must be PNG or JPEG).")
                            return render_template('events/editevent.html', user=user, admins=ADMINS[current_user.clubid],
                                                title=title, icon=icon, homeimage=homeimage, eventdatetime=eventdatetime, locked=locked,
                                                configdata=current_user.get_render_data())

                        new_event.homeimage = homefile.filename
                        homeimage = new_event.homeimage

                        current_user.logger.debug("Updated home image as '%s'" % new_event.homeimage, indent=1)
                        changed = True
                        homefile_changed = True

                # Save the change.
                if changed is True:
                    # Shove a new attribute into the event for this single purpose of updating the caches.
                    new_event.icon_changed = False
                    new_event.homeimage_changed = False

                    # Save each file that's changed.
                    if appfile_changed is True:
                        images.save_image_file("Editing an event", appfile, None, current_user.event.clubid, eventid)
                        new_event.icon_changed = True

                    if homefile_changed is True:
                        images.save_image_file("Editing an event", homefile, None, current_user.event.clubid, eventid)
                        new_event.homeimage_changed = True

                    # Update the config and database.
                    err = new_event.save_config(current_user.get_userid())
                    if err is not None:
                        current_user.logger.flashlog("Edit Event failure", err, propagate=True)

                    else:
                        # Update all the event caches.
                        EventConfig.update_event_caches(current_user.get_userid(), new_event)

                        current_user.logger.flashlog(None, "Event changes saved.", 'info', propagate=True)

                        if locked != event['locked']:
                            current_user.logger.flashlog(None, "Event has been %slocked." % ('un' if locked is False else ''), 'info')

                        current_user.logger.info("Editing an event: Operation completed")

                        if current_user.eventid == 0:
                            return redirect(url_for('main_bp.showevents'))
                        else:
                            return redirect(url_for('main_bp.editevent'))

                else:
                    current_user.logger.flashlog(None, "Changes not saved (no changes made).")

        if eventid is not None:
            return render_template('events/editevent.html', user=user, admins=ADMINS[current_user.clubid],
                                eventid=eventid, search=search, events=events, title=title, icon=icon, homeimage=homeimage, eventdatetime=eventdatetime,
                                locked=locked,
                                configdata=current_user.get_render_data())
        else:
            return render_template('events/editevent.html', user=user, admins=ADMINS[current_user.clubid],
                                eventid=eventid, search=search, events=events,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Edit Event failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Remove an event for a club.
def removeEvent(user):
    try:
        # Clear any session flags.
        def clear_session_flags():
            for flag in ['delete', 'confirm']:
                if flag in session:
                    current_user.logger.debug("Removing an event: Clearing session flag '%s'" % flag, indent=1)
                    session.pop(flag, None)

        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Remove event operation canceled.", 'info')
            clear_session_flags()

            return redirect(url_for('main_bp.removeevent'))

        current_user.logger.info("Displaying: Remove an event")

        # Get the entry ID to look up who to remove.
        eventid = request.values.get('eventid', '')
        search = request.values.get('namesearch', '')

        if len(eventid) == 0:
            eventid = None
        else:
            eventid = eventid.strip()

        if len(search) == 0:
            search = None
        else:
            search = search.strip().replace("'", "''")

        # If the event name is provided, do a lookup and build a table to feed back to the form.
        if eventid is None and search is not None and len(search) > 0:
            current_user.logger.debug("Removing an event: Searching by event name with '%s'" % search, indent=1)

            # Special keyword - this lets the user see them all.
            if search == '*':
                searchclause = ""
            else:
                searchclause = "AND LOWER(title) LIKE '%s%%'" % search.lower()

            outsql = '''SELECT eventid, title
                        FROM events
                        WHERE clubid='%d' AND eventid > 1 %s
                        ORDER BY title ASC;
                        ''' % (current_user.clubid, searchclause)
            _, result , _ = db.sql(outsql, handlekey=current_user.get_userid())

            # The return data is the first 'dbresults' in the list.
            result = result[0]

            events = []
            for r in result:
                events.append([r['eventid'], r['title']])

            # Nothing found.
            if len(events) == 0:
                current_user.logger.flashlog('Remove Event failure', "No Events with a name matching '%s' were found." % search)
                # Redirect to the edit page so we don't save the previous entry data.
                return redirect(url_for('main_bp.removeevent'))

        else:
            events = None

        # If an club ID has been specified, verify it and get the record.
        if eventid is not None and len(eventid) > 0:
            # Verify the format (numeric).
            try:
                eventid = int(eventid)
            except:
                current_user.logger.flashlog("Remove Event failure", "Event ID must be a number.")
                return redirect(url_for('main_bp.removeevent'))

            current_user.logger.debug("Removing an event: Searching for Event ID %s" % eventid, indent=1)

            # Fetch the event matching the event ID.  Event ID is unique.
            outsql = '''SELECT *
                        FROM events
                        WHERE eventid='%d';
                        ''' % eventid
            _, result , _ = db.sql(outsql, handlekey=current_user.get_userid())

            # The return data is the first 'dbresults' in the list.
            result = result[0]
            if len(result) == 0:
                current_user.logger.flashlog("Remove Event failure", "Event ID %s was not found." % eventid)

                # Redirect to the edit page so we don't save the previous entry data.
                return redirect(url_for('main_bp.removeevent'))

            event = result[0]

            # The process is:
            # - Initiate via 'Submit'
            #   - Set a 'set' flag in the session
            # - Confirm via 'Confirm'
            #   - Set a 'confirm' flag in the session
            # - Execute the delete
            # - Confirm one more time as it's totally destructive
            delete_request = False
            confirm_request = False
            saving = False

            savebutton = request.values.get('savebutton', None)
            if savebutton is not None:

                if savebutton == 'delete':
                    current_user.logger.debug("Removing an event: Delete requested for Event ID %d" % eventid, propagate=True, indent=1)
                    session['delete'] = True

                    # Force reaquiring of confirmation.
                    if 'confirm' in session:
                        session.pop('confirm', None)

                    delete_request = True

                elif savebutton == 'confirm' and 'delete' in session:
                    current_user.logger.debug("Removing an event: Confirm requested for Event ID %d" % eventid, propagate=True, indent=1)
                    session['confirm'] = True

                    delete_request = True
                    confirm_request = True

                else:
                    if all(x in session for x in ['delete', 'confirm']):
                        saving = True
            else:
                # Force-clear session flags on fresh page load.
                clear_session_flags()

            if saving is True:
                # Search all users to see if anyone is logged into an event (has the event ID in their event cache).
                users = []
                for user_id in ALLUSERS:
                    sessions = ALLUSERS.get(user_id, {})
                    for user_uuid in sessions:
                        userobj = ALLUSERS[user_id][user_uuid]
                        if userobj.event is not None and userobj.event.eventid == eventid:
                            users.append(userobj.id)

                if len(users) > 0:
                    current_user.logger.flashlog("Remove Event failure", "Events cannot be removed while users are logged in.")
                    for u in users:
                        current_user.logger.flashlog("Remove Event failure", "User: '%s'" % u, highlight=False, indent=True)

                    return redirect(url_for('main_bp.removeevent'))

                current_user.logger.info("Removing an event: Removing Event ID %d" % eventid, indent=1)

                # Force-clear session flags since we're done.
                clear_session_flags()
                delete_request = False
                confirm_request = False

                # Do the needful.
                err = remove_event_data(current_user.get_userid(), current_user.clubid, eventid)
                if err is not None:
                    current_user.logger.flashlog("Remove Event failure", "Failed to remove event data:", highlight=True, propagate=True)
                    current_user.logger.flashlog("Remove Event failure", err, propagate=True)
                else:
                    current_user.logger.flashlog(None, "Removed Event %d (%s)." % (eventid, event['title']), 'info', large=True, highlight=True, propagate=True)
                    current_user.logger.info("Removing an event: Operation completed")

                return redirect(url_for('main_bp.showevents'))

            return render_template('events/removeevent.html', user=user, admins=ADMINS[current_user.clubid],
                                eventid=eventid, search=search, events=events,
                                title=event['title'], icon=event['icon'], homeimage=event['homeimage'], eventdatetime=event['eventdatetime'],
                                locked=event['locked'],
                                delete_request=delete_request, confirm_request=confirm_request,
                                configdata=current_user.get_render_data())
        else:
            return render_template('events/removeevent.html', user=user, admins=ADMINS[current_user.clubid],
                                eventid=eventid, search=search, events=events,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Remove Event failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))
