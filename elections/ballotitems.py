#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import traceback
from enum import Enum

from flask import redirect, render_template, url_for, request
from flask_login import current_user

from elections import db, app
from elections import ADMINS

class ITEM_TYPES(Enum):
    ELECTION = 1
    QUESTION = 2

ITEM_TYPES_DICT = {
    ITEM_TYPES.ELECTION.value: 'Election',
    ITEM_TYPES.QUESTION.value: 'Question'
}

# Show all ballot items for an event.
def showItems(user):
    try:
        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        current_user.logger.info("Displaying: Show ballot items")

        # Fetch all of the ballot items, ordered by race ID.
        current_user.logger.debug("Showing ballot items: Fetching ballot items", indent=1)

        outsql = '''SELECT *
                    FROM ballotitems
                    WHERE clubid='%d' AND eventid='%d'
                    ORDER BY itemid ASC;
                    ''' % (current_user.event.clubid, current_user.event.eventid)
        _, data, _ = db.sql(outsql, handlekey=user)

        itemdata = []
        if len(data) > 0:
            itemdata = data[0]

        for i in itemdata:
            i['typestr'] = ITEM_TYPES_DICT[i['type']]

        for i in itemdata:
            viewselect = request.values.get("view_%d" % i['itemid'], None)
            editselect = request.values.get("edit_%d" % i['itemid'], None)

            if viewselect is not None:
                current_user.logger.info("Showing ballot items: Viewing item ID '%s' (%s)" % (i['itemid'], i['name']))

                # Redirect to the view page for that item.
                return redirect(url_for('main_bp.showitem', itemid=i['itemid']))

            if editselect is not None:
                current_user.logger.info("Showing ballot items: Editing item ID '%s' (%s)" %  (i['itemid'], i['name']))

                # Redirect to the edit page for that item.
                return redirect(url_for('main_bp.edititem', itemid=i['itemid']))

        current_user.logger.info("Showing ballot items: Operation completed")

        return render_template('ballots/showitems.html', user=user, admins=ADMINS[current_user.event.clubid],
                                itemdata=itemdata,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Show ballot items failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Show a specific ballot item for an event.
def showItem(user):
    try:
        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        itemid = request.values.get('itemid', None)
        if itemid is None:
            current_user.logger.flashlog("Show ballot item failure", "Missing ballot item to view.")
            return redirect(url_for('main_bp.index'))

        try:
            itemid = int(itemid)
        except:
            current_user.logger.flashlog("Show ballot item failure", "item ID must be a number.")
            return redirect(url_for('main_bp.index'))

        current_user.logger.info("Displaying: Show ballot item '%d'" % itemid)

        # Fetch all of the ballot items, ordered by race ID.
        current_user.logger.debug("Showing ballot items: Fetching ballot item '%d'" % itemid, indent=1)

        outsql = '''SELECT *
                    FROM ballotitems
                    WHERE clubid='%d' AND eventid='%d' AND itemid='%d';
                    ''' % (current_user.event.clubid, current_user.event.eventid, itemid)
        _, data, _ = db.sql(outsql, handlekey=user)

        itemdata = []
        if len(data) > 0:
            itemdata = data[0]

        if len(itemdata) == 0:
            current_user.logger.flashlog("Show ballot item failure", "item ID %d not found'." % itemid)
            return redirect(url_for('main_bp.index'))

        itemdata = itemdata[0]
        itemdata['typestr'] = ITEM_TYPES_DICT[itemdata['type']]

        current_user.logger.info("Showing ballot item %d: Operation completed" % itemid)

        return render_template('ballots/showitem.html', user=user, admins=ADMINS[current_user.event.clubid],
                                itemdata=itemdata,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Show ballot items failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Add a ballot item to an event.
def addItem(user):
    try:
        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Add ballot item operation canceled.", 'info')
            return redirect(url_for('main_bp.additem'))

        current_user.logger.info("Displaying: Add ballot item")

        # Fetch all of the ballot items, ordered by race ID.
        current_user.logger.debug("Adding a ballot item: Fetching ballot items", indent=1)
        outsql = ['''SELECT *
                     FROM ballotitems
                     WHERE clubid='%d' AND eventid='%d'
                     ORDER BY itemid ASC;
                  ''' % (current_user.event.clubid, current_user.event.eventid)]
        outsql.append('''SELECT MAX(itemid)
                         FROM ballotitems
                         WHERE clubid='%d' AND eventid='%d';
                      ''' % (current_user.event.clubid, current_user.event.eventid))
        _, data, _ = db.sql(outsql, handlekey=user)

        itemdata = data[0]
        itemmax = data[1]

        # Entry fields.
        entryfields = {'name': {"text": "Name", "value": None},
                       'description': {"text": "Description", "value": None},
                       'type': {"text": "Type", "value": None},
                       'positioncount': {"text": "# of Positions", "value": None},
                        }

        # Check if the event is locked.
        if current_user.event.locked is True:
            current_user.logger.flashlog("Add Ballot Item failure", "This Event is locked and cannot add ballot items.")

        else:
            # If saving the information, set this for later.
            saving = False
            if request.values.get('savebutton'):
                current_user.logger.debug("Adding a ballot item: Saving changes requested", indent=1)
                saving = True

            # Default return renderer.
            # This takes advantage of a couple of things previously retrieved.
            def return_default(msg, entryfields):
                current_user.logger.flashlog("Add ballot item failure", msg)

                return render_template('ballots/additem.html', user=user, admins=ADMINS[current_user.event.clubid],
                    name=entryfields['name']['value'], description=entryfields['description']['value'],
                    type=entryfields['type']['value'], positioncount=entryfields['positioncount']['value'],
                    itemtypes=ITEM_TYPES_DICT,
                    configdata=current_user.get_render_data())

            for field in entryfields:
                value = request.values.get(field)

                # If no value, make it an empty string to simplify future display.
                if value is None:
                    entryfields[field]['value'] = ''
                else:
                    # Escape apostrophes.
                    entryfields[field]['value'] = value.replace("'", "''").strip()

            # If the position count is 0 or blank, we default to 1.
            if len(entryfields['positioncount']['value']) == 0 or entryfields['positioncount']['value'] == '0':
                current_user.logger.debug("Adding a ballot item: Defaulting position count to 1", indent=1)
                entryfields['positioncount']['value'] = '1'

            if saving is True:
                failed = False

                # All fields must be populated.
                current_user.logger.debug("Adding a ballot item: Checking fields", indent=1)
                for field in entryfields:
                    if type(entryfields[field]['value']) is str and len(entryfields[field]['value']) == 0:
                        current_user.logger.flashlog("Add ballot item failure", "Field '%s' cannot be empty." % entryfields[field]['text'])
                        failed = True

                # Verify type.
                if failed is False:
                    try:
                        it = int(entryfields['type']['value'])
                        if it not in ITEM_TYPES_DICT.keys():
                            current_user.logger.flashlog("Add ballot item failure", "Field '%s' must be a valid number." % entryfields[field]['text'])
                            failed = True

                    except:
                        current_user.logger.flashlog("Add ballot item failure", "Field '%s' must be a number." % entryfields[field]['text'])
                        failed = True

                if failed is False:
                    try:
                        pc = int(entryfields['positioncount']['value'])
                        if pc <= 0:
                            current_user.logger.flashlog("Add ballot item failure", "Position Count cannot be 0 or negative." % entryfields[field]['text'])
                            failed = True

                    except:
                        current_user.logger.flashlog("Add ballot item failure", "Position count must be a number.")
                        failed = True

                if failed is False:
                    # The description must also be unique.
                    current_user.logger.debug("Adding a class: Checking class description", indent=1)
                    for r in itemdata:
                        if entryfields['name']['value'] == r['name']:
                            current_user.logger.flashlog("Add ballot item failure", "Ballot Item ID %s already has this name." % r['itemid'])
                            failed = True

                        if entryfields['description']['value'] == r['description']:
                            current_user.logger.flashlog("Add Ballot Item failure", "Ballot Item ID %s already has this description." % r['itemid'])
                            failed = True

                # Save the data.
                if failed is False:
                    current_user.logger.info("Adding a ballot item: Saving item data", indent=1)

                    # Set the race ID as the next after the highest for this event.
                    try:
                        itemid = int(itemmax[0]['max']) + 1
                    except:
                        itemid = 1

                    outsql = '''INSERT INTO ballotitems(clubid, eventid, itemid, type, name, description, positioncount)
                                VALUES('%d', '%d', '%d', '%s', '%s', '%s', '%s');
                             ''' % (current_user.event.clubid, current_user.event.eventid,
                                   itemid,
                                   entryfields['type']['value'],
                                   entryfields['name']['value'],
                                   entryfields['description']['value'],
                                   entryfields['positioncount']['value'])
                    _, _, err = db.sql(outsql, handlekey=current_user.get_userid())

                    # On error to update the database, return and print out the error (like "System is in read only mode").
                    if err is not None:
                        return return_default(err, entryfields)

                    itemtype = int(entryfields['type']['value'])
                    description = entryfields['description']['value'].replace("''", "'")

                    current_user.logger.flashlog(None, "New Ballot Item saved as ID %d:" % itemid, 'info', propagate=True)
                    current_user.logger.flashlog(None, "Type: %s" % ITEM_TYPES_DICT[itemtype], 'info', highlight=False, indent=True, propagate=True)
                    current_user.logger.flashlog(None, "Name: %s" % entryfields['name']['value'].replace("''", "'"), 'info', highlight=False, indent=True, propagate=True)
                    current_user.logger.flashlog(None, "Description: %s" % description[0:63], 'info', highlight=False, indent=True, propagate=True)

                    if itemtype == ITEM_TYPES.ELECTION.value:
                        current_user.logger.flashlog(None, "Position Count: %s" % entryfields['positioncount']['value'], 'info', highlight=False, indent=True)

                    current_user.logger.info("Add item type: Operation completed")

        return render_template('ballots/additem.html', user=user, admins=ADMINS[current_user.event.clubid],
                                name=entryfields['name']['value'], description=entryfields['description']['value'],
                                type=entryfields['type']['value'], positioncount=entryfields['positioncount']['value'],
                                itemtypes=ITEM_TYPES_DICT,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Add ballot item failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))

