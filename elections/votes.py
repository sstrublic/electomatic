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
from elections.ballotitems import ITEM_TYPES

# Add a vote to an event.
def addVote(user, voterid=None):
    try:
        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Add vote operation canceled.", 'info')
            return redirect(url_for('main_bp.addvote'))

        provided = False
        if voterid is not None:
            provided = True

        def return_err(err, url):
            if provided is True:
                return err
            else:
                current_user.logger.flashlog("Add vote failure", err)
                return redirect(url_for(url))

        # Check if the event is locked.
        if current_user.event.locked is True:
            err = "This Event is locked and cannot add Votes."
            return return_err(err, 'main_bp.addvote')

        current_user.logger.info("Displaying: Add vote")

        # Fetch the vote ID if not provided.
        if voterid is None:
            voterid = request.values.get('voterid', None)

        voter = None
        ballotitems = None
        candidates = None

        if voterid is not None:
            current_user.logger.info("Adding a vote: voter ID '%s'" % voterid)

            # Find the vote ID in the voter table for this event.
            outsql = '''SELECT *
                        FROM voters
                        WHERE clubid='%d' AND eventid='%d' AND voteid='%s';
                        ''' % (current_user.event.clubid, current_user.event.eventid, voterid)
            _, data, _ = db.sql(outsql, handlekey=user)

            if data is None or len(data[0]) == 0:
                return return_err("Vote ID '%s' was not found." % voterid, 'main_bp.addvote')

            # Get the voter revord.
            voter = data[0][0]

            # If the voter has already voted, they cannot vote again.
            if voter['voted'] is True:
                return return_err("Vote ID '%s' has already voted." % voterid, 'main_bp.addvote')

            current_user.logger.info("Adding a vote: Fetching ballot items and candidates")

            # Fetch all the ballots and candidates for contests.
            outsql = ['''SELECT *
                         FROM ballotitems
                         WHERE clubid='%d' AND eventid='%d'
                         ORDER BY itemid ASC;
                      ''' % (current_user.event.clubid, current_user.event.eventid)]

            # Only fetch the preconfigured candidates.
            # The voter must be free to write in their own candidates without influence.
            outsql.append('''SELECT *
                             FROM candidates
                             WHERE clubid='%d' AND eventid='%d' AND writein=False
                             ORDER by itemid ASC;
                          ''' % (current_user.event.clubid, current_user.event.eventid))

            _, data, _ = db.sql(outsql, handlekey=user)
            ballotitems = data[0]
            candidates = {}
            for c in data[1]:
                # Indicate the item is not newly added by a voter as a write-in candidate.
                c['new'] = False
                itemid = c['itemid']
                if itemid not in candidates:
                    candidates[itemid] = [c]
                else:
                    candidates[itemid].append(c)

            current_user.logger.info("Adding a vote: Parsing ballot items")

            # Append N write-in candidates (N = number of ballot item positions).
            for b in ballotitems:
                if ITEM_TYPES.CONTEST.value == b['type']:
                    itemid = b['itemid']

                    for r in range(0, b['positions']):
                        writein = {'id': 'writein_%d' % (r + 1),
                                   'itemid': itemid,
                                   'firstname': '',
                                   'lastname': '',
                                   'fullname': '',
                                   'writein': True,
                                   'new': True
                                  }

                        if itemid not in candidates:
                            candidates[itemid] = [writein]
                        else:
                            candidates[itemid].append(writein)

            # If saving the information, set this for later.
            saving = False
            if request.values.get('savebutton'):
                current_user.logger.debug("Adding a vote: Saving changes requested", indent=1)
                saving = True

            if saving is True:
                # Walk through the ballot items and extract the results.
                answers = {}
                failed = False

                current_user.logger.info("Adding a vote: Fetching answers")

                for b in ballotitems:
                    itemid = b['itemid']

                    if ITEM_TYPES.CONTEST.value == b['type']:
                        for c in candidates[itemid]:
                            candidateid = str(c['id'])

                            answer = request.values.get('contest_%d_%s' % (itemid, candidateid), None)
                            if answer is not None:
                                if c['new'] is True:
                                    # Fetch the name.
                                    name = request.values.get('writein_%d_%s' % (itemid, candidateid), None)
                                    if name is None or len(name) == 0:
                                        current_user.logger.flashlog("Add vote failure", "A selected write-in candidate name cannot be empty.")
                                        failed = True
                                    else:
                                        c['firstname'], c['lastname'] = name.split(' ', 1)
                                        c['fullname'] = name

                                if failed is False:
                                    vote = { 'type': b['type'],
                                             'item': b['name'],
                                             'candidate': c['fullname'],
                                             'answer': candidateid
                                           }
                                    if itemid not in answers:
                                        answers[itemid] = [vote]
                                    else:
                                        answers[itemid].append(vote)
                            else:
                                # We will not be adding this to the database.
                                c['new'] = False


                    elif ITEM_TYPES.QUESTION.value == b['type']:
                        answer = request.values.get('question_%s' % itemid, None)

                        # The answer may be empty (no vote).
                        if answer is not None:
                            result = True if answer == 'Yes' else False
                            vote = { 'type': b['type'],
                                     'item': b['name'],
                                     'answer': '1' if True == result else 0
                                   }
                            answers[itemid] = [vote]

                # If all the answers were retrieved successfully, add them to the database.
                if failed is False:
                    # Add any new write-in candidates.
                    # The ID used was temporary and the database will generate the new ID.
                    current_user.logger.info("Adding a vote: Saving votes")

                    # candidates is keyed by itemid.
                    for itemid in candidates:
                        for candidate in candidates[itemid]:
                            if candidate['new'] is True:
                                # See if this candidate already exists.
                                outsql = '''SELECT id, fullname
                                            FROM candidates
                                            WHERE clubid='%d' AND eventid='%d' AND itemid='%d' AND fullname='%s';
                                         ''' % (current_user.event.clubid, current_user.event.eventid, itemid, candidate['fullname'])
                                _, data, _ = db.sql(outsql, handlekey=current_user.get_userid())

                                # The candidate already exists; grab its ID.
                                if len(data) > 0 and len(data[0]) > 0:
                                    newid = data[0][0]['id']
                                    current_user.logger.info("Adding a vote: Write-in candidate '%s' already exists as ID %d" % (candidate['fullname'], newid))
                                else:
                                    outsql = '''INSERT INTO candidates(clubid, eventid, itemid, firstname, lastname, fullname, writein)
                                                    VALUES('%d', '%d', '%d', '%s', '%s', '%s', %s)
                                                    RETURNING id;
                                            ''' % (current_user.event.clubid, current_user.event.eventid, itemid,
                                                    candidate['firstname'], candidate['lastname'], candidate['fullname'],
                                                    candidate['writein'])
                                    _, result, err = db.sql(outsql, handlekey=current_user.get_userid())
                                    if err is not None:
                                        current_user.log.flashlog("Add vote failure", "Failed to add write-in candidate '%s': %s" % (candidate['fullname'], err))
                                        return redirect(url_for('main_bp.index'))

                                    newid = result[0][0]['id']
                                    current_user.logger.info("Adding a vote: Added write-in candidate '%s' as ID %d" % (candidate['fullname'], newid))

                                # Update the answer for this candidate.
                                for answer in answers[itemid]:
                                    if answer['answer'] == candidate['id']:
                                        answer['answer'] = str(newid)
                                        break

                                # Save the new ID for this candidate.
                                candidate['id'] = str(newid)

                    outsql = []
                    for a in answers:
                        for answer in answers[a]:
                            outsql.append('''INSERT INTO votes (clubid, eventid, itemid, answer)
                                            VALUES('%d', '%d', '%d', '%s');
                                          ''' % (current_user.event.clubid, current_user.event.eventid, a, answer['answer']))

                    # Mark that this voter has voted.
                    outsql.append('''UPDATE voters
                                     SET voted=True
                                     WHERE clubid='%d' AND eventid='%d' AND voteid='%s';
                                  ''' % (current_user.event.clubid, current_user.event.eventid, voterid))

                    _, _, err = db.sql(outsql, handlekey=user)
                    if err is not None:
                        current_user.logger.flashlog("Add vote failure", err)
                        return redirect(url_for('main_bp.index'))

                    current_user.logger.flashlog(None, "Vote recorded for Voter ID '%s':" % voterid, 'info', propagate=True)
                    for itemid in answers:
                        for answer in answers[itemid]:
                            if ITEM_TYPES.CONTEST.value == answer['type']:
                                current_user.logger.flashlog(None, "Contest %d (%s): %s" % (itemid, answer['item'], answer['candidate']), 'info', propagate=True)

                            elif ITEM_TYPES.QUESTION.value == answer['type']:
                                current_user.logger.flashlog(None, "Question %d (%s): %s" % (itemid, answer['item'], ('Yes' if answer['answer'] is True else 'No')), 'info', propagate=True)

                    current_user.logger.info("Add vote: Operation completed")
                    return redirect(url_for('main_bp.index'))

        return render_template('votes/addvote.html', user=user, admins=ADMINS[current_user.event.clubid],
                                voter=voter, voterid=voterid,
                                ballotitems=ballotitems, candidates=candidates,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Add vote failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))

def removeVote(user):
    try:
        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Remove vote operation canceled.", 'info')
            return redirect(url_for('main_bp.removevote'))

        current_user.logger.info("Displaying: Remove vote")


    except Exception as e:
        current_user.logger.flashlog("Remove vote failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))
