#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import traceback
import random, string

from flask import redirect, render_template, url_for, request, session
from flask_login import current_user

from elections import db, app
from elections import ADMINS

# Show voters.
def showVoters(user):
    try:
        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        current_user.logger.info("Displaying: Show voters")

        outsql = '''SELECT *
                    FROM voters
                    WHERE clubid='%d' AND eventid='%d';
                 ''' % (current_user.event.clubid, current_user.event.eventid)
        _, data, _ = db.sql(outsql, handlekey=user)

        voterdata = data[0]

        # Redirect to voter actions.
        for v in voterdata:
            editselect = request.values.get("edit_%d" % v['id'], None)
            removeselect = request.values.get("remove_%d" % v['id'], None)

            if editselect is not None:
                current_user.logger.info("Showing voters: Editing voter '%s' (%s)" %  (v['id'], v['fullname']))

                # Redirect to the edit page for that item.
                return redirect(url_for('main_bp.editvoter', id=v['id']))

            if removeselect is not None:
                current_user.logger.info("Showing voters: Removing voter '%s' (%s)" %  (v['id'], v['fullname']))

                # Redirect to the remove page for that item.
                return redirect(url_for('main_bp.removevoter', id=v['id']))

        current_user.logger.info("Show voters: Operation completed")

        return render_template('voters/showvoters.html', user=user, admins=ADMINS[current_user.event.clubid],
                                voterdata=voterdata,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Show voters failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Add a voter.
def addVoter(user):
    try:
        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Add voter operation canceled.", 'info')
            return redirect(url_for('main_bp.addvoter'))

        current_user.logger.info("Displaying: Add voter")

        # Entry fields.
        entryfields = {'firstname': {"text": "First Name", "value": None},
                       'lastname': {"text": "Last Name", "value": None}
                    }

        # Check if the event is locked.
        if current_user.event.locked is True:
            current_user.logger.flashlog("Add voter failure", "This Event is locked and cannot add voters to voters.")

        else:
            # If saving the information, set this for later.
            saving = False
            if request.values.get('savebutton'):
                current_user.logger.debug("Adding a voter: Saving changes requested", indent=1)
                saving = True

            # Default return renderer.
            # This takes advantage of a couple of things previously retrieved.
            def return_default(msg, entryfields):
                current_user.logger.flashlog("Add voter failure", msg)
                return render_template('voters/addvoter.html', user=user, admins=ADMINS[current_user.event.clubid],
                                        firstname=entryfields['firstname']['value'], lastname=entryfields['lastname']['value'],
                                        configdata=current_user.get_render_data())

            # Fetch field data
            for field in entryfields:
                value = request.values.get(field)

                # If no value, make it an empty string to simplify future display.
                if value is None:
                    entryfields[field]['value'] = ''
                else:
                    # Escape apostrophes.
                    entryfields[field]['value'] = value.replace("'", "''").strip()

            if saving is True:
                failed = False

                # All fields must be populated.
                current_user.logger.debug("Adding a voter: Checking fields", indent=1)
                for field in entryfields:
                    if type(entryfields[field]['value']) is str and len(entryfields[field]['value']) == 0:
                        current_user.logger.flashlog("Add voter failure", "Field '%s' cannot be empty." % entryfields[field]['text'])
                        failed = True

                if failed is False:
                    fullname = '%s %s' % (entryfields['firstname']['value'], entryfields['lastname']['value'])

                    # Verify there are no voters with the same name.
                    outsql = '''SELECT *
                                FROM voters
                                WHERE clubid='%d' AND eventid='%d' AND fullname='%s';
                                ''' % (current_user.event.clubid, current_user.event.eventid, fullname)
                    _, data, _ = db.sql(outsql, handlekey=user)

                    duplicates = data[0]
                    if len(duplicates) > 0:
                        current_user.logger.flashlog("Add voter failure", "Voter '%s' already exists for this Event." % fullname)
                        return redirect(url_for('main_bp.addvoter'))

                    # Generate a random 10 digit ID for this voter.
                    unique = False
                    while unique is False:
                        voteid = ''.join(random.choices(string.digits, k=10))

                        # Verify uniqueness.
                        outsql = '''SELECT *
                                    FROM voters
                                    WHERE clubid='%d' AND eventid='%d' AND voteid='%s';
                                 ''' % (current_user.event.clubid, current_user.event.eventid, voteid)
                        _, data, _ = db.sql(outsql, handlekey=user)

                        if data is None or len(data[0]) == 0:
                            unique = True

                    # Add the voter.
                    outsql = '''INSERT INTO voters(clubid, eventid, firstname, lastname, fullname, voteid, voted)
                                VALUES('%d', '%d', '%s', '%s', '%s', '%s', False);
                                ''' % (current_user.event.clubid, current_user.event.eventid,
                                    entryfields['firstname']['value'], entryfields['lastname']['value'], fullname, voteid)
                    _, _, err = db.sql(outsql, handlekey=current_user.get_userid())

                    # On error to update the database, return and print out the error (like "System is in read only mode").
                    if err is not None:
                        return return_default(err, entryfields)

                    current_user.logger.flashlog(None, "New Voter saved:", 'info', propagate=True)
                    current_user.logger.flashlog(None, "Name: %s" % fullname, 'info', highlight=False, indent=True, propagate=True)
                    current_user.logger.flashlog(None, "Voter ID: %s" % voteid, 'info', highlight=False, indent=True, propagate=True)

                    current_user.logger.info("Add voter: Operation completed")
                    return redirect(url_for('main_bp.addvoter'))

        return render_template('voters/addvoter.html', user=user, admins=ADMINS[current_user.event.clubid],
                                firstname=entryfields['firstname']['value'], lastname=entryfields['lastname']['value'],
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Add voter failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Edit a voter.
def editVoter(user):
    try:
        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Edit voter operation canceled.", 'info')
            return redirect(url_for('main_bp.showvoters'))

        # Check if the event is locked.
        if current_user.event.locked is True:
            current_user.logger.flashlog("Edit voter failure", "This Event is locked and cannot edit voters.")
            return redirect(url_for('main_bp.showvoters'))

        voterid = request.values.get('id', None)
        if voterid is None:
            current_user.logger.flashlog("Edit voter failure", "Voter ID must be specified.")
            return redirect(url_for('main_bp.showvoters'))

        try:
            voterid = int(voterid.strip())
        except:
            current_user.logger.flashlog("Edit voter failure", "Voter ID must be a number." % voterid)
            return redirect(url_for('main_bp.showvoters'))

        outsql = '''SELECT *
                    FROM voters
                    WHERE clubid='%d' AND eventid='%d' AND id='%s';
                    ''' % (current_user.event.clubid, current_user.event.eventid, voterid)
        _, data, _ = db.sql(outsql, handlekey=user)

        voter = data[0]
        if len(voter) == 0:
            current_user.logger.flashlog("Edit voter failure", "Voter ID '%d' was not found." % voterid)
            return redirect(url_for('main_bp.showvoters'))

        voter = voter[0]
        if voter['voted'] is True:
            current_user.logger.flashlog("Edit voter failure", "Voter '%s' has already voted and cannot be changed." % voter['fullname'])
            return redirect(url_for('main_bp.editvoter'))

        saving = False
        if request.values.get('savebutton'):
            saving = True

        if saving is True:
            current_user.logger.debug("Editing a voter: saving changes requested", indent=1)

            # Entry fields.
            entryfields = {'firstname': {"text": "First Name", "value": None},
                            'lastname': {"text": "Last Name", "value": None}
                        }

            # Fetch field data.
            for field in entryfields:
                value = request.values.get(field)

                # If no value, make it an empty string to simplify future display.
                if value is None:
                    entryfields[field]['value'] = ''
                else:
                    # Escape apostrophes.
                    entryfields[field]['value'] = value.replace("'", "''").strip()

            failed = False

            # All fields must be populated.
            current_user.logger.debug("Editing a voter: Checking fields", indent=1)
            for field in entryfields:
                if type(entryfields[field]['value']) is str and len(entryfields[field]['value']) == 0:
                    current_user.logger.flashlog("Edit voter failure", "Field '%s' cannot be empty." % entryfields[field]['text'])
                    failed = True

            if failed is False:
                # Verify changes.
                changed = False
                for field in entryfields:
                    if voter[field] != entryfields[field]['value']:
                        changed = True

                if changed:
                    # Fetch the fields into the voter structure.
                    for field in entryfields:
                        voter[field] = entryfields[field]['value']

                    fullname = '%s %s' % (entryfields['firstname']['value'], entryfields['lastname']['value'])

                    # Verify there are no other voters for this voter with the same name.
                    outsql = '''SELECT *
                                FROM voters
                                WHERE clubid='%d' AND eventid='%d' AND fullname='%s' AND id!='%d';
                                ''' % (current_user.event.clubid, current_user.event.eventid, fullname, voter['id'])
                    _, data, _ = db.sql(outsql, handlekey=user)

                    duplicates = data[0]
                    if len(duplicates) > 0:
                        current_user.logger.flashlog("Edit voter failure", "A Voter named '%s' is already entered for this Event." % fullname)
                        failed = True

                    if failed is False:
                        # Add the voter.
                        outsql = '''UPDATE voters
                                    SET firstname='%s',
                                        lastname='%s',
                                        fullname='%s'
                                    WHERE clubid='%d' AND eventid='%d' AND id='%d';
                                ''' % (entryfields['firstname']['value'], entryfields['lastname']['value'], fullname,
                                        current_user.event.clubid, current_user.event.eventid, voter['id'])
                        _, _, err = db.sql(outsql, handlekey=current_user.get_userid())

                        # On error to update the database, return and print out the error (like "System is in read only mode").
                        if err is not None:
                            current_user.logger.flashlog("Edit voter failure", err)
                        else:
                            current_user.logger.flashlog(None, "Updated Voter:", 'info', propagate=True)
                            current_user.logger.flashlog(None, "New Name: %s" % fullname, 'info', highlight=False, indent=True, propagate=True)

                            current_user.logger.info("Edit voter: Operation completed")
                            return redirect(url_for('main_bp.showvoters'))
                else:
                    current_user.logger.flashlog(None, "Changes not saved (no changes made).")

            if failed is True:
                # Fetch the fields into the voter structure to preserve the (faulty) edit.
                for field in entryfields:
                    voter[field] = entryfields[field]['value']

        return render_template('voters/editvoter.html', user=user, admins=ADMINS[current_user.event.clubid],
                                voter=voter,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Edit voter failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Remove a voter.
def removeVoter(user):
    try:
        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        # Clear any session flags.
        def clear_session_flags():
            for flag in ['voterdelete', 'voterconfirm']:
                if flag in session:
                    current_user.logger.debug("Removing a voter: Clearing session flag '%s'" % flag, indent=1)
                    session.pop(flag, None)

        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Remove voter operation canceled.", 'info')
            clear_session_flags()

            return redirect(url_for('main_bp.showvoters'))

        voterid = request.values.get('id', None)
        if voterid is None:
            current_user.logger.flashlog("Remove voter failure", "Missing voter to remove.")
            return redirect(url_for('main_bp.showvoters'))

        current_user.logger.info("Displaying: Remove voter %s" % voterid)

        # Check if the event is locked.
        if current_user.event.locked is True:
            current_user.logger.flashlog("Remove voter failure", "This Event is locked and cannot remove voters.")
            return redirect(url_for('main_bp.showvoters'))

        try:
            voterid = int(voterid)
        except:
            current_user.logger.flashlog("Remove voter failure", "Voter ID must be a number.")
            return redirect(url_for('main_bp.showvoters'))

        # Fetch the voter to remove.
        outsql = '''SELECT *
                    FROM voters
                    WHERE clubid='%d' AND eventid='%d' AND id='%d';
                 ''' % (current_user.event.clubid, current_user.event.eventid, voterid)
        _, data, _ = db.sql(outsql, handlekey=user)

        voter = data[0]
        if len(voter) == 0:
            current_user.logger.flashlog("Edit voter failure", "Voter ID '%d' was not found." % voterid)
            return redirect(url_for('main_bp.showvoters'))

        voter = voter[0]
        if voter['voted'] is True:
            current_user.logger.flashlog("Edit voter failure", "Voter '%s' has already voted and cannot be changed." % voter['fullname'])
            return redirect(url_for('main_bp.editvoter'))

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
                current_user.logger.debug("Removing a voter: Delete requested for voter ID %d" % voterid, propagate=True, indent=1)
                session['voterdelete'] = True

                # Force reaquiring of confirmation.
                if 'voterconfirm' in session:
                    session.pop('voterconfirm', None)

                delete_request = True

            elif savebutton == 'confirm' and 'voterdelete' in session:
                current_user.logger.debug("Removing a voter: Confirm requested for voter ID %d" % voterid, propagate=True, indent=1)
                session['voterconfirm'] = True

                delete_request = True
                confirm_request = True

            else:
                if all(x in session for x in ['voterdelete', 'voterconfirm']):
                    saving = True
        else:
            # Force-clear session flags on fresh page load.
            clear_session_flags()

        if saving is True:
            current_user.logger.debug("Remove voters: Removing voter '%d'" % voterid, indent=1)

            outsql = '''DELETE FROM voters
                         WHERE clubid='%d' AND eventid='%d' AND id='%d';
                     ''' % (current_user.event.clubid, current_user.event.eventid, voterid)

            _, _, err = db.sql(outsql, handlekey=user)

            if err is not None:
                current_user.logger.flashlog("Remove voter failure", "Failed to remove voter:", highlight=True)
                current_user.logger.flashlog("Remove voter failure", err)
            else:
                current_user.logger.flashlog(None, "Removed voter '%s'." % (voter['fullname']), 'info', large=True, highlight=True)
                current_user.logger.info("Remove voter %d: Operation completed" % voterid)

            return redirect(url_for('main_bp.showvoters'))

        return render_template('voters/removevoter.html', user=user, admins=ADMINS[current_user.event.clubid],
                                voter=voter,
                                delete_request=delete_request, confirm_request=confirm_request,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Remove voter failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))
