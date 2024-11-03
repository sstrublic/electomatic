#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import traceback
import re

from flask import redirect, render_template, url_for, request, session
from flask_login import current_user

from elections import db
from elections import ADMINS, ALLUSERS
from elections import app, loggers

from elections.log import AppLog
from elections.users import User
from elections.events import EventConfig
import elections.images as images

# Note: everythning in this file is managed by siteadmin.

def isValidEmail(email):
    if len(email) > 0:
        email_regex = re.compile(r"[^@]+@[^@]+\.[^@]+")
        if not email_regex.match(email):
            return False

    return True


def fetchClubs(user, clubid=0, fetchall=False):
    try:
        fetch = ''
        if fetchall is False:
            # We hide clubs 0 and 1 as internal-only club entries unless specified.
            if clubid == 0:
                fetch = 'WHERE clubid > 1'
            else:
                fetch = "WHERE clubid='%d'" % clubid

        outsql = '''SELECT *
                    FROM clubs %s
                    ORDER BY clubid ASC;
                ''' % fetch
        _, data, _ = db.sql(outsql, handlekey=user)
        clubs = data[0]

        return clubs

    except Exception as e:
        current_user.logger.flashlog("Fetch Clubs failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

    return None


def remove_club_data(user, clubid):
    # Remove the club from the database.
    outsql = '''DELETE FROM clubs
                WHERE clubid='%d';
             ''' % clubid
    _, _, err = db.sql(outsql, handlekey=current_user.get_userid())
    if err is not None:
        return err

    loggers[AppLog.get_id(clubid)].critical("### Removed Club ID %d ###" % clubid)

    return None

# Show the list of clubs.
def showClubs(user):
    try:
        current_user.logger.info("Displaying: Show clubs list")

        # Fetch all of the clubs.
        current_user.logger.debug("Showing clubs list: Fetching clubs", indent=1)

        clubs = fetchClubs(current_user.get_userid(), clubid=current_user.clubid)
        clubdata = []
        for c in clubs:
            clubdata.append([c['clubid'], c['clubname'], c['contact'], c['email'], c['phone'], c['active']])


        # Check the value of all select buttons for clubs.
        for c in clubdata:
            clubselect = request.values.get("select_%d" % c[0], None)
            viewselect = request.values.get("view_%d" % c[0], None)
            editselect = request.values.get("edit_%d" % c[0], None)

            if clubselect is not None:
                current_user.logger.info("Showing clubs list: Selecting Club ID '%s' (%s)" % (c[0], c[1]))

                # Set the club ID for the user to the selected club.
                current_user.set_club(c[0])
                current_user.event.clubid = c[0]

                # Update the cached club ID in the session.
                session['clubid'] = c[0]

                # Clear the previous URL so we can't try to go back to the clubs page.
                session['prev_url'] = None

                # Reset session's logfile offset.
                session['logfile_offset'] = 0

                # Redirect to the events page for that club.
                current_user.logger.info("Showing clubs list: User transitioned to Club ID '%s' (%s)" % (c[0], c[1]))
                return redirect(url_for('main_bp.showevents'))

            if viewselect is not None:
                current_user.logger.info("Showing clubs list: Viewing Club ID '%s' (%s)" % (c[0], c[1]))

                # Redirect to the view page for that club.
                return redirect(url_for('main_bp.showclub', clubid=c[0]))

            if editselect is not None:
                current_user.logger.info("Showing clubs list: Editing Club ID '%s' (%s)" % (c[0], c[1]))

                # Redirect to the edit page for that club.
                return redirect(url_for('main_bp.editclub', clubid=c[0]))

        # There are no voters or admins that apply for site-admin functions.
        return render_template('clubs/showclubs.html', user=user,  admins=ADMINS[current_user.clubid],
                                clubdata=clubdata,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("View Clubs failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# View a club.
def showClub(user, user_clubid=0):
    try:
        # Get the entry ID to look up who to edit.
        # If provided by the caller, we already know...
        if user_clubid != 0:
            clubid = str(user_clubid)
            current_user.logger.info("Displaying: View current club")
        else:
            current_user.logger.info("Displaying: View a club")
            clubid = request.values.get('clubid', '')

        search = request.values.get('namesearch', '')

        if len(clubid) == 0:
            clubid = None
        else:
            clubid = clubid.strip()

        if len(search) == 0:
            search = None
        else:
            search = search.strip().replace("'", "''")

        # If the club name is provided, do a lookup and build a table to feed back to the form.
        if clubid is None and search is not None and len(search) > 0:
            current_user.logger.debug("Viewing a club: Searching by club name with '%s'" % search, indent=1)

            # Special keyword - this lets the user see them all.
            if search == '*':
                searchclause = ""
            else:
                searchclause = "AND LOWER(clubname) LIKE '%s%%'" % search.lower()

            outsql = '''SELECT clubid, clubname, contact
                        FROM clubs
                        WHERE clubid > 1 %s
                        ORDER BY clubname ASC;
                        ''' % searchclause
            _, result , _ = db.sql(outsql, handlekey=current_user.get_userid())

            # The return data is the first 'dbresults' in the list.
            result = result[0]

            clubs = []
            for r in result:
                clubs.append([r['clubid'], r['clubname'], r['contact']])

            # Nothing found.
            if len(clubs) == 0:
                current_user.logger.flashlog('View Club failure', "No Clubs with a name matching '%s' were found." % search)
                # Redirect to the edit page so we don't save the previous entry data.
                return redirect(url_for('main_bp.showclub'))

        else:
            clubs = None

        # If an club ID has been specified, verify it and get the record.
        if clubid is not None and len(clubid) > 0:
            # Verify the format (numeric).
            try:
                clubid = int(clubid)
            except:
                current_user.logger.flashlog("View Club failure", "Club ID must be a number.")
                return redirect(url_for('main_bp.showclub'))

            current_user.logger.debug("Viewing a club: Viewing Club ID %s" % clubid, indent=1)

            # Fetch the club matching the club ID.
            outsql = '''SELECT *
                        FROM clubs
                        WHERE clubid='%d';
                        ''' % clubid
            _, result , _ = db.sql(outsql, handlekey=current_user.get_userid())

            # The return data is the first 'dbresults' in the list.
            result = result[0]
            if len(result) == 0:
                current_user.logger.flashlog("View Club failure", "Club ID %s was not found." % clubid)

                # Redirect to the edit page so we don't save the previous entry data.
                return redirect(url_for('main_bp.showclub'))

            club = result[0]

            icon = club['icon']
            homeimage = club['homeimage']

            current_user.logger.info("Viewing a club: Operation completed")

            return render_template('clubs/showclub.html', user=user, admins=ADMINS[current_user.clubid],
                                    clubid=clubid, search=search, clubs=clubs, icon=icon, homeimage=homeimage,
                                    clubname=club['clubname'], contact=club['contact'], email=club['email'], phone=club['phone'], active=club['active'],
                                    configdata=current_user.get_render_data())
        else:
            return render_template('clubs/showclub.html', user=user, admins=ADMINS[current_user.clubid],
                                    clubid=clubid, search=search, clubs=clubs,
                                    configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("View Club failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Add a club.
def addClub(user):
    try:
        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Add club operation canceled.", 'info')
            return redirect(url_for('main_bp.addclub'))

        current_user.logger.info("Displaying: Add a club")

        # If saving the information, set this for later.
        saving = False
        if request.values.get('savebutton'):
            current_user.logger.debug("Adding a club: Saving changes requested", indent=1)
            saving = True

        # Fetch the fields.
        clubname = request.values.get('clubname', '').strip().replace("'", "''")
        contact = request.values.get('contact', '').strip().replace("'", "''")
        email = request.values.get('email', '').strip().replace("'", "''")
        phone = request.values.get('phone', '').strip().replace("'", "''")

        active = request.values.get('active', False)
        if active is not False:
            active = True

        icon = app.config.get('DEFAULT_APPICON')
        homeimage = app.config.get('DEFAULT_HOMEIMAGE')

        appfile = request.files.get('appfile')
        if appfile is not None and appfile.filename != '':
            icon = appfile.filename
        else:
            appfile = None

        homefile = request.files.get('homefile')
        if homefile is not None and homefile.filename != '':
            homeimage = homefile.filename
        else:
            homefile = None

        if saving is True:
            # Fetch all of the clubs.
            current_user.logger.debug("Adding a club: Fetching clubs", indent=1)

            clubs = fetchClubs(current_user.get_userid(), clubid=current_user.clubid)
            clubdata = []
            for c in clubs:
                clubdata.append([c['clubid'], c['clubname'], c['contact'], c['email'], c['phone'], c['active']])

            failed = False

            if len(clubname) == 0:
                current_user.logger.flashlog("Add Club failure", "Must specify a Club name.")
                failed = True

            if len(contact) == 0:
                current_user.logger.flashlog("Add Club failure", "Must specify a Club contact.")
                failed = True

            # If both email and phone are empty, that's not good (have to have a way to reach someone)
            if len(email) == 0 and len(phone) == 0:
                current_user.logger.flashlog("Add Club failure", "Must specify either a contact email or phone number.")
                failed = True

            # If an email address is specified, require a standard format.
            if not isValidEmail(email):
                current_user.logger.flashlog("Add Club failure", "Contact email is not in a standard format.")
                failed = True

            # Aside from name, there really is no duplication that would prevent adding a club;
            # Someone could be the contact for multiple clubs.
            for c in clubdata:
                # Index 1 is the club name.
                if c[1] == clubname:
                    current_user.logger.flashlog('Add Clubs failure', "There is already a Club named '%s'." % clubname.strip())
                    failed = True

            if appfile is not None:
                if appfile.mimetype != "image/x-icon":
                    current_user.logger.flashlog("Add Club failure", "Unsupported browser icon type (not an icon).")
                    failed = True

            # If there was a home image selected, fetch and verify.
            if homefile is not None:
                SUPPORTED_FILETYPES = ["image/jpeg", "image/png"]
                if homefile.mimetype not in SUPPORTED_FILETYPES:
                    current_user.logger.flashlog("Add Club failure", "Unsupported home image type (must be PNG or JPEG).")
                    failed = True

            if failed is False:
                # Add the club.
                outsql = '''INSERT INTO clubs (clubname, contact, email, phone, active, icon, homeimage)
                            VALUES('%s', '%s', '%s', '%s', '%s', '%s', '%s')
                            RETURNING clubid;
                        ''' % (clubname, contact, email, phone, active, icon, homeimage)
                _, results, err = db.sql(outsql, handlekey=current_user.get_userid())

                # On error to update the database, return and print out the error (like "System is in read only mode").
                if err is not None:
                    current_user.logger.flashlog("Add Club failure", err)
                    return render_template('clubs/addclub.html', user=user,  admins=ADMINS[current_user.clubid],
                                            clubname=clubname, contact=contact, email=email, phone=phone, active=active, icon=icon, homeimage=homeimage,
                                            configdata=current_user.get_render_data())

                # The return data is the first 'dbresults' set in the list.
                # The return data set is a list; we need the first row.  We want the ID.
                results = results[0]
                r = results[0]
                clubid = r['clubid']

                # Save the image files.
                images.save_image_file("Adding a club", appfile, icon, clubid, 0)
                images.save_image_file("Adding a club", homefile, homeimage, clubid, 0)

                # Create the log for this club.
                logid = AppLog.get_id(clubid)
                loggers[logid] = AppLog(clubid, 0, app.config.get('LOG_BASENAME'), app.config.get('LOG_DOWNLOAD_FOLDER'), user)
                loggers[logid].info("### Club created ###")

                # Add the club to the user caches.
                User.add_club_to_user_cache(clubid)

                current_user.logger.flashlog(None, "Added Club:", 'info')
                current_user.logger.flashlog(None, "Club ID %s:" % clubid, 'info')
                current_user.logger.flashlog(None, "Club Name: %s" % clubname.replace("''", "'"), 'info', highlight=False, indent=True)
                current_user.logger.flashlog(None, "Club Contact: %s" % contact.replace("''", "'"), 'info', highlight=False, indent=True)
                current_user.logger.flashlog(None, "Contact Email: %s" % email.replace("''", "'"), 'info', highlight=False, indent=True)
                current_user.logger.flashlog(None, "Contact Phone: %s" % phone.replace("''", "'"), 'info', highlight=False, indent=True)
                current_user.logger.flashlog(None, "Club Active: %s" % ("Yes" if active is True else "No"), 'info', highlight=False, indent=True)

                current_user.logger.info("Adding a club: Operation completed")
                return redirect(url_for('main_bp.addclub'))

        return render_template('clubs/addclub.html', user=user,  admins=ADMINS[current_user.clubid],
                                clubname=clubname, contact=contact, email=email, phone=phone, active=active, icon=icon, homeimage=homeimage,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Add Club failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Edit a club.
def editClub(user, user_clubid=0):
    try:
        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Edit club operation canceled.", 'info')
            return redirect(url_for('main_bp.editclub'))

        # Get the club ID to look up who to edit.
        # If provided by the caller, we already know...
        if user_clubid != 0:
            clubid = str(user_clubid)
            current_user.logger.info("Displaying: Edit club %s" % clubid)
        else:
            current_user.logger.info("Displaying: Edit a club")
            clubid = request.values.get('clubid', '')

        # If saving the information, set this for later.
        saving = False
        if request.values.get('savebutton'):
            current_user.logger.debug("Editing a club: Saving changes requested", indent=1)
            saving = True

        # Holds the entry data.
        entryfields = {'clubname': {'text': "Club Name", 'value': None},
                       'contact': {'text': "Club Contact", 'value': None},
                       'email': {'text': "Email", 'value': None},
                       'phone': {'text': "Phone", 'value': None},
                       'active': {'text': "Account Active", 'value': None},
                      }

        search = request.values.get('namesearch', '')

        if len(clubid) == 0:
            clubid = None
        else:
            clubid = clubid.strip()

        if len(search) == 0:
            search = None
        else:
            search = search.strip().replace("'", "''")

        # If the club name is provided, do a lookup and build a table to feed back to the form.
        if clubid is None and search is not None and len(search) > 0:
            current_user.logger.debug("Editing a club: Searching by club name with '%s'" % search, indent=1)

            # Special keyword - this lets the user see them all.
            if search == '*':
                searchclause = ""
            else:
                searchclause = "AND LOWER(clubname) LIKE '%s%%'" % search.lower()

            outsql = '''SELECT clubid, clubname, contact
                        FROM clubs
                        WHERE clubid > 1 %s
                        ORDER BY clubname ASC;
                        ''' % searchclause
            _, result , _ = db.sql(outsql, handlekey=current_user.get_userid())

            # The return data is the first 'dbresults' in the list.
            result = result[0]

            clubs = []
            for r in result:
                clubs.append([r['clubid'], r['clubname'], r['contact']])

            # Nothing found.
            if len(clubs) == 0:
                current_user.logger.flashlog('Edit Club failure', "No Clubs with a name matching '%s' were found." % search)
                # Redirect to the edit page so we don't save the previous entry data.
                return redirect(url_for('main_bp.editclub'))

        else:
            clubs = None

        # If an club ID has been specified, verify it and get the record.
        if clubid is not None and len(clubid) > 0:
            # Verify the format (numeric).
            try:
                clubid = int(clubid)
            except:
                current_user.logger.flashlog("Edit Club failure", "Club ID must be a number.")
                return redirect(url_for('main_bp.editclub'))

            current_user.logger.info("Editing a club: Editing Club ID %s" % clubid, indent=1)

            # Fetch the club matching the club ID.
            outsql = '''SELECT *
                        FROM clubs
                        WHERE clubid='%d';
                        ''' % clubid
            _, result , _ = db.sql(outsql, handlekey=current_user.get_userid())

            # The return data is the first 'dbresults' in the list.
            result = result[0]
            if len(result) == 0:
                current_user.logger.flashlog("Edit Club failure", "Club ID %s was not found." % clubid)

                # Redirect to the edit page so we don't save the previous entry data.
                return redirect(url_for('main_bp.editclub'))

            club = result[0]

            icon = club['icon']
            homeimage = club['homeimage']

            if saving is True:
                appfile = None
                homefile = None

                current_user.logger.info("Editing a club: Saving entry changes", indent=1)

                # Verify entry parameters.
                current_user.logger.debug("Editing a club: Checking fields", indent=1)
                for field in entryfields:
                    value = request.values.get(field)

                    # Handle checkbox fields.
                    if field in ['active']:
                        entryfields[field]['value'] = value
                        if value is None:
                            entryfields[field]['value'] = 'False'
                    else:
                        entryfields[field]['value'] = value.strip().replace("'", "''")

                # Default return renderer.
                # This takes advantage of a couple of things previously retrieved.
                def return_default(msg, entryfields):
                    current_user.logger.flashlog("Edit Club failure", msg)

                    return render_template('clubs/editclub.html', user=user,  admins=ADMINS[current_user.clubid],
                                            clubid=clubid, search=search, clubs=clubs,
                                            clubname=entryfields['clubname']['value'], contact=entryfields['contact']['value'],
                                            email=entryfields['email']['value'], phone=entryfields['phone']['value'],
                                            active=entryfields['active']['value'],
                                            icon=icon, homeimage=homeimage,
                                            configdata=current_user.get_render_data())

                # Check fields for content.
                for field in entryfields:
                    value = entryfields[field]['value']

                    # Field must not be empty.
                    if field in ['clubname', 'contact'] and len(value) == 0:
                        return return_default("Field '%s' cannot be empty." % entryfields[field]['text'], entryfields)

                    if field == 'email':
                        # If an email address is specified, require a standard format.
                        if not isValidEmail(value):
                            return return_default("Contact email is not in a standard format.", entryfields)

                if all(len(entryfields[f]['value']) == 0 for f in ['email', 'phone']):
                    return return_default("Must specify either a contact email or phone number.", entryfields)

                # If no changes were made, do nothing.
                changed = False
                appfile_changed = False
                homefile_changed = False

                for field in entryfields:
                    if entryfields[field]['value'] != str(club[field]):
                        changed = True

                if 'appfile' in request.files:
                    appfile = request.files.get('appfile')
                    if appfile.filename != '':
                        # Verify the file is an icon of specific size.
                        if appfile.mimetype != "image/x-icon":
                            return return_default("Unsupported browser icon type (not an icon).", entryfields)
                        else:
                            icon = appfile.filename
                            changed = True
                            appfile_changed = True
                    else:
                        appfile = None

                # If there was a home image selected, fetch and verify.
                if 'homefile' in request.files:
                    homefile = request.files.get('homefile')
                    if homefile.filename != '':
                        # Verify the file is a specific type and size.
                        SUPPORTED_FILETYPES = ["image/jpeg", "image/png"]
                        if homefile.mimetype not in SUPPORTED_FILETYPES:
                            return return_default("Unsupported home image type (must be PNG or JPEG).", entryfields)
                        else:
                            homeimage = homefile.filename
                            changed = True
                            homefile_changed = True
                    else:
                        homefile = None

                if changed is True:
                    # Save the change.
                    outsql = '''UPDATE clubs
                                SET clubname='%s', contact='%s', email='%s', phone='%s', active=%s,
                                icon='%s', homeimage='%s'
                                WHERE clubid='%d';
                             ''' % (entryfields['clubname']['value'], entryfields['contact']['value'],
                                    entryfields['email']['value'], entryfields['phone']['value'],
                                    entryfields['active']['value'], icon, homeimage, clubid)
                    _, _, err = db.sql(outsql, handlekey=current_user.get_userid())

                    # On error to update the database, return and print out the error (like "System is in read only mode").
                    if err is not None:
                        return return_default(err, None)

                    clubdata = {'clubid': clubid,
                                'clubname': entryfields['clubname']['value']}

                    # Save each file that's changed.
                    if appfile_changed is True:
                        images.save_image_file("Editing a club", appfile, None, clubid, 0)
                        clubdata['icon'] = icon

                    if homefile_changed is True:
                        images.save_image_file("Editing a club", homefile, None, clubid, 0)
                        clubdata['homeimage'] = homeimage

                    # Update all users that may be logged into this club.
                    EventConfig.update_club_caches(current_user.get_userid(), clubdata)

                    current_user.logger.flashlog(None, "Club changes saved:", 'info')
                    current_user.logger.flashlog(None, "Club ID: %s" % clubid, 'info')
                    current_user.logger.flashlog(None, "Club Name: %s" % entryfields['clubname']['value'].replace("''", "'"), 'info', highlight=False, indent=True)
                    current_user.logger.flashlog(None, "Club Contact: %s" % entryfields['contact']['value'].replace("''", "'"), 'info', highlight=False, indent=True)
                    current_user.logger.flashlog(None, "Contact Email: %s" % entryfields['email']['value'].replace("''", "'"), 'info', highlight=False, indent=True)
                    current_user.logger.flashlog(None, "Contact Phone: %s" % entryfields['phone']['value'].replace("''", "'"), 'info', highlight=False, indent=True)

                    # Only show for site admins.
                    if current_user.get_render_data()[6] is True:
                        current_user.logger.flashlog(None, "Club Active: %s" % ("Yes" if entryfields['active']['value'] == 'True' else "No"), 'info', highlight=False, indent=True)

                    current_user.logger.info("Editing a club: Operation completed")
                    return redirect(url_for('main_bp.editclub'))

                else:
                    current_user.logger.flashlog(None, "Changes not saved (no changes made).")

        if clubid is not None:
            return render_template('clubs/editclub.html', user=user,  admins=ADMINS[current_user.clubid],
                                    clubid=clubid, search=search, clubs=clubs, icon=icon, homeimage=homeimage,
                                    clubname=club['clubname'], contact=club['contact'], email=club['email'], phone=club['phone'], active=club['active'],
                                    configdata=current_user.get_render_data())
        else:
            return render_template('clubs/editclub.html', user=user,  admins=ADMINS[current_user.clubid],
                                    clubid=clubid, search=search, clubs=clubs, icon=None, homeimage=None,
                                    configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Edit Club failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Remove a club.
def removeClub(user):
    try:
        # Clear any session flags.
        def clear_session_flags():
            for flag in ['clubdelete', 'clubconfirm']:
                if flag in session:
                    current_user.logger.debug("Removing a club: Clearing session flag '%s'" % flag, indent=1)
                    session.pop(flag, None)

        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Remove club operation canceled.", 'info')
            clear_session_flags()

            return redirect(url_for('main_bp.removeclub'))

        current_user.logger.info("Displaying: Remove a club")

        # Get the club ID to look up who to remove.
        clubid = request.values.get('clubid', '')
        search = request.values.get('namesearch', '')

        if len(clubid) == 0:
            clubid = None
        else:
            clubid = clubid.strip()

        if len(search) == 0:
            search = None
        else:
            search = search.strip().replace("'", "''")

        # If the club name is provided, do a lookup and build a table to feed back to the form.
        if clubid is None and search is not None and len(search) > 0:
            current_user.logger.debug("Removing a club: Searching by club name with '%s'" % search, indent=1)

            # Special keyword - this lets the user see them all.
            if search == '*':
                searchclause = ""
            else:
                searchclause = "AND LOWER(clubname) LIKE '%s%%'" % search.lower()

            outsql = '''SELECT clubid, clubname
                        FROM clubs
                        WHERE clubid > 1 %s
                        ORDER BY clubname ASC;
                        ''' % (searchclause)
            _, result , _ = db.sql(outsql, handlekey=current_user.get_userid())

            # The return data is the first 'dbresults' in the list.
            result = result[0]

            clubs = []
            for r in result:
                clubs.append([r['clubid'], r['clubname']])

            # Nothing found.
            if len(clubs) == 0:
                current_user.logger.flashlog('Remove Club failure', "No Clubs with a name matching '%s' were found." % search)
                # Redirect to the edit page so we don't save the previous entry data.
                return redirect(url_for('main_bp.removeclub'))

        else:
            clubs = None

        # If an club ID has been specified, verify it and get the record.
        if clubid is not None and len(clubid) > 0:
            # Verify the format (numeric).
            try:
                clubid = int(clubid)
            except:
                current_user.logger.flashlog("Remove Club failure", "Club ID must be a number.")
                return redirect(url_for('main_bp.removeclub'))

            current_user.logger.debug("Removing a club: Searching for Club ID %s" % clubid, indent=1)

            # Fetch the club matching the club ID.
            outsql = ['''SELECT *
                        FROM clubs
                        WHERE clubid='%d';
                        ''' % clubid]
            outsql.append('''SELECT *
                             FROM events
                             WHERE clubid = '%d';
                          ''' % clubid)
            _, result , _ = db.sql(outsql, handlekey=current_user.get_userid())

            # The return data is the first 'dbresults' in the list.
            clubs = result[0]
            if len(clubs) == 0:
                current_user.logger.flashlog("Remove Club failure", "Club ID %s was not found." % clubid)

                # Redirect to the edit page so we don't save the previous entry data.
                return redirect(url_for('main_bp.removeclub'))

            club = clubs[0]

            icon = club['icon']
            homeimage = club['homeimage']

            # Cannot remove the internal club IDs 0 and 1.
            if clubid <= 1:
                current_user.logger.flashlog("Remove Club failure", "Cannot remove reserved Club ID '%s'." % clubid)
                return redirect(url_for('main_bp.removeclub'))

            events = result[1]
            if len(events) > 0:
                # Cannot remove a club that has events (must remove all events first).
                current_user.logger.flashlog("Remove Club failure", "Cannot remove a Club that has Events.")
                for e in events:
                    current_user.logger.flashlog("Remove Club failure", "Event %d: '%s'" % (e['eventid'], e['title']), highlight=False, indent=True)

                # Redirect to the edit page so we don't save the previous entry data.
                return redirect(url_for('main_bp.removeclub'))

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
                    current_user.logger.debug("Removing a club: Delete requested for Club ID %d" % clubid, propagate=True, indent=1)
                    session['clubdelete'] = True

                    # Force reaquiring of confirmation.
                    if 'clubconfirm' in session:
                        session.pop('clubconfirm', None)

                    delete_request = True

                elif savebutton == 'confirm' and 'clubdelete' in session:
                    current_user.logger.debug("Removing a club: Confirm requested for Club ID %d" % clubid, propagate=True, indent=1)
                    session['clubconfirm'] = True

                    delete_request = True
                    confirm_request = True

                else:
                    if all(x in session for x in ['clubdelete', 'clubconfirm']):
                        saving = True
            else:
                # Force-clear session flags on fresh page load.
                clear_session_flags()

            if saving is True:
                # Search all users to see if anyone is logged into a club (has an event ID for this club in their event cache).
                users = []
                for user_id in ALLUSERS:
                    sessions = ALLUSERS.get(user_id, {})
                    for user_uuid in sessions:
                        userobj = ALLUSERS[user_id][user_uuid]
                        if userobj.clubid == clubid:
                            users.append(userobj.id)

                if len(users) > 0:
                    current_user.logger.flashlog("Remove Club failure", "Clubs cannot be removed while users are logged in.")
                    for u in users:
                        current_user.logger.flashlog("Remove Club failure", "User: '%s'" % u, highlight=False, indent=True)

                    return redirect(url_for('main_bp.removeclub'))

                current_user.logger.info("Removing a club: Removing Club ID %d" % clubid, indent=1)

                # Force-clear session flags since we're done.
                clear_session_flags()
                delete_request = False
                confirm_request = False

                # Do the needful.
                err = remove_club_data(user, clubid)

                if err is not None:
                    current_user.logger.flashlog("Remove Club failure", "Failed to remove club data:", highlight=True)
                    current_user.logger.flashlog("Remove Club failure", err)
                else:
                    current_user.logger.flashlog(None, "Removed Club %d (%s)." % (clubid, club['clubname']), 'info', large=True, highlight=True)
                    current_user.logger.info("Removing a club: Operation completed")

                return redirect(url_for('main_bp.removeclub'))

            return render_template('clubs/removeclub.html', user=user, admins=ADMINS[current_user.clubid],
                                clubid=clubid, search=search, clubs=clubs, icon=icon, homeimage=homeimage,
                                clubname=club['clubname'],
                                delete_request=delete_request, confirm_request=confirm_request,
                                configdata=current_user.get_render_data())
        else:
            return render_template('clubs/removeclub.html', user=user, admins=ADMINS[current_user.clubid],
                                clubid=clubid, search=search, clubs=clubs,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Remove Club failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))
