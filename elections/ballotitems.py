#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import traceback
from enum import Enum

from flask import redirect, render_template, url_for, request, session
from flask_login import current_user

from elections import db, app
from elections import ADMINS

class ITEM_TYPES(Enum):
    CONTEST = 1
    QUESTION = 2

ITEM_TYPES_DICT = {
    ITEM_TYPES.CONTEST.value: 'Contest',
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
            removeselect = request.values.get("remove_%d" % i['itemid'], None)

            if viewselect is not None:
                current_user.logger.info("Showing ballot items: Viewing item ID '%s' (%s)" % (i['itemid'], i['name']))

                # Redirect to the view page for that item.
                return redirect(url_for('main_bp.showitem', itemid=i['itemid']))

            if editselect is not None:
                current_user.logger.info("Showing ballot items: Editing item ID '%s' (%s)" %  (i['itemid'], i['name']))

                # Redirect to the edit page for that item.
                return redirect(url_for('main_bp.edititem', itemid=i['itemid']))

            if removeselect is not None:
                current_user.logger.info("Showing ballot items: Removing item ID '%s' (%s)" %  (i['itemid'], i['name']))

                # Redirect to the remove page for that item.
                return redirect(url_for('main_bp.removeitem', itemid=i['itemid']))

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
            return redirect(url_for('main_bp.showitems'))

        try:
            itemid = int(itemid)
        except:
            current_user.logger.flashlog("Show ballot item failure", "item ID must be a number.")
            return redirect(url_for('main_bp.showitems'))

        current_user.logger.info("Displaying: Show ballot item %d" % itemid)

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
            current_user.logger.flashlog("Show ballot item failure", "Item ID %d not found'." % itemid)
            return redirect(url_for('main_bp.showitems'))

        itemdata = itemdata[0]
        itemdata['typestr'] = ITEM_TYPES_DICT[itemdata['type']]

        current_user.logger.info("Showing ballot item %d: Operation completed" % itemid)

        return render_template('ballots/showitem.html', user=user, admins=ADMINS[current_user.event.clubid],
                                itemdata=itemdata,
                                itemid=itemid,
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
                       'positions': {"text": "Positions", "value": None},
                       'writeins': {"text": "Write-Ins Allowed", "value": False},
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
                    type=entryfields['type']['value'], positions=entryfields['positions']['value'],
                    writeins=entryfields['writeins']['value'],
                    itemtypes=ITEM_TYPES_DICT,
                    configdata=current_user.get_render_data())

            for field in entryfields:
                value = request.values.get(field)

                # If no value, make it an empty string to simplify future display.
                if value is None:
                    if field in ['writeins']:
                        entryfields[field]['value'] = False
                    else:
                        entryfields[field]['value'] = ''
                else:
                    if field in ['writeins']:
                        f = request.values.get(field, False)
                        entryfields[field]['value'] = True if f is not False else False
                    else:
                        # Escape apostrophes.
                        entryfields[field]['value'] = value.replace("'", "''").strip()

            # If the position count is 0 or blank, we default to 1.
            if len(entryfields['positions']['value']) == 0 or entryfields['positions']['value'] == '0':
                current_user.logger.debug("Adding a ballot item: Defaulting position count to 1", indent=1)
                entryfields['positions']['value'] = '1'

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
                        pc = int(entryfields['positions']['value'])
                        if pc <= 0:
                            current_user.logger.flashlog("Add ballot item failure", "Positions cannot be 0 or negative." % entryfields[field]['text'])
                            failed = True

                    except:
                        current_user.logger.flashlog("Add ballot item failure", "Positions must be a number.")
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

                    # Set the item ID as the next after the highest for this event.
                    try:
                        itemid = int(itemmax[0]['max']) + 1
                    except:
                        itemid = 1

                    outsql = '''INSERT INTO ballotitems(clubid, eventid, itemid, type, name, description, positions, writeins)
                                VALUES('%d', '%d', '%d', '%s', '%s', '%s', '%s', '%s');
                             ''' % (current_user.event.clubid, current_user.event.eventid,
                                   itemid,
                                   entryfields['type']['value'],
                                   entryfields['name']['value'],
                                   entryfields['description']['value'],
                                   entryfields['positions']['value'],
                                   entryfields['writeins']['value'])
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

                    if itemtype == ITEM_TYPES.CONTEST.value:
                        current_user.logger.flashlog(None, "Positions: %s" % entryfields['positions']['value'], 'info', highlight=False, indent=True)
                        current_user.logger.flashlog(None, "Write-ins Allowed: %s" % ("Yes" if entryfields['writeins']['value'] is True else "No"), 'info', highlight=False, indent=True)

                    current_user.logger.info("Add item type: Operation completed")
                    return redirect(url_for('main_bp.additem'))

        return render_template('ballots/additem.html', user=user, admins=ADMINS[current_user.event.clubid],
                                name=entryfields['name']['value'], description=entryfields['description']['value'],
                                type=entryfields['type']['value'], positions=entryfields['positions']['value'],
                                writeins=entryfields['writeins']['value'],
                                itemtypes=ITEM_TYPES_DICT,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Add ballot item failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Edit a ballot item.
def editItem(user):
    try:
        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        itemid = request.values.get('itemid', None)

        if request.values.get('cancelbutton'):
            try:
                itemid = int(itemid)
                current_user.logger.flashlog(None, "Edit ballot item operation canceled.", 'info')
                return redirect(url_for('main_bp.showitem') + "?itemid=%d" % itemid)
            except:
                current_user.logger.flashlog("Edit ballot item failure", "Item ID must be a number.")
                return redirect(url_for('main_bp.showitems'))

        if itemid is None:
            current_user.logger.flashlog("Edit ballot item failure", "Missing ballot item to edit.")
            return redirect(url_for('main_bp.showitems'))

        current_user.logger.info("Displaying: Edit ballot item %s" % itemid)

        # Check if the event is locked.
        if current_user.event.locked is True:
            current_user.logger.flashlog("Edit ballot item failure", "This Event is locked and cannot edit ballot items.")
            return redirect(url_for('main_bp.showitems'))

        try:
            itemid = int(itemid)
        except:
            current_user.logger.flashlog("Edit ballot item failure", "Item ID must be a number.")
            return redirect(url_for('main_bp.showitems'))

        # Fetch the current database values.
        outsql = ['''SELECT *
                    FROM ballotitems
                    WHERE ballotitems.clubid='%d' AND ballotitems.eventid='%d' AND ballotitems.itemid='%d';
                  ''' % (current_user.event.clubid, current_user.event.eventid, itemid)]
        outsql.append('''SELECT *
                         FROM ballotitems
                         WHERE clubid='%d' AND eventid='%d'
                         ORDER BY itemid ASC;
                      ''' % (current_user.event.clubid, current_user.event.eventid))
        outsql.append('''SELECT COUNT(id) AS votecount
                         FROM votes
                         WHERE clubid='%d' AND eventid='%d' AND itemid='%d';
                      ''' % (current_user.event.clubid, current_user.event.eventid, itemid))

        _, data, _ = db.sql(outsql, handlekey=user)

        itemdata = data[0]
        allitems = data[1]

        if len(itemdata) == 0:
            current_user.logger.flashlog("Edit ballot item failure", "Item ID %d not found'." % itemid)
            return redirect(url_for('main_bp.showitems'))

        itemdata = itemdata[0]
        count = data[2][0]

        if count['votecount'] > 0:
            current_user.logger.flashlog("Edit ballot item failure", "Item with ID %d has Votes and cannot be changed." % itemid)
            return redirect(url_for('main_bp.showitems'))

        itemdata['typestr'] = ITEM_TYPES_DICT[itemdata['type']]

        # Entry fields.
        entryfields = {'name': {"text": "Name", "value": None},
                        'description': {"text": "Description", "value": None},
                        'type': {"text": "Type", "value": None},
                        'positions': {"text": "Positions", "value": None},
                        'writeins': {"text": "Write-Ins Allowed", "value": False},
                        }

        for field in entryfields:
            value = request.values.get(field)

            # If no value, make it an empty string to simplify future display.
            if value is None:
                if field in ['writeins']:
                    entryfields[field]['value'] = False
                else:
                    entryfields[field]['value'] = ''
            else:
                if field in ['writeins']:
                    f = request.values.get(field, False)
                    entryfields[field]['value'] = True if f is not False else False
                else:
                    # Escape apostrophes.
                    entryfields[field]['value'] = value.replace("'", "''").strip()

        # Default return renderer.
        # This takes advantage of a couple of things previously retrieved.
        def return_default(msg, entryfields):
            if msg is not None:
                current_user.logger.flashlog("Edit ballot item failure", msg)

            return render_template('ballots/edititem.html', user=user, admins=ADMINS[current_user.event.clubid],
                itemid=itemid,
                name=entryfields['name']['value'], description=entryfields['description']['value'],
                type=entryfields['type']['value'], positions=entryfields['positions']['value'],
                writeins=entryfields['writeins']['value'],
                itemtypes=ITEM_TYPES_DICT,
                configdata=current_user.get_render_data())

        saving = False
        if request.values.get('savebutton'):
            saving = True

        if saving is True:
            changed = False
            failed = False

            # All fields must be populated.
            current_user.logger.debug("Editing a ballot item: Checking fields", indent=1)
            for field in entryfields:
                if type(entryfields[field]['value']) is str and len(entryfields[field]['value']) == 0:
                    current_user.logger.flashlog("Edit ballot item failure", "Field '%s' cannot be empty." % entryfields[field]['text'])
                    failed = True
                else:
                    if field in ['writeins']:
                        if entryfields[field]['value'] != itemdata[field]:
                            changed = True

                    elif entryfields[field]['value'] != str(itemdata[field]):
                        changed = True

            if changed is False:
                current_user.logger.flashlog(None, "Changes not saved (no changes made).")
            else:
                # Verify type.
                if failed is False:
                    try:
                        it = int(entryfields['type']['value'])
                        if it not in ITEM_TYPES_DICT.keys():
                            current_user.logger.flashlog("Edit ballot item failure", "Field '%s' must be a valid number." % entryfields[field]['text'])
                            failed = True

                    except:
                        current_user.logger.flashlog("Edit ballot item failure", "Field '%s' must be a number." % entryfields[field]['text'])
                        failed = True

                if failed is False:
                    try:
                        pc = int(entryfields['positions']['value'])
                        if pc <= 0:
                            current_user.logger.flashlog("Edit ballot item failure", "Positions cannot be 0 or negative." % entryfields[field]['text'])
                            failed = True

                    except:
                        current_user.logger.flashlog("Edit ballot item failure", "Positions must be a number.")
                        failed = True

                if failed is False:
                    # The description must also be unique.
                    current_user.logger.debug("Editing a ballot item: Checking class description", indent=1)
                    for r in allitems:
                        if r['itemid'] != itemid:
                            if entryfields['name']['value'] == r['name']:
                                current_user.logger.flashlog("Edit ballot item failure", "Ballot Item ID %s already has this name." % r['itemid'])
                                failed = True

                            if entryfields['description']['value'] == r['description']:
                                current_user.logger.flashlog("Edit Ballot Item failure", "Ballot Item ID %s already has this description." % r['itemid'])
                                failed = True

                # Save the data.
                if failed is True:
                    return return_default(None, entryfields)

                current_user.logger.info("Editing a ballot item: Saving item data", indent=1)

                outsql = '''UPDATE ballotitems
                            SET type='%s',
                                name='%s',
                                description='%s',
                                positions='%s',
                                writeins='%s'
                            WHERE clubid='%d' AND eventid='%d' AND itemid='%d';
                            ''' % (entryfields['type']['value'],
                                entryfields['name']['value'],
                                entryfields['description']['value'],
                                entryfields['positions']['value'],
                                entryfields['writeins']['value'],
                                current_user.event.clubid, current_user.event.eventid, itemid)
                _, _, err = db.sql(outsql, handlekey=current_user.get_userid())

                # On error to update the database, return and print out the error (like "System is in read only mode").
                if err is not None:
                    return return_default(err, entryfields)

                itemtype = int(entryfields['type']['value'])
                description = entryfields['description']['value'].replace("''", "'")

                current_user.logger.flashlog(None, "Updated Ballot Item %d:" % itemid, 'info', propagate=True)
                current_user.logger.flashlog(None, "Type: %s" % ITEM_TYPES_DICT[itemtype], 'info', highlight=False, indent=True, propagate=True)
                current_user.logger.flashlog(None, "Name: %s" % entryfields['name']['value'].replace("''", "'"), 'info', highlight=False, indent=True, propagate=True)
                current_user.logger.flashlog(None, "Description: %s" % description[0:63], 'info', highlight=False, indent=True, propagate=True)

                if itemtype == ITEM_TYPES.CONTEST.value:
                    current_user.logger.flashlog(None, "Positions: %s" % entryfields['positions']['value'], 'info', highlight=False, indent=True)
                    current_user.logger.flashlog(None, "Write-ins Allowed: %s" % ("Yes" if entryfields['writeins']['value'] is True else "No"), 'info', highlight=False, indent=True)

                current_user.logger.info("Edit ballot item: Operation completed")
                return redirect(url_for('main_bp.showitem') + "?itemid=%d" % itemid)


        return render_template('ballots/edititem.html', user=user, admins=ADMINS[current_user.event.clubid],
                                itemid=itemid,
                                name=itemdata['name'], description=itemdata['description'],
                                type=itemdata['type'], positions=itemdata['positions'],
                                writeins=itemdata['writeins'],
                                itemtypes=ITEM_TYPES_DICT,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Edit ballot item failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))

# Remove a ballot item for an event.
def removeItem(user):
    try:
        # Since these buttons are in the form area on this page, we have to handle in code.
        option = request.values.get('redirect')
        if option is not None:
            return redirect(url_for('main_bp.%s' % option))

        # Clear any session flags.
        def clear_session_flags():
            for flag in ['ballotdelete', 'ballotconfirm']:
                if flag in session:
                    current_user.logger.debug("Removing a ballot item: Clearing session flag '%s'" % flag, indent=1)
                    session.pop(flag, None)

        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Remove ballot item operation canceled.", 'info')
            clear_session_flags()

            return redirect(url_for('main_bp.showitems'))

        itemid = request.values.get('itemid', None)
        if itemid is None:
            current_user.logger.flashlog("Remove ballot item failure", "Missing ballot item to remove.")
            return redirect(url_for('main_bp.showitems'))

        current_user.logger.info("Displaying: Remove ballot item %s" % itemid)

        # Check if the event is locked.
        if current_user.event.locked is True:
            current_user.logger.flashlog("Remove ballot item failure", "This Event is locked and cannot remove ballot items.")
            return redirect(url_for('main_bp.showitems'))

        try:
            itemid = int(itemid)
        except:
            current_user.logger.flashlog("Remove ballot item failure", "Item ID must be a number.")
            return redirect(url_for('main_bp.showitems'))

        # Fetch the ballot item to remove.
        outsql = ['''SELECT *
                    FROM ballotitems
                    WHERE clubid='%d' AND eventid='%d' AND itemid='%d';
                    ''' % (current_user.event.clubid, current_user.event.eventid, itemid)]
        outsql.append('''SELECT COUNT(id) AS votecount
                         FROM votes
                         WHERE clubid='%d' AND eventid='%d' AND itemid='%d'
                      ''' % (current_user.event.clubid, current_user.event.eventid, itemid))
        _, data, _ = db.sql(outsql, handlekey=user)

        itemdata = data[0]
        if len(itemdata) == 0:
            current_user.logger.flashlog("Remove ballot item failure", "item ID %d not found'." % itemid)
            return redirect(url_for('main_bp.showitems'))

        itemdata = itemdata[0]
        count = data[1][0]

        if count['votecount'] > 0:
            current_user.logger.flashlog("Remove ballot item failure", "Item with ID %d has Votes and cannot be removed." % itemid)
            return redirect(url_for('main_bp.showitem') + "?itemid=%d" % itemid)

        itemdata['typestr'] = ITEM_TYPES_DICT[itemdata['type']]

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
                current_user.logger.debug("Removing a ballot item: Delete requested for ballot item ID %d" % itemid, propagate=True, indent=1)
                session['ballotdelete'] = True

                # Force reaquiring of confirmation.
                if 'ballotconfirm' in session:
                    session.pop('ballotconfirm', None)

                delete_request = True

            elif savebutton == 'confirm' and 'ballotdelete' in session:
                current_user.logger.debug("Removing a ballot item: Confirm requested for ballot item ID %d" % itemid, propagate=True, indent=1)
                session['ballotconfirm'] = True

                delete_request = True
                confirm_request = True

            else:
                if all(x in session for x in ['ballotdelete', 'ballotconfirm']):
                    saving = True
        else:
            # Force-clear session flags on fresh page load.
            clear_session_flags()

        if saving is True:
            current_user.logger.debug("Remove ballot items: Removing ballot item '%d'" % itemid, indent=1)

            outsql = ['''DELETE FROM ballotitems
                         WHERE clubid='%d' AND eventid='%d' AND itemid='%d';
                      ''' % (current_user.event.clubid, current_user.event.eventid, itemid)]

            # Remove all candidates for the ballot item as well.
            outsql.append('''DELETE FROM candidates
                             WHERE clubid='%d' AND eventid='%d' AND itemid='%d';
                          ''' % (current_user.event.clubid, current_user.event.eventid, itemid))
            _, _, err = db.sql(outsql, handlekey=user)

            if err is not None:
                current_user.logger.flashlog("Remove ballot item failure", "Failed to remove ballot item data:", highlight=True)
                current_user.logger.flashlog("Remove ballot item failure", err)
            else:
                current_user.logger.flashlog(None, "Removed ballot item %d (%s) and all candidates." % (itemid, itemdata['name']), 'info', large=True, highlight=True)
                current_user.logger.info("Remove ballot item %d: Operation completed" % itemid)

            return redirect(url_for('main_bp.showitems'))

        return render_template('ballots/removeitem.html', user=user, admins=ADMINS[current_user.event.clubid],
                                itemdata=itemdata,
                                delete_request=delete_request, confirm_request=confirm_request,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Remove ballot item failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))
