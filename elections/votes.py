#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import traceback

from flask import redirect, render_template, url_for, request
from flask_login import current_user

from elections import db, app, EVENTCONFIG
from elections import loggers
from elections.log import AppLog
from elections.events import EventConfig

from elections import ADMINS
from elections.ballotitems import ITEM_TYPES

def publicVote():
    logger = loggers[AppLog.get_id()]

    event = None

    # Get the current event if it's available.
    event = EVENTCONFIG
    configdata = event.get_event_render_data()

    # Fetch the voter ID.
    voterid = request.values.get('voterid', None)
    if voterid is not None:

        # Verify the voter Id.
        outsql = '''SELECT *
                    FROM voters
                    WHERE voteid='%s';
                 ''' % voterid
        _, data, _ = db.sql(outsql, handlekey='system')

        if data is None or len(data[0]) == 0:
            logger.flashlog("Public vote failure", "Vote ID '%s' was not found." % voterid)
            return render_template('votes/vote.html', voterid=None, configdata=configdata)

        # We found them -
        voter = data[0][0]
        clubid = voter['clubid']
        eventid = voter['eventid']

        event = None
        outsql = '''SELECT *
                    FROM events
                    WHERE eventid='%d';
                ''' % eventid
        _, result, _ = db.sql(outsql, handlekey='system')

        # The result is the first 'dbresults' in the list.
        result = result[0]

        if len(result) == 0:
            logger.flashlog("Public vote failure", "There is no Event with ID %d." % eventid)

            event = EVENTCONFIG
            configdata = event.get_event_render_data()
            return render_template('votes/voted.html', user=None, admins=None, success=False, configdata=configdata)
        else:
            outsql = '''SELECT clubname, icon, homeimage FROM clubs WHERE clubid='%d';''' % clubid
            _, data, _ = db.sql(outsql, handlekey='system')
            club = data[0][0]

            # Create an EventConfig instance and initialize from the global config, with session data and the chosen event ID.
            event = EventConfig(version=app.config.get('VERSION'), user='public', clubid=clubid, eventid=eventid)

            # If the icon or home images files are missing, use the club's files (which are one directory above).
            if event.icon is None:
                event.icon = '../%s' % club['icon']

            if event.homeimage is None:
                event.homeimage = '../%s' % club['homeimage']

        # Redirect to the add-vote page.
        return addVote('public', voterid=voterid, event=event, external=True)
    else:
        logger.info("Public login request started")
        return render_template('votes/vote.html', voterid=None, configdata=configdata)

# Add a vote to an event.
def addVote(user, voterid=None, event=None, external=False):
    try:
        if current_user.is_anonymous:
            if event is None:
                configdata = EVENTCONFIG.get_event_render_data()
                eventlogger = loggers[AppLog.get_id(0, 0)]
            else:
                configdata = event.get_event_render_data()
                eventlogger = loggers[AppLog.get_id(event.clubid, event.eventid)]

            handlekey = user
        else:
            configdata = current_user.get_render_data()
            eventlogger = current_user.logger
            event = current_user.event
            handlekey = current_user.get_userid()

        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        if request.values.get('cancelbutton'):
            eventlogger.flashlog(None, "Add vote operation canceled.", 'info')

            if external is True:
                return render_template('votes/vote.html', user=user, admins=ADMINS[event.clubid],
                                        success=False, voterid=None, fullname=None, configdata=configdata)
            else:
                return redirect(url_for('main_bp.addvote'))

        def return_err(err, url):
            eventlogger.flashlog("Add vote failure", err)

            if external is True:
                return render_template('votes/vote.html', user=user, admins=ADMINS[event.clubid],
                                        success=False, voterid=None, fullname=None, configdata=configdata)
            else:
                return redirect(url_for(url))

        # Check if the event is locked.
        if event is not None and event.locked is True:
            err = "This Event is locked and cannot add Votes."

            if external is True:
                eventlogger.flashlog("Add vote failure", err)
                return render_template('votes/vote.html', user=user, admins=ADMINS[event.clubid],
                                        success=False, voterid=None, fullname=None, configdata=configdata)
            else:
                return return_err(err, 'main_bp.addvote')

        eventlogger.info("Displaying: Add vote")

        # Fetch the vote ID if not provided.
        if voterid is None:
            voterid = request.values.get('voterid', None)

        voter = None
        ballotitems = None
        candidates = None
        answers = None

        if voterid is not None:
            eventlogger.debug("Adding a vote: voter ID '%s'" % voterid)

            # Find the vote ID in the voter table for this event.
            outsql = '''SELECT *
                        FROM voters
                        WHERE clubid='%d' AND eventid='%d' AND voteid='%s';
                        ''' % (event.clubid, event.eventid, voterid)
            _, data, _ = db.sql(outsql, handlekey=handlekey)

            if data is None or len(data[0]) == 0:
                return return_err("Vote ID '%s' was not found." % voterid, 'main_bp.addvote')

            # Get the voter revord.
            voter = data[0][0]

            # If the voter has already voted, they cannot vote again.
            if voter['voted'] is True:
                return return_err("Vote ID '%s' has already voted." % voterid, 'main_bp.addvote')

            eventlogger.debug("Adding a vote: Fetching ballot items and candidates")

            # Fetch all the ballots and candidates for contests.
            outsql = ['''SELECT *
                         FROM ballotitems
                         WHERE clubid='%d' AND eventid='%d'
                         ORDER BY itemid ASC;
                      ''' % (event.clubid, event.eventid)]

            # Only fetch the preconfigured candidates.
            # The voter must be free to write in their own candidates without influence.
            outsql.append('''SELECT *
                             FROM candidates
                             WHERE clubid='%d' AND eventid='%d' AND writein=False
                             ORDER by itemid ASC, lastname ASC;
                          ''' % (event.clubid, event.eventid))

            _, data, _ = db.sql(outsql, handlekey=handlekey)
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

            eventlogger.debug("Adding a vote: Parsing ballot items")

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
            answers = {}

            result = request.values.get('savebutton')
            if result is not None:
                if result == 'save':
                    eventlogger.debug("Adding a vote: Saving changes requested", indent=1)
                    saving = True
                else:
                    # Fetch the data but no validation is performed.
                    for b in ballotitems:
                        itemid = b['itemid']

                        if ITEM_TYPES.CONTEST.value == b['type']:
                            for c in candidates[itemid]:
                                candidateid = str(c['id'])

                                answer = request.values.get('contest_%d_%s' % (itemid, candidateid), None)
                                if answer is not None:
                                    # The candidate was selected.
                                    c['selected'] = True

                                    # Fetch the name for write-in candidates.
                                    if c['new'] is True:
                                        name = request.values.get('writein_%d_%s' % (itemid, candidateid), None)
                                        if name is not None and len(name) > 0:
                                            c['firstname'], c['lastname'] = name.split(' ', 1)
                                            c['fullname'] = name

                                            vote = { 'type': b['type'],
                                                    'item': b['name'],
                                                    'candidate': c['fullname'],
                                                    'writein': c['new'],
                                                    'answer': candidateid,
                                                }

                                            if itemid not in answers:
                                                answers[itemid] = [vote]
                                            else:
                                                answers[itemid].append(vote)

                        elif ITEM_TYPES.QUESTION.value == b['type']:
                            answer = request.values.get('question_%s' % itemid, None)

                            # The answer may be empty (no vote).
                            if answer is not None:
                                result = True if answer == 'Yes' else False
                                vote = { 'type': b['type'],
                                        'item': b['name'],
                                        'answer': '1' if True == result else '0'
                                    }
                                answers[itemid] = [vote]

            if saving is True:
                # Walk through the ballot items and extract the results.
                failed = False
                error = False

                eventlogger.debug("Adding a vote: Fetching answers")

                for b in ballotitems:
                    itemid = b['itemid']

                    if ITEM_TYPES.CONTEST.value == b['type']:
                        votecount = 0
                        for c in candidates[itemid]:
                            candidateid = str(c['id'])

                            answer = request.values.get('contest_%d_%s' % (itemid, candidateid), None)
                            if answer is not None:
                                # The candidate was selected.
                                c['selected'] = True

                                if c['new'] is True:
                                    # Fetch the name.
                                    name = request.values.get('writein_%d_%s' % (itemid, candidateid), None)
                                    if name is None or len(name) == 0:
                                        if error is False:
                                            eventlogger.flashlog("Add vote failure", "Error in Contest '%s':" % b['name'], large=True)
                                            error = True

                                        eventlogger.flashlog("Add vote failure", "A selected write-in candidate name cannot be empty.", indent=True)
                                        failed = True
                                    else:
                                        c['firstname'], c['lastname'] = name.split(' ', 1)
                                        c['fullname'] = name

                                if failed is False:
                                    votecount += 1
                                    vote = { 'type': b['type'],
                                             'item': b['name'],
                                             'candidate': c['fullname'],
                                             'writein': c['new'],
                                             'answer': candidateid,
                                           }
                                    if itemid not in answers:
                                        answers[itemid] = [vote]
                                    else:
                                        answers[itemid].append(vote)

                        # If the voter has selected more than the allotted number of posistions for this contest, it is not accepted.
                        if votecount > b['positions']:
                            if error is False:
                                eventlogger.flashlog("Add vote failure", "Error in Contest '%s':" % b['name'], large=True)
                                error = True

                            eventlogger.flashlog("Add vote failure", "Only %d positions may be selected." % b['positions'], indent=True)
                            failed = True

                    elif ITEM_TYPES.QUESTION.value == b['type']:
                        answer = request.values.get('question_%s' % itemid, None)

                        # The answer may be empty (no vote).
                        if answer is not None:
                            result = True if answer == 'Yes' else False
                            vote = { 'type': b['type'],
                                     'item': b['name'],
                                     'answer': '1' if True == result else '0'
                                   }
                            answers[itemid] = [vote]

                # Empty ballots are not accepted.
                if failed is False:
                    if len(answers) == 0:
                        eventlogger.flashlog("Add vote failure", "Election Error:", large=True)
                        eventlogger.flashlog("Add vote failure", "The ballot is empty.", indent=True)
                        failed = True

                # If all the answers were retrieved successfully, add them to the database.
                ballotid = 0
                if failed is False:
                    # Add any new write-in candidates.
                    # The ID used was temporary and the database will generate the new ID.
                    eventlogger.info("Adding a vote: Saving votes")

                    ballotid, err = event.get_vote_ballotid(user)
                    if err is not None:
                        failed = True

                if failed is False:
                    # Make all write-in candidates that are not selected 'not-new' so we don't
                    # try to add them to the database.
                    for itemid in candidates:
                        for candidate in candidates[itemid]:
                            if candidate['writein'] is True:
                                # If the candidate ID is not in the answers for this item,
                                # set its 'new' flag to False;
                                present = list(filter(lambda x: str(x['answer']) == candidate['id'], answers[itemid]))
                                if len(present) == 0:
                                    candidate['new'] = False

                    # Candidates is keyed by itemid.
                    for itemid in candidates:
                        for candidate in candidates[itemid]:
                            if candidate['new'] is True:
                                # See if this candidate already exists.
                                outsql = '''SELECT id, fullname
                                            FROM candidates
                                            WHERE clubid='%d' AND eventid='%d' AND itemid='%d' AND fullname='%s';
                                         ''' % (event.clubid, event.eventid, itemid, candidate['fullname'])
                                _, data, _ = db.sql(outsql, handlekey=handlekey)

                                # The candidate already exists; grab its ID.
                                if len(data) > 0 and len(data[0]) > 0:
                                    newid = data[0][0]['id']
                                    eventlogger.info("Adding a vote: Write-in candidate '%s' already exists as ID %d" % (candidate['fullname'], newid))
                                else:
                                    outsql = '''INSERT INTO candidates(clubid, eventid, itemid, firstname, lastname, fullname, writein)
                                                    VALUES('%d', '%d', '%d', '%s', '%s', '%s', %s)
                                                    RETURNING id;
                                            ''' % (event.clubid, event.eventid, itemid,
                                                    candidate['firstname'], candidate['lastname'], candidate['fullname'],
                                                    candidate['writein'])
                                    _, result, err = db.sql(outsql, handlekey=handlekey)
                                    if err is not None:
                                        eventlogger.flashlog("Add vote failure", "Failed to add write-in candidate '%s': %s" % (candidate['fullname'], err))
                                        return redirect(url_for('main_bp.index'))

                                    newid = result[0][0]['id']
                                    eventlogger.info("Adding a vote: Added write-in candidate '%s' as ID %d" % (candidate['fullname'], newid))

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
                            outsql.append('''INSERT INTO votes (clubid, eventid, itemid, ballotid, answer)
                                            VALUES('%d', '%d', '%d', '%d', '%s');
                                          ''' % (event.clubid, event.eventid, a, ballotid, answer['answer']))

                    # Mark that this voter has voted.
                    outsql.append('''UPDATE voters
                                     SET voted=True
                                     WHERE clubid='%d' AND eventid='%d' AND voteid='%s';
                                  ''' % (event.clubid, event.eventid, voterid))

                    _, _, err = db.sql(outsql, handlekey=handlekey)
                    if err is not None:
                        eventlogger.flashlog("Add vote failure", err)
                        if external is True:
                            return render_template('votes/voted.html', user=user, admins=ADMINS[event.clubid],
                                                    success=False, voterid=voterid, fullname=voter['fullname'], configdata=configdata)
                        else:
                            return redirect(url_for('main_bp.index'))

                    eventlogger.flashlog(None, "Vote Recorded for Voter ID %s:" % voterid, 'info', propagate=True, large=True)
                    eventlogger.flashlog(None, "Voter Name: %s" % voter['fullname'], 'info', propagate=True, indent=True)
                    eventlogger.info("(Vote choices are not logged)", propagate=True, indent=True)

                    eventlogger.flashlog(None, "Selections", 'info', propagate=True, large=True, log=False)
                    for itemid in answers:
                        # These get displayed to the page but are not logged to keep the vote anonymous.
                        for answer in answers[itemid]:
                            if ITEM_TYPES.CONTEST.value == answer['type']:
                                eventlogger.flashlog(None, "Contest %d (%s): %s%s" %
                                                             (itemid, answer['item'], answer['candidate'], ' (write-in)' if answer['writein'] is True else ""),
                                                             'info', propagate=True, log=False, indent=True)

                            elif ITEM_TYPES.QUESTION.value == answer['type']:
                                eventlogger.flashlog(None, "Question %d (%s): %s" %
                                                            (itemid, answer['item'], ('Yes' if answer['answer'] == '1' else 'No')),
                                                            'info', propagate=True, log=False, indent=True)

                    eventlogger.info("Add vote: Operation completed")
                    if external is True:
                        return render_template('votes/voted.html', user=user, admins=ADMINS[event.clubid],
                                                success=True, voterid=voterid, fullname=voter['fullname'], configdata=configdata)
                    else:
                        return redirect(url_for('main_bp.index'))

        return render_template('votes/addvote.html', user=user, admins=ADMINS[event.clubid],
                                voter=voter, voterid=voterid, external=external,
                                ballotitems=ballotitems, candidates=candidates, answers=answers,
                                configdata=configdata)

    except Exception as e:
        eventlogger.flashlog("Add vote failure", "Exception: %s" % str(e), propagate=True)
        eventlogger.error("Unexpected exception:")
        eventlogger.error(traceback.format_exc())

        if external is True:
            return render_template('votes/vote.html', user=user, admins=ADMINS[event.clubid],
                                    success=False, voterid=None, fullname=None, configdata=configdata)
        else:
            # Redirect to the main page to display the exception and prevent recursive loops.
            return redirect(url_for('main_bp.index'))

def showResults(user):
    try:
        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        current_user.logger.info("Displaying: Show vote results")

        current_user.logger.debug("Show vote results: Fetching ballots and votes")
        # Fetch all ballot items and votes.
        outsql = ['''SELECT *
                        FROM ballotitems
                        WHERE clubid='%d' AND eventid='%d'
                        ORDER BY itemid ASC;
                    ''' % (current_user.event.clubid, current_user.event.eventid)]
        outsql.append('''SELECT votes.itemid, votes.answer, candidates.fullname, COUNT(*)
                         FROM votes
                         LEFT JOIN candidates ON candidates.eventid=votes.eventid AND candidates.itemid=votes.itemid AND candidates.id=votes.answer
                         WHERE votes.clubid='%d' AND votes.eventid='%d'
                         GROUP BY votes.itemid, votes.answer, candidates.fullname
                         ORDER BY itemid ASC, count DESC;
                      ''' % (current_user.event.clubid, current_user.event.eventid))
        _, data, _ = db.sql(outsql, handlekey=user)

        ballotdata = data[0]
        votedata = data[1]

        current_user.logger.debug("Show vote results: Counting votes")

        ballotitems = {}
        for b in ballotdata:
            itemid = b['itemid']
            ballotitems[itemid] = b

        votes = {}
        placed = {}

        for v in votedata:
            itemid = v['itemid']
            ballottype = ballotitems[v['itemid']]['type']
            positions = ballotitems[v['itemid']]['positions']

            if itemid not in placed.keys():
                placed[itemid] = 0
            else:
                placed[itemid] += 1

            if ITEM_TYPES.CONTEST.value == ballottype:
                if placed[itemid] < positions:
                    v['placed'] = True
                else:
                    v['placed'] = False
            elif ITEM_TYPES.QUESTION.value == ballottype:
                if 0 == placed[itemid]:
                    v['placed'] = True
                else:
                    v['placed'] = False

            if itemid not in votes:
                votes[itemid] = [v]
            else:
                votes[itemid].append(v)

        # Add the votes to the ballot item.
        for b in ballotitems:
            if b in list(votes.keys()):
                ballotitems[b]['votes'] = votes[b]

        current_user.logger.info("Show vote results: Operation completed")

        return render_template('votes/showresults.html', user=user, admins=ADMINS[current_user.event.clubid],
                                ballotitems=ballotitems,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Show vote results failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))
