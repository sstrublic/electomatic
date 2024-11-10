#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import os
import traceback

from flask import Blueprint, render_template, request, session, abort, send_file, make_response
from datetime import datetime

from elections import app, getRemoteAddr
from elections import ALLSOURCES, ALLUSERS, ADMINS
from elections import EVENTCONFIG
from elections import login_manager
from elections import loggers

from flask import redirect, url_for
from flask_login import login_required, fresh_login_required, current_user

# Methods for doing things.
import elections.logins as logins
import elections.users as users
import elections.configdata as configdata
import elections.clubs as clubs
import elections.events as events
import elections.logdata as logdata
import elections.docs as docs
import elections.ballotitems as ballotitems
import elections.candidates as candidates
import elections.voters as voters
import elections.votes as votes

from elections.log import AppLog

from werkzeug.exceptions import HTTPException, BadRequest

# Blueprint Configuration
main_bp = Blueprint(
    'main_bp', __name__,
    template_folder='templates',
    static_folder='static'
)

# Path to club level images (like user QR codes).
@main_bp.route('/images/<clubid>/<filename>', methods=['GET', 'POST'])
def clubimages(clubid, filename):
    # If there are spaces in the filename, convert them to underscores.
    filename = filename.replace(' ', '_')

    # Check if the requested image exists on disk.
    filepath = os.path.join(os.getcwd(), app.config.get('IMAGES_UPLOAD_FOLDER'), clubid, filename)

    if os.path.exists(filepath):
        # Send the existing image.
        return send_file(os.path.join(app.config.get('IMAGES_FOLDER'), clubid, filename) )
    else:
        # Send the default 'X' image.
        return send_file(os.path.join(app.config.get('STATIC_FOLDER'), app.config.get('MISSING_IMAGE')) )


# Path to images.
@main_bp.route('/images/<clubid>/<eventid>/<filename>', methods=['GET', 'POST'])
def images(clubid, eventid, filename):
    # If there are spaces in the filename, convert them to underscores.
    filename = filename.replace(' ', '_')

    # Check if the requested image exists on disk.
    filepath = os.path.join(os.getcwd(), app.config.get('IMAGES_UPLOAD_FOLDER'), clubid, eventid, filename)

    if os.path.exists(filepath):
        # Send the existing image.
        return send_file(os.path.join(app.config.get('IMAGES_FOLDER'), clubid, eventid, filename) )
    else:
        # Send the default 'X' image.
        return send_file(os.path.join(app.config.get('STATIC_FOLDER'), app.config.get('MISSING_IMAGE')) )


# Path to entry images (QR codes).
@main_bp.route('/images/<clubid>/<eventid>/entries/<filename>', methods=['GET', 'POST'])
def entryimages(clubid, eventid, filename):
    # If there are spaces in the filename, convert them to underscores.
    filename = filename.replace(' ', '_')

    # Check if the requested image exists on disk.
    filepath = os.path.join(os.getcwd(), app.config.get('IMAGES_UPLOAD_FOLDER'), clubid, eventid, 'entries', filename)

    if os.path.exists(filepath):
        # Send the existing image.
        return send_file(os.path.join(app.config.get('IMAGES_FOLDER'), clubid, eventid, app.config.get('ENTRY_IMAGES_FOLDER'), filename) )
    else:
        # Send the default 'X' image.
        return send_file(os.path.join(app.config.get('STATIC_FOLDER'), app.config.get('MISSING_IMAGE')) )


# Determine where to send people when unauthorized.
def unauthorized_redirect():
    # For new sessions with no user, we default to 'not found' unless a specific login URL was provided.
    if request.cookies.get('uuid', None) is None and session.get('uuid', None) is None:
        return render_template('404.html'), 404

    else:
        # For public logins, redirect to the logout page so they don't see the
        # login page by default.
        if session.get('public_login', False) is False:
            return redirect(url_for('main_bp.login'))
        else:
            return redirect(url_for('main_bp.logout'))


@login_manager.unauthorized_handler
@main_bp.route('/unauthorized', methods=['GET', 'POST'])
def unauthorized():
    user = current_user.get_id()
    if user is not None:
        clubid = current_user.clubid
        eventid = 0

        # Get the current event if it's available.
        event = EVENTCONFIG
        configdata=event.get_event_render_data()

        if current_user.is_active:
            event = current_user.event
            eventid = event.eventid
            configdata = current_user.get_render_data()

        now = datetime.now()
        try:
            loggers[AppLog.get_id(clubid, eventid)].critical("[%s]: User not authorized: Club ID %d: User='%s'" % (now.strftime("%m-%d-%Y %H:%M:%S"), clubid, user))
        except:
            loggers[AppLog.get_id()].critical("[%s]: User not authorized: Club ID %d: User='%s'" % (now.strftime("%m-%d-%Y %H:%M:%S"), clubid, user))

        # Use the global 'not-authorized' app config instance.
        return render_template('unauthorized.html', user=user, admins=ADMINS[clubid], configdata=configdata), 401

    else:
        return unauthorized_redirect()


# Default logout end-session message.
def sessionEnded(user):
    loggers[AppLog.get_id()].warning("Session ended for user '%s'" % user)
    return logins.logoutUser("Your session has ended.")


# Generic error handler.
@main_bp.errorhandler(BadRequest)
def handle_bad_request(e):
    return "Bad Request", 400


@main_bp.errorhandler(Exception)
def handle_exception(e):
    # Pass through HTTP errors
    if isinstance(e, HTTPException):
        return e

    # Now you're handling non-HTTP exceptions only
    return abort(404)


# Log incoming request information.
@main_bp.before_request
def before():
    remote_addr = getRemoteAddr(request)

    # If the current user is an actual user (meaning, is_active is a function, not False),
    # then check for expiration and scrape the user object cache for this user to remove old sessions.
    if current_user.is_active:
        now = datetime.now()
        user = current_user.get_id()
        user_id = current_user.get_userid()
        user_uuid = current_user.get_uuid()

        # Filter out 'get image' messages because they get spammy.
        if all(x not in request.full_path for x in ['/images', '/showlog']):
            current_user.logger.debug('>>> [%s %s]' % (request.method, request.full_path), ipaddr=remote_addr, indent=1)

        try:
            # If a session timeout is in place, check for timeout and flush.
            idletime = app.config.get('SESSION_IDLE_TIME')
            if idletime > 0:

                try:
                    # Check the user caches.
                    # Note that any request will trigger this action for a given user.

                    # Get a list of all object UUIDs for this user.
                    # We have to iterate there instead of on the dict itself so we can remove items.
                    uuids_list = list(ALLUSERS.get(user_id, {}))
                    if user_uuid not in uuids_list:
                        current_user.logger.debug("User '%s' (%s) not present in cache" % (user, user_uuid))

                    for uuid in uuids_list:

                        # This log could get really spammy.
                        # current_user.logger.debug("Checking user object '%s'" % user_uuid)

                        userobj = ALLUSERS[user_id][uuid]

                        last_active = userobj.last_updated

                        delta = now - last_active.replace(tzinfo=None)
                        if delta.seconds > idletime:
                            # For good measure, unauthenticate the user - in case there is still someone
                            # holding on to this object.
                            userobj.authenticated = False
                            userobj.set_login_status(False)

                            # Remove from cache.
                            current_user.logger.warning("Removing stale user object '%s' (age: %s)" % (uuid, str(delta)))
                            users.User.remove_from_object_cache(user_id, uuid, userobj)

                except Exception as e:
                    # Log the failure.
                    current_user.logger.critical("Failed to remove user object '%s': %s" % (uuid, str(e)))
                    pass

                # Get the last action time from the session and compare to now().
                # If the time is longer than the session timeout, log the user out.
                last_active = current_user.last_updated
                if last_active is not None:
                    delta = now - last_active.replace(tzinfo=None)
                    if delta.seconds > idletime:
                        msg = "Your session has expired."
                        if session.get('public_login', False) is True:
                            msg = "Your public access session has expired."

                        return logins.logoutUser(msg)

        except:
            # On failure, it's because there is no last-active action time or there was an error in the compare.
            current_user.logger.debug("Failed to check user caches:")
            current_user.logger.error(traceback.format_exc())

        # Store the last action time as now().
        try:
            current_user.last_updated = now
        except:
            pass
    else:
        loggers[AppLog.get_id()].debug('>>> [%s %s] (inactive)' % (request.method, request.full_path), ipaddr=remote_addr, indent=1)


# Log outgoing result information.
@main_bp.after_request
def after(response):
    # Filter out '304' (not modified) messages because they get spammy.
    if '304' in response.status:
        return response

    # Filter out images and log messages.
    if any(x in request.full_path for x in ['/images', '/showlog']):
        return response

    remote_addr = getRemoteAddr(request)
    critical = False

    # Certain responses should get logged as critical since we aren't expecting them and want to see.
    if any(x in response.status for x in ['401', '404', '500']):
        critical = True

    if current_user.is_active:
        if critical:
            current_user.logger.critical('<<< [%s %s] %s' % (request.method, request.full_path, response.status), ipaddr=remote_addr, indent=1)
        else:
            current_user.logger.debug('<<< [%s %s] %s' % (request.method, request.full_path, response.status), ipaddr=remote_addr, indent=1)
    else:
        if critical:
            loggers[AppLog.get_id()].critical('<<< [%s %s] %s (inactive)' % (request.method, request.full_path, response.status), ipaddr=remote_addr, indent=1)
        else:
            loggers[AppLog.get_id()].debug('<<< [%s %s] %s (inactive)' % (request.method, request.full_path, response.status), ipaddr=remote_addr, indent=1)

    # Save the current URL as the last URL visited.  We can do this since we always loop
    # through here to authenticate every page.  But not for certain pages that would create an
    # infinite loop of being unable to access anything.
    if all(x not in request.full_path for x in ['login', 'logout', 'unauthorized', 'clubs', 'images', 'vote']):
        session['prev_url'] = request.full_path

    return response


# Login page.
@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    return logins.loginUser(clubs=False)


# Public user login page.
@main_bp.route('/vote', methods=['GET', 'POST'])
def vote():
    return votes.publicVote()


# Clubs login page.
if app.config.get('MULTI_TENANCY') is True:
    @main_bp.route('/clubs', methods=['GET', 'POST'])
    def clublogin():
        return logins.loginUser(clubs=True)


# Logout.
@login_required
@main_bp.route('/logout')
def logout():
    return logins.logoutUser()


# Exit to events page.
if app.config.get('MULTI_TENANCY') is True:
    @login_required
    @main_bp.route('/exit', methods=['GET', 'POST'])
    def exit():
        user = current_user.get_id()

        # Generic catchall in case the current user has been invalidated.
        if current_user.is_active is False:
            return sessionEnded(user)

        clubid = current_user.clubid

        session['eventid'] = None
        session['prev_url'] = None

        # Invalidate the user in the user cache.
        # Site admins need to revert to club ID 0.
        if current_user.siteadmin is True:
            # Get the user from the session UUID.
            if current_user.clubid == 1:
                userobj = users.User.get_user(1, user, session.get('uuid', None))
            else:
                userobj = users.User.get_user(0, user, session.get('uuid', None))

        else:
            # Get the user from the session UUID.
            userobj = users.User.get_user(clubid, user, session.get('uuid', None))

        if userobj is not None:
            current_user.logger.info("Returning to events page for Club ID %d" % clubid)
            userobj.set_event(0)
            return redirect(url_for('main_bp.showevents'))
        else:
            loggers[AppLog.get_id(clubid)].error("No user object for Club ID %d: Logging out: User = '%s'" % (clubid, user))
            return redirect(url_for('main_bp.logout'))


# Main page that redirects to other options.
@main_bp.route('/', methods=['GET', 'POST'])
def root():
    if current_user.is_active:
        return redirect(url_for('main_bp.index'))
    else:
        # For the main (root) link we either allow a redirect to a login page or return 404.
        return unauthorized_redirect()


@main_bp.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    # At this point, there should always be a user config block in the current user for this session.
    eventid = current_user.event.eventid

    current_user.logger.info("Displaying main page")

    # If the user is a siteadmin in siteadmin mode (club 0), display the 'show clubs' page as the main page.  Allow selection of a club.
    # If the clubid is nonzero but the eventid is, display the 'show events' page as the main page.  Allow selection of an event.
    if app.config.get('MULTI_TENANCY') is False:
        return render_template('index.html', user=user, admins=ADMINS[clubid], configdata=current_user.get_render_data())
    else:
        if clubid == 0:
            return clubs.showClubs(user)
        elif eventid == 0:
            return events.showEvents(user)
        else:
            return render_template('index.html', user=user, admins=ADMINS[clubid], configdata=current_user.get_render_data())


# Add a club.
if app.config.get('MULTI_TENANCY') is True:
    @main_bp.route('/clubs/addclub', methods=['GET', 'POST'])
    @login_required
    def addclub():
        user = current_user.get_id()

        # Generic catchall in case the current user has been invalidated.
        if current_user.is_active is False:
            return sessionEnded(user)

        # Must be club ID zero and a site admin.
        clubid = current_user.clubid
        if clubid != 0 or current_user.siteadmin is False:
            return unauthorized()

        return clubs.addClub(user)


# Edit a club.
if app.config.get('MULTI_TENANCY') is True:
    @main_bp.route('/clubs/editclub', methods=['GET', 'POST'])
    @login_required
    def editclub():
        user = current_user.get_id()

        # Generic catchall in case the current user has been invalidated.
        if current_user.is_active is False:
            return sessionEnded(user)

        # Must be a club admin (which also covers siteadmins).
        clubid = current_user.clubid
        if current_user.clubadmin is False:
            return unauthorized()

        return clubs.editClub(user, clubid)


# Remove a club.
if app.config.get('MULTI_TENANCY') is True:
    @main_bp.route('/clubs/removeclub', methods=['GET', 'POST'])
    @login_required
    def removeclub():
        user = current_user.get_id()

        # Generic catchall in case the current user has been invalidated.
        if current_user.is_active is False:
            return sessionEnded(user)

        # Must be club ID zero and a site admin.
        clubid = current_user.clubid
        if clubid != 0 or current_user.siteadmin is False:
            return unauthorized()

        # Operation not supported at this time.
        return clubs.removeClub(user)


# Show a club.
if app.config.get('MULTI_TENANCY') is True:
    @main_bp.route('/clubs/showclub', methods=['GET', 'POST'])
    @login_required
    def showclub():
        user = current_user.get_id()

        # Generic catchall in case the current user has been invalidated.
        if current_user.is_active is False:
            return sessionEnded(user)

        clubid = current_user.clubid

        # Must be a club admin (which also covers siteadmins).
        clubid = current_user.clubid
        if current_user.clubadmin is False:
            return unauthorized()

        return clubs.showClub(user, clubid)


# Show clubs.
if app.config.get('MULTI_TENANCY') is True:
    @main_bp.route('/clubs/showclubs', methods=['GET', 'POST'])
    @login_required
    def showclubs():
        user = current_user.get_id()

        # Generic catchall in case the current user has been invalidated.
        if current_user.is_active is False:
            return sessionEnded(user)

        # Must be a club admin (which also covers siteadmins) and the event ID must be 0
        # (not logged into an event).
        clubid = current_user.clubid
        event = current_user.event
        if current_user.clubadmin is False or (event is not None and event.eventid != 0):
            return unauthorized()

        # If reloading (going home), then reset the user's clubid to 0.
        reload = request.values.get('reload', False)
        reload = True if str(reload).lower() == 'true' else False
        if reload is True:
            # Reset session's logfile offset.
            session['logfile_offset'] = 0

            if current_user.clubid > 1:
                current_user.set_club(0)

            return redirect(url_for('main_bp.showclubs'))
        else:
            # Must be club ID 0 or 1.
            if clubid > 1:
                return unauthorized()

        return clubs.showClubs(user)


# Add an event.
if app.config.get('MULTI_TENANCY') is True:
    @main_bp.route('/clubs/addevent', methods=['GET', 'POST'])
    @login_required
    def addevent():
        user = current_user.get_id()

        # Generic catchall in case the current user has been invalidated.
        if current_user.is_active is False:
            return sessionEnded(user)

        # Must be a club admin (which covers siteadmins).
        # Cannot be club ID 0 (have not selected a club) or logged into an event.
        clubid = current_user.clubid
        event = current_user.event
        if current_user.clubadmin is False or clubid == 0 or (event is not None and event.eventid != 0):
            return unauthorized()

        return events.addEvent(user)


# Edit an event (club level.
if app.config.get('MULTI_TENANCY') is True:
    @main_bp.route('/clubs/editevent', methods=['GET', 'POST'])
    @login_required
    def editclubevent():
        user = current_user.get_id()

        # Generic catchall in case the current user has been invalidated.
        if current_user.is_active is False:
            return sessionEnded(user)

        clubid = current_user.clubid

        # Cannot be club ID 0 (have not selected a club).
        # Must be an admin user with club admin rights.
        if current_user.clubadmin is False or clubid == 0 or user not in ADMINS[clubid]:
            return unauthorized()

        return events.editEvent(user)


@main_bp.route('/events/editevent', methods=['GET', 'POST'])
@login_required
def editevent():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    # Cannot be club ID 0 (have not selected a club).
    # Must be an admin user with club admin rights.
    if current_user.clubadmin is False or clubid == 0 or user not in ADMINS[clubid]:
        return unauthorized()

    return events.editEvent(user)


# Remove an event.
if app.config.get('MULTI_TENANCY') is True:
    @main_bp.route('/clubs/removeevent', methods=['GET', 'POST'])
    @login_required
    def removeevent():
        user = current_user.get_id()

        # Generic catchall in case the current user has been invalidated.
        if current_user.is_active is False:
            return sessionEnded(user)

        clubid = current_user.clubid
        # Must be a club admin (which covers siteadmins).
        # Cannot be club ID 0 (have not selected a club) or logged into an event.
        clubid = current_user.clubid
        event = current_user.event
        if current_user.clubadmin is False or clubid == 0 or (event is not None and event.eventid != 0):
            return unauthorized()

        return events.removeEvent(user)


# Show events for a given club.
if app.config.get('MULTI_TENANCY') is True:
    @main_bp.route('/events/showevents', methods=['GET', 'POST'])
    @login_required
    def showevents():
        user = current_user.get_id()

        # Generic catchall in case the current user has been invalidated.
        if current_user.is_active is False:
            return sessionEnded(user)

        # Must be a club admin (which covers siteadmins).
        # Cannot be club ID 0 (have not selected a club) or logged into an event.
        clubid = current_user.clubid
        event = current_user.event
        if current_user.clubadmin is False or clubid == 0 or (event is not None and event.eventid != 0):
            return unauthorized()

        return events.showEvents(user)


# Show an event for a given club.
@main_bp.route('/events/showevent', methods=['GET', 'POST'])
@login_required
def showevent():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    # Cannot be club ID 0 (have not selected a club).
    if clubid == 0 or user not in ADMINS[clubid]:
        return unauthorized()

    return events.showEvent(user)


# Show an event for a given club.
@main_bp.route('/events/restartevent', methods=['GET', 'POST'])
@login_required
def restartevent():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid
    eventid = current_user.event.eventid

    # Cannot be event ID 0 (have not selected an event) and must be an admin.
    if eventid == 0 or user not in ADMINS[clubid]:
        return unauthorized()

    return configdata.restartEvent(user)


# Add a user.
@main_bp.route('/users/adduser', methods=['GET', 'POST'])
@login_required
def adduser():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid
    event = current_user.event

    # In multi-tenancy mode, this isn't available outside the siteadmin or clubs area.
    if app.config.get('MULTI_TENANCY') is True:
        # Must be a club admin (which covers siteadmins).
        # Cannot be logged into an event.
        if current_user.clubadmin is False or (event is not None and event.eventid != 0):
            return unauthorized()
    else:
        # Must be an admin user.
        if user not in ADMINS[clubid]:
            return unauthorized()

    return users.addUser(user)


# Edit a user.
@main_bp.route('/users/edituser', methods=['GET', 'POST'])
@login_required
def edituser():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid
    event = current_user.event

    # In multi-tenancy mode, this isn't available outside the siteadmin or clubs area.
    if app.config.get('MULTI_TENANCY') is True:
        # Must be a club admin (which covers siteadmins).
        # Cannot be logged into an event.
        if current_user.clubadmin is False or (event is not None and event.eventid != 0):
            return unauthorized()
    else:
        # Must be an admin user.
        if user not in ADMINS[clubid]:
            return unauthorized()

    return users.editUser(user)


# Reset a user's password.
@main_bp.route('/users/resetpassword', methods=['GET', 'POST'])
@fresh_login_required
def resetpassword():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return users.resetPassword(user)


# Remove a user.
@main_bp.route('/users/removeuser', methods=['GET', 'POST'])
@login_required
def removeuser():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid
    event = current_user.event

    # In multi-tenancy mode, this isn't available outside the siteadmin or clubs area.
    if app.config.get('MULTI_TENANCY') is True:
        # Must be a club admin (which covers siteadmins).
        # Cannot be logged into an event.
        if current_user.clubadmin is False or (event is not None and event.eventid != 0):
            return unauthorized()
    else:
        # Must be an admin user.
        if user not in ADMINS[clubid]:
            return unauthorized()

    return users.removeUser(user)


# View a user.
@main_bp.route('/users/showuser', methods=['GET', 'POST'])
@login_required
def showuser():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid
    event = current_user.event

    # In multi-tenancy mode, this isn't available outside the siteadmin or clubs area.
    if app.config.get('MULTI_TENANCY') is True:
        # Must be a club admin (which covers siteadmins).
        # Cannot be logged into an event.
        if current_user.clubadmin is False or (event is not None and event.eventid != 0):
            return unauthorized()
    else:
        # Must be an admin user.
        if user not in ADMINS[clubid]:
            return unauthorized()

    return users.showUser(user)


# Show the users.
@main_bp.route('/users/showusers', methods=['GET'])
@login_required
def showusers():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid
    event = current_user.event

    # In multi-tenancy mode, this isn't available outside the siteadmin or clubs area.
    if app.config.get('MULTI_TENANCY') is True:
        # Must be a club admin (which covers siteadmins).
        # Cannot be logged into an event.
        if current_user.clubadmin is False or (event is not None and event.eventid != 0):
            return unauthorized()
    else:
        # Must be an admin user.
        if user not in ADMINS[clubid]:
            return unauthorized()

    return users.showUsers(user)


# Download exported file.
@main_bp.route('/exports/<filename>', methods=['GET', 'POST'])
def exportfile(filename):
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid
    eventid = current_user.event.eventid

    if eventid == 0 or user not in ADMINS[clubid]:
        return unauthorized()

    return send_file(os.path.join(app.config.get('EXPORT_FOLDER'), filename) )


# Import data from Excel file for restore.
@main_bp.route('/config/importdata', methods=['GET', 'POST'])
@login_required
def importdata():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid
    eventid = current_user.event.eventid

    if eventid == 0 or user not in ADMINS[clubid]:
        return unauthorized()

    return configdata.importData(user)


# Export data to Excel file for user backup.
@main_bp.route('/config/exportdata', methods=['GET', 'POST'])
@login_required
def exportdata():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid
    eventid = current_user.event.eventid

    if eventid == 0 or user not in ADMINS[clubid]:
        return unauthorized()

    return configdata.exportData(user)


# Reset to factory defaults.
@main_bp.route('/config/resetdata', methods=['GET', 'POST'])
@login_required
def resetdata():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid
    eventid = current_user.event.eventid

    if eventid == 0 or user not in ADMINS[clubid]:
        return unauthorized()

    return configdata.resetData(user)


# Fetch the event template file.
@main_bp.route('/templatefile', methods=['GET'])
def templatefile():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid
    eventid = current_user.event.eventid

    if clubid == 0 or user not in ADMINS[clubid]:
        return unauthorized()

    return configdata.downloadTemplate(user)


# Fetch system docs.
@main_bp.route('/fetchdocs', methods=['GET'])
def fetchdocs():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return docs.fetchDocs(user)


# Show the system log.
@main_bp.route('/config/showlog', methods=['GET', 'POST'])
@login_required
def showlog():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return logdata.showLog(user)


# Clear logs.
@main_bp.route('/config/clearlogs', methods=['GET', 'POST'])
@login_required
def clearlogs():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    # At the system level, clearing logs clears all logs.
    all = False
    if clubid == 0:
        all = True

    return logdata.clearLogs(user, alllogs=all)


# Download exported file.
@main_bp.route('/log/<filename>', methods=['GET', 'POST'])
def logfile(filename):
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return send_file(os.path.join(app.config.get('LOG_FOLDER'), filename) )


# Add a ballot item.
@main_bp.route('/ballots/additem', methods=['GET', 'POST'])
@login_required
def additem():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return ballotitems.addItem(user)


# Edit a ballot item.
@main_bp.route('/ballots/edititem', methods=['GET', 'POST'])
@login_required
def edititem():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return ballotitems.editItem(user)


# Remove a ballot item.
@main_bp.route('/ballots/removeitem', methods=['GET', 'POST'])
@login_required
def removeitem():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return ballotitems.removeItem(user)


# Show ballot items.
@main_bp.route('/ballots/showitem', methods=['GET', 'POST'])
@login_required
def showitem():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    return ballotitems.showItem(user)


# Show ballot items.
@main_bp.route('/ballots/showitems', methods=['GET', 'POST'])
@login_required
def showitems():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    return ballotitems.showItems(user)


# Add a ballot contest candidate.
@main_bp.route('/candidates/addcandidate', methods=['GET', 'POST'])
@login_required
def addcandidate():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return candidates.addCandidate(user)


# Edit a ballot contest candidate.
@main_bp.route('/candidates/editcandidate', methods=['GET', 'POST'])
@login_required
def editcandidate():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return candidates.editCandidate(user)


# Remove a ballot contest candidate.
@main_bp.route('/candidates/removecandidate', methods=['GET', 'POST'])
@login_required
def removecandidate():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return candidates.removeCandidate(user)


# Show ballot contest candidates.
@main_bp.route('/candidates/showcandidates', methods=['GET', 'POST'])
@login_required
def showcandidates():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return candidates.showCandidates(user)


# Add an event voter.
@main_bp.route('/voters/addvoter', methods=['GET', 'POST'])
@login_required
def addvoter():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return voters.addVoter(user)


# Edit an event voter.
@main_bp.route('/voters/editvoter', methods=['GET', 'POST'])
@login_required
def editvoter():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return voters.editVoter(user)


# Remove an event voter.
@main_bp.route('/voters/removevoter', methods=['GET', 'POST'])
@login_required
def removevoter():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return voters.removeVoter(user)


# Show event voters.
@main_bp.route('/voters/showvoters', methods=['GET', 'POST'])
@login_required
def showvoters():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return voters.showVoters(user)


# Add a vote for an event.
@main_bp.route('/votes/addvote', methods=['GET', 'POST'])
@login_required
def addvote():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return votes.addVote(user)


# Show event vote results.
@main_bp.route('/votes/showresults', methods=['GET', 'POST'])
@login_required
def showresults():
    user = current_user.get_id()

    # Generic catchall in case the current user has been invalidated.
    if current_user.is_active is False:
        return sessionEnded(user)

    clubid = current_user.clubid

    if user not in ADMINS[clubid]:
        return unauthorized()

    return votes.showResults(user)
