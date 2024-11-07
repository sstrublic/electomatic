#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import traceback

from flask import redirect, render_template, url_for, request, session
from flask_login import current_user

from elections import db, app
from elections import ADMINS

from elections.ballotitems import ITEM_TYPES, ITEM_TYPES_DICT

# Show candidates for ballot contests.
def showCandidates(user):
    try:
        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        current_user.logger.info("Displaying: Show ballot items")

        # Fetch all of the ballot contests, ordered by ID.
        current_user.logger.debug("Showing ballot items: Fetching ballot items", indent=1)

        outsql = ['''SELECT *
                    FROM ballotitems
                    WHERE clubid='%d' AND eventid='%d' AND type='%d'
                    ORDER BY itemid ASC;
                    ''' % (current_user.event.clubid, current_user.event.eventid, ITEM_TYPES.CONTEST.value)]
        outsql.append('''SELECT *
                        FROM candidates
                        WHERE clubid='%d' AND eventid='%d'
                        ORDER BY itemid ASC, lastname ASC;
                      ''' % (current_user.event.clubid, current_user.event.eventid))
        _, data, _ = db.sql(outsql, handlekey=user)

        itemdata = data[0]
        candidates = data[1]

        # Redirect to candidate actions.
        for c in candidates:
            editselect = request.values.get("edit_%d" % c['id'], None)
            removeselect = request.values.get("remove_%d" % c['id'], None)

            if editselect is not None:
                current_user.logger.info("Showing ballot contest candidates: Editing candidate '%s' (%s)" %  (c['id'], c['fullname']))

                # Redirect to the edit page for that item.
                return redirect(url_for('main_bp.editcandidate', contest=c['itemid'], candidateid=c['id']))

            if removeselect is not None:
                current_user.logger.info("Showing ballot contest candidates: Removing candidate '%s' (%s)" %  (c['id'], c['fullname']))

                # Redirect to the remove page for that item.
                return redirect(url_for('main_bp.removecandidate', contest=c['itemid'], candidateid=c['id']))


        # Add candidates to each contest.
        for i in itemdata:
            i['typestr'] = ITEM_TYPES_DICT[i['type']]
            i['candidates'] = []

            for c in candidates:
                if c['itemid'] == i['itemid']:
                    i['candidates'].append(c)

        current_user.logger.info("Showing ballot contest candidates: Operation completed")

        return render_template('candidates/showcandidates.html', user=user, admins=ADMINS[current_user.event.clubid],
                                itemdata=itemdata,
                                configdata=current_user.get_render_data())


    except Exception as e:
        current_user.logger.flashlog("Show candidates failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Add a candidate to a contest.
# If details are provided, use them instead of a form-based operation.
# This allows the voter to add write-in candidate(s) at voting time.
def addCandidate(user, details=None):
    try:
        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Add candidate operation canceled.", 'info')
            return redirect(url_for('main_bp.addcandidate'))

        current_user.logger.info("Displaying: Add candidate")

        # Entry fields.
        entryfields = {'firstname': {"text": "First Name", "value": None},
                       'lastname': {"text": "Last Name", "value": None}
                    }

        # Fetch all the ballot contests for this event.
        outsql = '''SELECT *
                    FROM ballotitems
                    WHERE clubid='%d' AND eventid='%d' AND type='%d';
                  ''' % (current_user.event.clubid, current_user.event.eventid,
                         ITEM_TYPES.CONTEST.value)
        _, data, _ = db.sql(outsql, handlekey=user)

        contests = data[0]
        if len(contests) == 0:
            current_user.logger.flashlog("Add candidate failure", "A ballot contest must be added before adding a Candidate.")
        else:
            # Check if the event is locked.
            if current_user.event.locked is True:
                current_user.logger.flashlog("Add candidate failure", "This Event is locked and cannot add candidates to ballots.")

            else:
                # If saving the information, set this for later.
                saving = False
                if request.values.get('savebutton'):
                    current_user.logger.debug("Adding a candidate: Saving changes requested", indent=1)
                    saving = True

                # Default return renderer.
                # This takes advantage of a couple of things previously retrieved.
                def return_default(msg, entryfields):
                    current_user.logger.flashlog("Add candidate failure", msg)
                    return render_template('candidates/addcandidate.html', user=user, admins=ADMINS[current_user.event.clubid],
                                            firstname=entryfields['firstname']['value'], lastname=entryfields['lastname']['value'],
                                            contests=contests,
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
                    current_user.logger.debug("Adding a candidate: Checking fields", indent=1)
                    for field in entryfields:
                        if type(entryfields[field]['value']) is str and len(entryfields[field]['value']) == 0:
                            current_user.logger.flashlog("Add candidate failure", "Field '%s' cannot be empty." % entryfields[field]['text'])
                            failed = True

                    if failed is False:
                        # Fetch the ballot item ID.
                        itemid = int(request.values.get('contest'))
                        fullname = '%s %s' % (entryfields['firstname']['value'], entryfields['lastname']['value'])

                        # Verify there are no candidates for this ballot with the same name.
                        outsql = '''SELECT *
                                    FROM candidates
                                    WHERE clubid='%d' AND eventid='%d' AND
                                        itemid='%d' AND fullname='%s';
                                    ''' % (current_user.event.clubid, current_user.event.eventid, itemid, fullname)
                        _, data, _ = db.sql(outsql, handlekey=user)

                        duplicates = data[0]
                        if len(duplicates) > 0:
                            current_user.logger.flashlog("Add candidate failure", "Candidate '%s' is already entered for this contest." % fullname)
                            return redirect(url_for('main_bp.addcandidate'))

                        # Add the candidate.
                        outsql = '''INSERT INTO candidates(clubid, eventid, itemid, firstname, lastname, fullname, writein)
                                    VALUES('%d', '%d', '%d', '%s', '%s', '%s', False);
                                 ''' % (current_user.event.clubid, current_user.event.eventid, itemid,
                                        entryfields['firstname']['value'], entryfields['lastname']['value'], fullname)
                        _, _, err = db.sql(outsql, handlekey=current_user.get_userid())

                        # On error to update the database, return and print out the error (like "System is in read only mode").
                        if err is not None:
                            return return_default(err, entryfields)

                        # Get the ballot item name for this item id.
                        contest = None
                        for c in contests:
                            if c['itemid'] == itemid:
                                contest = c['name']
                                break

                        current_user.logger.flashlog(None, "New Candidate saved for ballot contest '%s':" % contest, 'info', propagate=True)
                        current_user.logger.flashlog(None, "Name: %s" % fullname, 'info', highlight=False, indent=True, propagate=True)

                        current_user.logger.info("Add candidate: Operation completed")
                        return redirect(url_for('main_bp.addcandidate'))

        return render_template('candidates/addcandidate.html', user=user, admins=ADMINS[current_user.event.clubid],
                                firstname=entryfields['firstname']['value'], lastname=entryfields['lastname']['value'],
                                contests=contests,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Add candidate failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Edit an existing candidate in a contest.
def editCandidate(user):
    try:
        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Edit candidate operation canceled.", 'info')
            return redirect(url_for('main_bp.editcandidate'))

        # Fetch all the ballot contests for this event.
        outsql = '''SELECT *
                    FROM ballotitems
                    WHERE clubid='%d' AND eventid='%d' AND type='%d';
                  ''' % (current_user.event.clubid, current_user.event.eventid,
                         ITEM_TYPES.CONTEST.value)
        _, data, _ = db.sql(outsql, handlekey=user)

        contests = data[0]
        if len(contests) == 0:
            current_user.logger.flashlog("Edit candidate failure", "There are no ballot contests.")
        else:
            # Check if the event is locked.
            if current_user.event.locked is True:
                current_user.logger.flashlog("Editcandidate failure", "This Event is locked and cannot edit candidates.")
                return redirect(url_for('main_bp.editcandidate'))

        itemid = request.values.get('contest', None)
        candidateid = request.values.get('candidateid', None)
        search = request.values.get('namesearch', '')
        candidate = None
        candidates = None
        contest = None

        if candidateid is not None:
            candidateid = candidateid.strip()

        if len(search) == 0:
            search = None
        else:
            search = search.strip().replace("'", "''")

        # If the last name is provided, do a lookup and build a table to feed back to the form.
        if candidateid is None and search is not None and len(search) > 0:
            current_user.logger.debug("Editing a candidate: Searching by last name with '%s'" % search, indent=1)

            # Special keyword - this lets the user see them all.
            if search == '*':
                searchclause = ""
            else:
                searchclause = "AND LOWER(candidates.lastname) LIKE '%s%%'" % search.lower()

            outsql = '''SELECT candidates.*, ballotitems.name AS contest
                        FROM candidates
                        JOIN ballotitems ON ballotitems.eventid=candidates.eventid AND ballotitems.itemid=candidates.itemid
                        WHERE candidates.clubid='%d' AND candidates.eventid='%d' AND candidates.itemid='%s' %s
                        ORDER BY candidates.lastname ASC;
                        ''' % (current_user.event.clubid, current_user.event.eventid, itemid, searchclause)
            _, result , _ = db.sql(outsql, handlekey=current_user.get_userid())

            # The return data is the first 'dbresults' in the list.
            candidates = result[0]

            if len(candidates) == 0:
                current_user.logger.flashlog('Edit Candidate failure', "No Candidates with a last name matching '%s' were found." % search)
                # Redirect to the edit page so we don't save the previous entry data.
                return redirect(url_for('main_bp.editcandidate'))

            # Fetch the contest (it is the same for all).
            contest = candidates[0]['contest']

        # If a candidate ID is specified, find them for the specified contest.
        if candidateid is not None:
            outsql = '''SELECT candidates.*, ballotitems.name AS contest
                        FROM candidates
                        JOIN ballotitems ON ballotitems.eventid=candidates.eventid AND ballotitems.itemid=candidates.itemid
                        WHERE candidates.clubid='%d' AND candidates.eventid='%d' AND candidates.itemid='%s'
                              AND candidates.id='%s';
                     ''' % (current_user.event.clubid, current_user.event.eventid, itemid, candidateid)
            _, data, _ = db.sql(outsql, handlekey=user)

            candidate = data[0]

            if len(candidate) == 0:
                # Find the full name associated with this id.
                fullname = None
                for c in candidates:
                    if c['id'] == candidateid:
                        fullname = c['fullname']
                        break

                current_user.logger.flashlog("Edit candidate failure", "Candidate '%s' was not found for this Contest." % fullname)
                return redirect(url_for('main_bp.editcandidate'))

            candidate = candidate[0]

            # Fetch the contest (it is the same for all).
            contest = candidate['contest']

            # A candidate cannot be edited if the ballot item has votes.
            outsql = '''SELECT COUNT(id) AS votecount
                        FROM votes
                        WHERE clubid='%d' AND eventid='%d' AND itemid='%s';
                     ''' % (current_user.event.clubid, current_user.event.eventid, itemid)
            _, data, _ = db.sql(outsql, handlekey=user)

            count = data[0][0]

            if count['votecount'] > 0:
                current_user.logger.flashlog("Edit candidate failure", "Ballot item '%s' has Votes and candidates cannot be changed." % contest)
                return redirect(url_for('main_bp.editcandidate'))

            saving = False
            if request.values.get('savebutton'):
                saving = True

            if saving is True:
                current_user.logger.debug("Editing a candidate: saving changes requested", indent=1)

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
                current_user.logger.debug("Editing a candidate: Checking fields", indent=1)
                for field in entryfields:
                    if type(entryfields[field]['value']) is str and len(entryfields[field]['value']) == 0:
                        current_user.logger.flashlog("Edit candidate failure", "Field '%s' cannot be empty." % entryfields[field]['text'])
                        failed = True

                if failed is False:
                    # Verify changes.
                    changed = False
                    for field in entryfields:
                        if candidate[field] != entryfields[field]['value']:
                            changed = True

                    if changed:
                        # Fetch the fields into the candidate structure.
                        for field in entryfields:
                            candidate[field] = entryfields[field]['value']

                        fullname = '%s %s' % (entryfields['firstname']['value'], entryfields['lastname']['value'])

                        # Verify there are no other candidates for this ballot with the same name.
                        outsql = '''SELECT *
                                    FROM candidates
                                    WHERE clubid='%d' AND eventid='%d' AND
                                          itemid='%d' AND fullname='%s' AND id!='%d';
                                    ''' % (current_user.event.clubid, current_user.event.eventid, candidate['itemid'], fullname, candidate['id'])
                        _, data, _ = db.sql(outsql, handlekey=user)

                        duplicates = data[0]
                        if len(duplicates) > 0:
                            current_user.logger.flashlog("Edit candidate failure", "Candidate '%s' is already entered for this contest." % fullname)
                            failed = True

                        if failed is False:
                            # Add the candidate.
                            outsql = '''UPDATE candidates
                                        SET firstname='%s',
                                            lastname='%s',
                                            fullname='%s'
                                        WHERE clubid='%d' AND eventid='%d' AND id='%d';
                                    ''' % (entryfields['firstname']['value'], entryfields['lastname']['value'], fullname,
                                           current_user.event.clubid, current_user.event.eventid, candidate['id'])
                            _, _, err = db.sql(outsql, handlekey=current_user.get_userid())

                            # On error to update the database, return and print out the error (like "System is in read only mode").
                            if err is not None:
                                current_user.logger.flashlog("Edit candidate failure", err)
                            else:
                                current_user.logger.flashlog(None, "Updated Candidate for ballot contest '%s':" % contest, 'info', propagate=True)
                                current_user.logger.flashlog(None, "New Name: %s" % fullname, 'info', highlight=False, indent=True, propagate=True)

                                current_user.logger.info("Edit candidate: Operation completed")
                                return redirect(url_for('main_bp.editcandidate'))
                    else:
                        current_user.logger.flashlog(None, "Changes not saved (no changes made).")


        # If the candidate is a write-in candidate and the new candidate name exists,
        # ask if this is a consolidation attempt.
        # Names might be very similar for write-in candidates and adding their
        # votes only works if the names are the same.

        return render_template('candidates/editcandidate.html', user=user, admins=ADMINS[current_user.event.clubid],
                                candidate=candidate, contests=contests, candidates=candidates,
                                itemid=itemid, candidateid=candidateid, search=search, contest=contest,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Edit candidate failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Remove a candidate from a contest.
def removeCandidate(user):
    try:
        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        # Clear any session flags.
        def clear_session_flags():
            for flag in ['candidatedelete', 'candidateconfirm']:
                if flag in session:
                    current_user.logger.debug("Removing a candidate: Clearing session flag '%s'" % flag, indent=1)
                    session.pop(flag, None)

        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Remove candidate operation canceled.", 'info')
            clear_session_flags()
            return redirect(url_for('main_bp.removecandidate'))

        # Fetch all the ballot contests for this event.
        outsql = '''SELECT *
                    FROM ballotitems
                    WHERE clubid='%d' AND eventid='%d' AND type='%d';
                  ''' % (current_user.event.clubid, current_user.event.eventid,
                         ITEM_TYPES.CONTEST.value)
        _, data, _ = db.sql(outsql, handlekey=user)

        contests = data[0]
        if len(contests) == 0:
            current_user.logger.flashlog("Remove candidate failure", "There are no ballot contests.")
        else:
            # Check if the event is locked.
            if current_user.event.locked is True:
                current_user.logger.flashlog("Remove candidate failure", "This Event is locked and cannot remove candidates from ballots.")
                return redirect(url_for('main_bp.removecandidate'))

        itemid = request.values.get('contest', None)
        candidateid = request.values.get('candidateid', None)
        search = request.values.get('namesearch', '')
        candidate = None
        candidates = None
        contest = None

        delete_request = False
        confirm_request = False

        if candidateid is not None:
            candidateid = candidateid.strip()

        if len(search) == 0:
            search = None
        else:
            search = search.strip().replace("'", "''")

        # If the last name is provided, do a lookup and build a table to feed back to the form.
        if candidateid is None and search is not None and len(search) > 0:
            clear_session_flags()
            current_user.logger.debug("Removing a candidate: Searching by last name with '%s'" % search, indent=1)

            # Special keyword - this lets the user see them all.
            if search == '*':
                searchclause = ""
            else:
                searchclause = "AND LOWER(candidates.lastname) LIKE '%s%%'" % search.lower()

            outsql = '''SELECT candidates.*, ballotitems.name AS contest
                        FROM candidates
                        JOIN ballotitems ON ballotitems.eventid=candidates.eventid AND ballotitems.itemid=candidates.itemid
                        WHERE candidates.clubid='%d' AND candidates.eventid='%d' AND candidates.itemid='%s' %s
                        ORDER BY candidates.lastname ASC;
                        ''' % (current_user.event.clubid, current_user.event.eventid, itemid, searchclause)
            _, result , _ = db.sql(outsql, handlekey=current_user.get_userid())

            # The return data is the first 'dbresults' in the list.
            candidates = result[0]

            if len(candidates) == 0:
                current_user.logger.flashlog('Remove Candidate failure', "No Candidates with a last name matching '%s' were found." % search)
                # Redirect to the edit page so we don't save the previous entry data.
                return redirect(url_for('main_bp.removecandidate'))

            # Fetch the contest (it is the same for all).
            contest = candidates[0]['contest']

        # If a candidate ID is specified, find them for the specified contest.
        if candidateid is not None:
            outsql = '''SELECT candidates.*, ballotitems.name AS contest
                        FROM candidates
                        JOIN ballotitems ON ballotitems.eventid=candidates.eventid AND ballotitems.itemid=candidates.itemid
                        WHERE candidates.clubid='%d' AND candidates.eventid='%d' AND candidates.itemid='%s'
                              AND candidates.id='%s';
                     ''' % (current_user.event.clubid, current_user.event.eventid, itemid, candidateid)
            _, data, _ = db.sql(outsql, handlekey=user)

            candidate = data[0]

            if len(candidate) == 0:
                # Find the full name associated with this id.
                fullname = None
                for c in candidates:
                    if c['id'] == candidateid:
                        fullname = c['fullname']
                        break

                current_user.logger.flashlog("Remove candidate failure", "Candidate '%s' was not found for this Contest." % fullname)
                return redirect(url_for('main_bp.removecandidate'))

            candidate = candidate[0]

            # Fetch the contest (it is the same for all).
            contest = candidate['contest']

            # A candidate cannot be removed if the ballot item has votes.
            outsql = '''SELECT COUNT(id) AS votecount
                        FROM votes
                        WHERE clubid='%d' AND eventid='%d' AND itemid='%s';
                     ''' % (current_user.event.clubid, current_user.event.eventid, itemid)
            _, data, _ = db.sql(outsql, handlekey=user)

            count = data[0][0]

            if count['votecount'] > 0:
                current_user.logger.flashlog("Remove candidate failure", "Ballot item '%s' has Votes and cannot be removed." % contest)
                return redirect(url_for('main_bp.removecandidate'))

            saving = False

            savebutton = request.values.get('savebutton', None)
            if savebutton is not None:
                if savebutton == 'delete':
                    current_user.logger.debug("Removing a candidate: Delete requested for candidate '%s'" % candidate['fullname'], propagate=True, indent=1)
                    session['candidatedelete'] = True

                    # Force reaquiring of confirmation.
                    if 'candidateconfirm' in session:
                        session.pop('candidateconfirm', None)

                    delete_request = True

                elif savebutton == 'confirm' and 'candidatedelete' in session:
                    current_user.logger.debug("Removing a candidate: Confirm requested for candidate '%s'" % candidate['fullname'], propagate=True, indent=1)
                    session['candidateconfirm'] = True

                    delete_request = True
                    confirm_request = True

                else:
                    if all(x in session for x in ['candidatedelete', 'candidateconfirm']):
                        saving = True
            else:
                # Force-clear session flags on fresh page load.
                clear_session_flags()

            if saving is True:
                current_user.logger.debug("Removing a candidate: Removing candidate '%s'" % candidate['fullname'], indent=1)

                # Remove the candidate.
                outsql = '''DELETE FROM candidates
                                WHERE clubid='%d' AND eventid='%d' AND itemid='%s' AND id='%s';
                              ''' % (current_user.event.clubid, current_user.event.eventid, itemid, candidate['id'])
                _, _, err = db.sql(outsql, handlekey=user)

                if err is not None:
                    current_user.logger.flashlog("Remove candidate failure", "Failed to remove candidate data:", highlight=True)
                    current_user.logger.flashlog("Remove candidate failure", err)
                else:
                    current_user.logger.flashlog(None, "Removed candidate '%s' from context '%s'." % (candidate['fullname'], contest), 'info', large=True, highlight=True)
                    current_user.logger.info("Remove candidate: Operation completed")

                return redirect(url_for('main_bp.removecandidate'))

        return render_template('candidates/removecandidate.html', user=user, admins=ADMINS[current_user.event.clubid],
                                candidate=candidate, contests=contests, candidates=candidates,
                                itemid=itemid, candidateid=candidateid, search=search, contest=contest,
                                delete_request=delete_request, confirm_request=confirm_request,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Remove candidate failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))
