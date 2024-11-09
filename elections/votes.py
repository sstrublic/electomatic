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

            # Fetch all the ballots and cadidates for contests.
            outsql = ['''SELECT *
                         FROM ballotitems
                         WHERE clubid='%d' AND eventid='%d'
                         ORDER BY itemid ASC;
                      ''' % (current_user.event.clubid, current_user.event.eventid)]
            outsql.append('''SELECT *
                             FROM candidates
                             WHERE clubid='%d' AND eventid='%d'
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

            # Append N write-in candidates (N= number of ballot item positions).
            for b in ballotitems:
                itemid = b['itemid']
                if ITEM_TYPES.CONTEST.value == b['type']:
                    writein = {'itemid': itemid,
                               'firstname': '',
                               'lastname': '',
                               'fullname': '',
                               'writein': True,
                               'new': True
                              }

                    for r in range(0, b['positions']):
                        writein['id'] = 'writein_%d' % (r + 1)
                        if itemid not in candidates:
                            candidates[itemid] = [writein]
                        else:
                            candidates[itemid].append(writein)

            # If saving the information, set this for later.
            saving = False
            if request.values.get('savebutton'):
                current_user.logger.debug("Adding a voter: Saving changes requested", indent=1)
                saving = True

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
