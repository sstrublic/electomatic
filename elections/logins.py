#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import traceback

from elections import db
from elections import app, getRemoteAddr
from elections import loggers, login_manager
from elections import ALLUSERS, ALLSOURCES
from elections import EVENTCONFIG

from flask import redirect, render_template, url_for, request, session, make_response
from flask_login import login_user, logout_user, current_user
from elections.log import AppLog
from elections.users import User
from elections.events import EventConfig

@login_manager.user_loader
def load_user(user_id):

    # Build the ID we will use for reference.
    # The session caches the chosen club ID at login time.
    clubid = session.get('clubid', None)
    if session.get('siteadmin', False) is True and clubid != 1:
        clubid = 0

    if clubid is not None:
        # Look up the user in the all-users cache by the UUID stored in the session, assuming there is one.
        # If there isn't, the user han't been previously authenticated or their session timed out.
        user_uuid = session.get('uuid', None)
        user = User.get_user(clubid, user_id, user_uuid)

        if user is not None:
            # Verify the user name and club ID in the user object.  If the siteadmin, we already found them 'specially'.
            # This seems a little silly, since we've already validated it - but the login manager needs it so we can return
            # the User object for this request.  We use the all-users session cache (looked up when finding the user) to
            # reduce overhead and prevent hammering of the database.
            if user.siteadmin is True or (user.clubid == int(clubid) and user.id == user_id):
                if user.is_authenticated():
                    return user

            loggers[AppLog.get_id(clubid)].warning("User '%s' has not been authenticated" % user_id, indent=1)

        else:
            loggers[AppLog.get_id(clubid)].warning("Unable to locate session for user '%s'" % user_id, indent=1)

    else:
        loggers[AppLog.get_id(clubid)].debug("User '%s' does not have a prior session" % user_id, indent=1)

    # Clear session variables when not found or authenticated.
    clear_session_variables()

    return None


def publicLogin():
    logger = loggers[AppLog.get_id()]

    logger.info("Public login request started")

    # The public key will be part of the login.
    publickey = request.values.get('publickey', None)
    if publickey is None:
        logger.critical("Public login: Public key not specified")
        return redirect(url_for('main_bp.unauthorized'))

    else:
        logger.info("Public login: Public key specified as '%s'" % publickey, indent=1)

        # Find the user by their public key.
        userdata = User.find_user_by_public_key(publickey)
        if userdata is not None:
            # We found them -
            username = userdata['username']
            clubid = userdata['clubid']
            eventid = userdata['eventid']
            active = userdata['active']

            # If the user is not active, deny login.
            if active is False:
                logger.critical("Public login: Public user '%s' is not active" % username)
                return redirect(url_for('main_bp.unauthorized'))

            user = User(username, fullname=userdata['fullname'], usertype=userdata['usertype'], clubid=clubid, eventid=eventid,
                        active=userdata['active'], siteadmin=False, clubadmin=False, publickey=publickey)
            if user is None:
                logger.critical("Public login: Failed to create user object for user '%s'!" % username)
                return redirect(url_for('main_bp.unauthorized'))

            # If they are active, then they're authorized as public users.

            # Fetch any previous session uuid.
            session_uuid = session.get('uuid', None)

            # Log in the user, with a default expiration time before logout.
            login_user(user)

            user.set_login_status(True)
            user.authenticated = True

            # Overwrite the club ID.  This is harmless for single-tenant,
            # but ensures the multi-tenant club ID is always right.
            user.set_club(clubid)

            # Sent the event configuration for this event.
            user.set_event(eventid)

            # Now we've got a user log instance... use it!
            user.logger.info("Logged in public user '%s'" % username)

            # Update the event club ID to what was entered.
            # This is okay because we always have an event (even if it is a copy of the default/global event).
            user.event.clubid = clubid

            # Add the user session data to the caches.
            if session_uuid is None:
                session_uuid = User.add_to_object_cache(user)

            if session_uuid is not None:
                # Cache the club ID in the session for future reference.
                # We can't always rely on the current_user object at the login/logout stage.
                session['clubid'] = clubid

                # Cache the siteadmin flag state as False (public users are never siteadmins).
                session['siteadmin'] = False

                # If not already so, the user will eventually pick an event, which will set the event information.
                session['eventid'] = eventid

                # This is a direct login to an event.
                session['event_login'] = True

                # This was a login from the public login interface (QR code based).
                session['public_login'] = True

                # Cache the session's UUID.
                session['uuid'] = session_uuid

                # Public users always log into the main page.
                session['prev_url'] = None

                return redirect(url_for('main_bp.index'))

            else:
                loggers[AppLog.get_id(clubid, eventid)].flashlog("Login Failed", "Login failed.", propagate=True)
                user.set_event(0)

        else:
            eventid = int(request.values.get('eventid', '0'))
            classid = int(request.values.get('classid', '0'))

        # No good.
        return redirect(url_for('main_bp.unauthorized'))


# Log in a user.
def loginUser(clubs=True):
    logger = loggers[AppLog.get_id()]

    url = 'main_bp.login' if clubs is False else 'main_bp.clublogin'

    try:
        if request.values.get('cancelbutton'):
            logger.flashlog(None, "Login operation canceled.", 'info')
            return redirect(url_for(url))

        logger.info("Displaying: Login page")

        # If performing a login, set this for later.
        saving = False
        if request.values.get('savebutton'):
            logger.info("%s login request started" % ("Event" if clubs is False else "Club / Event"))
            saving = True

        if saving is True:
            # Default event ID to None so we can search for a unique event ID for login.
            eventid = None

            # In a multi-tenant environment, fetch the club/event ID.
            # A standalone install will default to club ID 1 and log directly into the Event.
            if app.config.get('MULTI_TENANCY') is True:
                clubid = request.values.get('clubid')
            else:
                clubid = app.config.get('DEFAULT_CLUB_ID', 1)

            # Get the user name and password.
            username = request.values.get('username', '').strip()
            userpass = request.values.get('passwd', '')

            if len(username) > 0:
                try:
                    clubid = int(clubid)
                except:
                    logger.flashlog("Login failure", "%sEvent ID must be a number." % ('Club / ' if clubs is True else ''))
                    return redirect(url_for(url))

                # Default to expecting to log in to a club.
                session['event_login'] = False

                # This is not a login from the public login interface (QR code based).
                session['public_login'] = False

                # If this is from the clubs login page, we we search by Club ID first.
                if clubs is True:
                    # Try to find any clubs with this ID.
                    # For a standalone install, this will succeed with club ID 1.
                    outsql = '''SELECT *
                                FROM clubs
                                WHERE clubid='%d';
                            ''' % clubid
                    _, result, _ = db.sql(outsql, handlekey='system')

                    # The result is the first 'dbresults' in the list.
                    result = result[0]
                    if len(result) == 0:
                        # If no Club ID, check for the unique event ID.
                        logger.debug("No Club ID %d found: searching for unique Event ID..." % clubid, indent=1)
                else:
                    logger.debug("Searching for unique Event ID...", indent=1)
                    result = []

                if len(result) == 0:
                    outsql = '''SELECT *
                                FROM events
                                WHERE eventid='%d';
                            ''' % clubid
                    _, result, _ = db.sql(outsql, handlekey='system')

                    # The result is the first 'dbresults' in the list.
                    result = result[0]

                    if len(result) == 0:
                        logger.flashlog("Login failure", "There is no %sEvent with ID %d." % ('Club or ' if clubs is True else '', clubid))
                        return redirect(url_for(url))
                    else:
                        # The event is the first and only entry in the results.
                        event = result[0]

                        # Pull the club and event ID from the record.
                        clubid = event['clubid']
                        eventid = event['eventid']

                        # Cache that we logged in directly to the event versus through the club/event pages.
                        # This lets us decide if we should show 'logout' or 'exit'.
                        if eventid != 0:
                            session['event_login'] = True

                        loggers[AppLog.get_id(clubid, eventid)].debug("Located Event ID %d with Club ID %d" % (eventid, clubid), indent=1)

                # In a multi-tenant environment, set the event ID to 0 to require selection of an event.
                # A standalone install will default to event ID 1.
                if app.config.get('MULTI_TENANCY') is True:
                    if eventid is None:
                        # No event was found from the unique event ID.
                        # At this point, there is no event - so default to 0.
                        eventid = 0
                else:
                    eventid = app.config.get('DEFAULT_EVENT_ID', 1)

                loggers[AppLog.get_id(clubid, eventid)].info("Log in request started for user '%s'" % (username))

                # Find the user that belongs to this.
                user = None
                user_id = '%d_%s' % (clubid, username)
                siteadmin = False
                err = ''
                found_cookie = False

                # See if the requestor has a cookie with the session UUID.
                session_uuid = request.cookies.get('uuid')
                if session_uuid is not None:
                    loggers[AppLog.get_id(clubid, eventid)].info("Found session cookie '%s' for user '%s'" % (session_uuid, username), indent=1)
                    found_cookie = True
                else:
                    # See if the session has a UUID cached.
                    session_uuid = session.get('uuid', None)
                    if session_uuid is not None:
                        session.pop('uuid')

                if user_id not in ALLUSERS:
                    loggers[AppLog.get_id(clubid, eventid)].info("Did not find user '%s' for Club ID %d: checking siteadmin" % (username, clubid), indent=1)

                    # Try again as a siteadmin.
                    user_id = '0_%s' % username
                    siteadmin = True

                if user_id in ALLUSERS:
                    verified = False

                    # if the session has a UUID and it's in the system. try to fetch it.
                    # Otherwise, build a User object with the retrieved data.
                    if session_uuid is not None:
                        user = User.find_in_object_cache(user_id, session_uuid)

                    # If the user session doesn't exist, fetch it from the database.
                    if user is None:
                        # Find the user.
                        if siteadmin is True:
                            userdata = User.find_user(username, 0)
                            user_clubid = 0
                        else:
                            userdata = User.find_user(username, clubid)
                            user_clubid = clubid

                        if userdata is not None:
                            loggers[AppLog.get_id(clubid, eventid)].info("Located user '%s' for Club ID %d" % (username, user_clubid), indent=1)

                            # If the user is not authorized for this event, stop here.
                            if userdata['eventid'] != 0 and userdata['eventid'] != eventid:
                                if eventid == 0:
                                    err = "User '%s' is not authorized for Club ID %d" % (username, clubid)
                                else:
                                    err = "User '%s' is not authorized for Event ID %d" % (username, eventid)
                            else:
                                user = User(username, fullname=userdata['fullname'], usertype=userdata['usertype'], clubid=user_clubid, eventid=eventid,
                                            active=userdata['active'], siteadmin=userdata['siteadmin'], clubadmin=userdata['clubadmin'], publickey=userdata['publickey'],
                                            user_uuid=session_uuid)
                    else:
                        loggers[AppLog.get_id(clubid, eventid)].info("Using cached session '%s'" % session_uuid, indent=1)

                if user is not None:
                    # If the user does not have club level login rights, they must log directly into the event.
                    # This allows for Club admins and event admins.
                    if user.clubadmin is False and eventid == 0:
                        loggers[AppLog.get_id(clubid, eventid)].error("User '%s' for Club ID %d does not have Club level access" % (username, clubid), indent=1)
                        err = "User does not have Club level login permissions"
                    else:
                        if user.is_authenticated():
                            verified = True
                        else:
                            # Site admins need their club ID set to 0 for this authentication if it's not the single-tenant install.
                            # This will be reset when authenticated.
                            if user.siteadmin is True and clubid > 1:
                                user.clubid = 0

                            verified, err = user.verify_user(userpass)

                    if verified is True:
                        clear_session_login_variables()

                        # Log in the user, with a default expiration time before logout.
                        login_user(user)

                        user.set_login_status(True)

                        # Overwrite the club ID.  This is harmless for single-tenant,
                        # but ensures the multi-tenant club ID is always right.
                        user.set_club(clubid)

                        # Sent the event configuration for this event.
                        user.set_event(eventid)

                        # Update the event club ID to what was entered.
                        # This is okay because we always have an event (even if it is a copy of the default/global event).
                        user.event.clubid = clubid

                        # Add the user session data to the caches.  If we have a UUID, use it.
                        session_uuid = User.add_to_object_cache(user, session_uuid)

                        # Now we've got a user log instance... use it!
                        user.logger.info("Logged in user '%s'" % username, propagate=True)

                    if verified is True and session_uuid is not None:
                        # Cache the club ID in the session for future reference.
                        # We can't always rely on the current_user object at the login/logout stage.
                        session['clubid'] = clubid

                        # Cache the siteadmin flag state for verification of site-admins after initial login.
                        session['siteadmin'] = user.siteadmin

                        # If not already so, the user will eventually pick an event, which will set the event information.
                        session['eventid'] = eventid

                        session['uuid'] = session_uuid

                        # Reset session's logfile offset.
                        session['logfile_offset'] = 0

                        prev_url = session.get('prev_url', None)
                        session['prev_url'] = None

                        if prev_url is not None and all(x not in prev_url for x in ['login', 'images']):
                            resp = make_response(redirect(prev_url))
                        else:
                            resp = make_response(redirect(url_for('main_bp.index')))

                        # Set a tracking cookie for this login.  This will be used for redirect to the previous URL
                        # after a session expires and a new login is completed.
                        if found_cookie is False:
                            resp.set_cookie('uuid', str(session_uuid), max_age=86400)

                        return resp

                    else:
                        loggers[AppLog.get_id(clubid, eventid)].flashlog("Login Failed", "Login failed: %s." % err, propagate=True)
                        user.set_event(0)

                        # Reset the site admin cached user's club ID to 0 for next login.
                        if user.siteadmin is True:
                            user.set_club(0)

                        # Note we leave the session variables cached.
                else:
                    if len(err) == 0:
                        if clubs is True:
                            err = "User '%s' not found for %s ID %d" % (username, ("Event" if session['event_login'] is True else "Club"), clubid)
                        else:
                            err = "User '%s' not found for Event ID %d" % (username, eventid)

                    loggers[AppLog.get_id(clubid, eventid)].flashlog("Login Failed", "%s." % err, propagate=True)
            else:
                logger.flashlog("Login Failed", "No user name was specified.")

        return render_template('users/login.html', user=None, tenancy=app.config.get('MULTI_TENANCY'), clubs=clubs, configdata=EVENTCONFIG.get_event_render_data())

    except Exception as e:
        logger.flashlog("Log In failure", "Exception: %s" % str(e), propagate=True)
        logger.error("Unexpected exception:")
        logger.error(traceback.format_exc())

        # Redirect to the page so we don't save the previous entry data.
        return redirect(url_for(url))


# Clear session variables.
def clear_session_variables():
    session['clubid'] = None
    session['eventid'] = None
    session['prev_url'] = None

    session['siteadmin'] = False
    session['event_login'] = False
    session['logfile_offset'] = 0

    session['_user_id'] = None
    session['uuid'] = None


# Clear variables that should be reset at each login.
def clear_session_login_variables():
    session['logfile_offset'] = 0

    session['ownersort'] = None


# Log out a user.
def logoutUser(msg=None):
    logger = loggers[AppLog.get_id()]

    try:
        if msg is None:
            if session.get('public_login', False) is True:
                msg = "Your public access session has expired."
            else:
                msg = "You have been logged out."

        logger.info("Displaying: Logout page")

        user = current_user.get_id()
        if user is None or current_user.is_active is False:
            logger.info("Log out request started")
            logger.flashlog(None, msg, level='info')

            # Clear the session.
            clear_session_variables()

            logger.info("Log out request completed (no user)")

        else:
            # Site admins will have a club ID of 0.
            if current_user.siteadmin is True:
                clubid = 0
            else:
                clubid = current_user.clubid

            # Stash a handle for the user's logger to show the logout completion after
            # the user is actually logged out.
            user_logger = current_user.logger

            user_logger.info("Log out request started")

            current_user.authenticated = False

            # Invalidate the user in the all-users cache by removing their object.
            user_id = '%d_%s' % (clubid, user)
            user_uuid = session.get('uuid', None)

            userobj = User.find_in_object_cache(user_id, user_uuid)

            # If the user object still exists, clear it out.
            # It may have been removed during a flush.
            if userobj is not None:
                # Pull them from the object cache.
                User.remove_from_object_cache(user_id, user_uuid, userobj)

                # Even though we're destroying the user object, clear it out for good measure.
                userobj.authenticated = False

                user_logger.info("Clearing user club and event data", indent=1)

                userobj.set_event(0)

                # Also set a siteadmin's club ID back to 0 if not the single-tenant install.
                if userobj.siteadmin is True and clubid > 1:
                    userobj.set_club(0)

                userobj.set_login_status(False)

            # Clear the session.
            clear_session_variables()

            user_logger.flashlog(None, msg, level='info')
            user_logger.info("Log out request completed for user '%s'" % user, propagate=True)

            # Now remove the user's login info, which clears the current_user object.
            logout_user()

        return render_template('users/logout.html', user=None, configdata=EVENTCONFIG.get_event_render_data())

    except Exception as e:
        logger.flashlog("Log Out failure", "Exception: %s" % str(e), propagate=True)
        logger.error("Unexpected exception:")
        logger.error(traceback.format_exc())

        # On failure, we're logging the user out anyhow for safekeeping.
        logout_user()

        # The user will be sent to 'unauthorized'.
        resp = make_response(redirect(url_for('main_bp.index')))
        resp.set_cookie('uuid', '', expires=0)
        return resp
