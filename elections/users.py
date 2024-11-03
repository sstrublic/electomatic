#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import os
import re
import traceback
import copy
import uuid
import datetime
import random, string

from flask_login import UserMixin, current_user
from flask import redirect, render_template, url_for, request, session

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from elections import db, app
from elections import loggers
from elections import EVENTCONFIG, USERTYPES, USERS, ADMINS, ALLUSERS

from elections.events import EventConfig
from elections.log import AppLog

import elections.qrcodes as qrcodes

# Users are per-club.
class User(UserMixin):
    def __init__(self, username, usertype="Public", fullname="", clubid=0, eventid=0,
                 active=False, siteadmin=False, clubadmin=False, clubname="", publickey=None, user_uuid=None):

        # UserMixin things.
        self.id = username
        self.authenticated = False
        self.active = active

        # Application specific user things.
        self.usertype = usertype
        self.fullname = fullname
        self.clubid = clubid
        self.eventid = eventid
        self.siteadmin = siteadmin
        self.clubadmin = clubadmin

        # Site admins are always club admins.
        if self.siteadmin is True:
            self.clubadmin = True

        # Public users can have a key used to directly log into an event which can be passed during login.
        self.publickey = publickey

        # Internal tracking variable for this user's login status.
        self.loggedin = False

        # Everyone starts with a copy of the global event config.  That way we can change it as we need
        # before selecting the 'real' event.
        self.event = copy.copy(EVENTCONFIG)

        # Cache the club name for easier rendering.
        self.clubname = clubname

        # Create a logger instance for this user based on the club.
        self.logger = AppLog(clubid, 0, app.config.get('LOG_BASENAME'), app.config.get('LOG_DOWNLOAD_FOLDER'), user=username)
        self.logid = AppLog.get_id(clubid)

        # Initialize the UUID for this user.  We only need the string aspect for session tracking.
        if user_uuid is not None:
            self.uuid = user_uuid
            self.logger.info("Using provided user UUID '%s'" % self.uuid, indent=1, propagate=True)
        else:
            self.uuid = str(uuid.uuid4())
            self.logger.info("Created user UUID '%s'" % self.uuid, indent=1, propagate=True)

        # Set the last-updated time for the object, so we can age it out.
        self.last_updated = datetime.datetime.now()
        self.logger.debug("Initialized UUID '%s' last-updated time" % self.uuid, indent=1)


    # Create all user objects from the database with username, user type and as not-authenticated.
    def fetch_users():
        loggers[AppLog.get_id()].info("Loading users")

        outsql = ['''SELECT *
                    FROM clubs;
                 ''']
        outsql.append('''SELECT *
                         FROM users
                         ORDER BY clubid ASC;
                       ''')

        _, data, err = db.sql(outsql, handlekey='system')
        if err is not None:
            loggers[AppLog.get_id()].critical("Failed to access users in database!")
            return False

        # The clubs are the furst 'dbresults' in the list.
        # The users are the second 'dbresults' in the list.
        clubs = data[0]
        userdata = data[1]

        # Initialize the in-memory cache for all the clubs.
        for c in clubs:
            clubid = c['clubid']
            USERS[clubid] = []
            ADMINS[clubid] = []

        # Add the users to the in-memory cache.
        # Users within a club have a unique ID, so this is indexed by that ID.
        for user in userdata:
            username = user['username']
            usertype = user['usertype']
            clubid = user['clubid']

            # Create the unique user ID by club_id and username (id).
            user_id = '%d_%s' % (clubid, username)

            # Create the bin for all User objects with this username.
            ALLUSERS[user_id] = {}

            # If the user is a siteadmin, add them to all the things.
            if user['siteadmin'] is True:
                for c in clubs:
                    USERS[c['clubid']].append(username)
                    ADMINS[c['clubid']].append(username)

            else:
                # Everyone is a user.
                if username not in USERS[clubid]:
                    USERS[clubid].append(username)

                # Add as an Admin.
                if usertype == "Admin" and username not in ADMINS[clubid]:
                    ADMINS[clubid].append(username)

                loggers[AppLog.get_id(clubid)].info("Club ID %d: Loaded user '%s' as '%s'" % (clubid, username, usertype), indent=1)

        loggers[AppLog.get_id()].info("Loaded users")
        return True


    # Find a user in the database.
    def find_user(username, clubid=0):
        # If the user is in the database, retrieve the user data.
        outsql = '''SELECT *
                    FROM users
                    WHERE clubid='%d' AND username='%s';
                    ''' % (clubid, username.replace("'", "''"))
        _, userdata, _ = db.sql(outsql, handlekey='system')
        # The return data is the first 'dbresults' in the list.
        userdata = userdata[0]

        if len(userdata) > 0:
            return userdata[0]
        else:
            return None


    # Find a user by public key.  Public keys are unique so assured to find the specific one we want.
    def find_user_by_public_key(key):
        outsql = '''SELECT *
                    FROM users
                    WHERE publickey='%s';
                    ''' % (key)
        _, userdata, _ = db.sql(outsql, handlekey='system')

        # The return data is the first 'dbresults' in the list.
        userdata = userdata[0]

        if len(userdata) > 0:
            return userdata[0]
        else:
            return None


    # Find this user in the object cache.
    def find_in_object_cache(user_id, user_uuid):
        if user_id in ALLUSERS and user_uuid in ALLUSERS[user_id]:
            return ALLUSERS[user_id][user_uuid]

        return None

    # Add this User object to the user object cache.
    def add_to_object_cache(userobj, user_uuid=None):
        # Add to the all-users cache.
        user_id = userobj.get_userid()
        if user_id not in ALLUSERS:
            ALLUSERS[user_id] = {}

        if user_uuid is None:
            user_uuid = userobj.get_uuid()

        # Add the object to the all-users cache under the object's UUID.
        ALLUSERS[user_id][user_uuid] = userobj

        userobj.logger.info("Added user '%s' to all-users cache as '%s'" % (user_id, user_uuid), indent=1, propagate=True)

        # Set the last-updated time for the object, so we can age it out.
        userobj.last_updated = datetime.datetime.now()
        userobj.logger.debug("Reset UUID '%s' last-updated time" % user_uuid, indent=1)

        # Return the UUID to allow the session to track the data.
        return user_uuid

    # Remove this user/UUID from the object cache.
    def remove_from_object_cache(user_id, user_uuid, userobj=None):
        if userobj is not None:
            logger = userobj.logger
        else:
            logger = AppLog[AppLog.get_id()]

        if user_id in ALLUSERS:
            if user_uuid in ALLUSERS[user_id]:
                ALLUSERS[user_id].pop(user_uuid)
                logger.info("Removed user '%s' (%s) from all-users cache" % (user_id, user_uuid), indent=1, propagate=True)
            else:
                logger.error("Did not find user UUID '%s' in all-users cache" % user_uuid, indent=1, propagate=True)
        else:
            logger.error("Did not find user ID '%s' in all-users cache" % user_id, indent=1)


    # Add the club to the user caches.
    def add_club_to_user_cache(clubid):
        # Create the club's user caches.
        USERS[clubid] = []
        ADMINS[clubid] = []

        # Since the club is being initialized add all siteadmin users to the user caches
        # # to allow for user management of the club.
        outsql = '''SELECT *
                    FROM users
                    WHERE siteadmin = True
                    ORDER BY clubid ASC;
                  '''
        _, data, err = db.sql(outsql, handlekey='system')
        if err is not None:
            loggers[AppLog.get_id()].critical("Failed to access users in database!")
            return False

        # The user data is the first 'dbresults' in the list.
        userdata = data[0]
        for user in userdata:
            USERS[clubid].append(user['username'])
            ADMINS[clubid].append(user['username'])

        loggers[AppLog.get_id()].info("Initialized user caches for Club ID %d" % clubid, indent=1, propagate=True)


    # Verify the user given the user object and a provided password.
    def verify_user(self, userpass):
        self.authenticated = False
        self.active = False

        # Verify the user exists and fetch what we know.
        userdata = User.find_user(self.id, self.clubid)
        if userdata is None:
            errmsg = "User '%s' not found for Club ID %d" % (self.id, self.clubid)
            self.logger.error(errmsg, indent=1)
            self.set_login_status(False)
            return False, errmsg

        # Check the given password against the hashed databsae value.
        if check_password_hash(userdata['passwd'], userpass) is False:
            errmsg = "Invalid password"
            self.logger.error(errmsg, indent=1)
            self.set_login_status(False)
            return False, errmsg

        # If the user is not active, they cannot be authenticated.
        if userdata['active'] is False:
            errmsg = "User '%s' has been deactivated" % self.id
            self.logger.error(errmsg, indent=1)
            self.set_login_status(False)
            return False, errmsg

        # Update the user type and indicate they're authenticated and active.
        self.usertype = userdata['usertype']
        self.authenticated = True
        self.active = True

        self.logger.info("Verified user '%s' as type '%s'" % (self.id, self.usertype), indent=1, propagate=True)

        return True, None


    # Find the User session in the cache.
    def get_user(clubid, username, user_uuid):
        user_id = '%d_%s' % (clubid, username)
        sessions = ALLUSERS.get(user_id, {})

        # IF the UUID is listed for this user, fetch the User object for it.
        if user_uuid is not None and user_uuid in sessions:
            return sessions[user_uuid]

        # Nope!
        return None


    # Add a user to the database.
    # Users work against the current club ID, so we reuse the user's club ID for this purpose.
    def add_user(self, username, userpass, usertype, fullname, active, siteadmin=False, clubadmin=False, eventid=0):
        # Verify the user was not found.
        if User.find_user(username, self.clubid) is not None:
            if self.clubid == 0:
                return False, "User '%s' already exists" % username
            else:
                return False, "User '%s' already exists for Club ID %d" % (username, self.clubid)

        # Search for this username in the siteadmins list (cannot duplicate anyone in that group).
        if self.clubid != 0 and User.find_user(username) is not None:
            return False, "User '%s' already exists" % username

        # If the user type is not valid, reject.
        if usertype not in USERTYPES:
            errmsg = "User '%s' does not have a valid type ('%s')" % (username, usertype)
            self.logger.error(errmsg)
            return False, errmsg

        # Generate the public user's login key.  NULL is inserted for non-public users.
        publickey = 'NULL'
        if usertype == 'Public':
            publickey, _ = self.generate_public_user_key(username, updatedb=False)

        # Add the user to the database.
        outsql = '''INSERT INTO users (clubid, eventid, username, passwd, usertype, fullname, active, siteadmin, clubadmin, publickey, created, updated)
                    VALUES('%d', '%d', '%s', '%s', '%s', '%s', %s, %s, %s, '%s', NOW(), NOW())
                    ''' % (self.clubid, eventid, username.replace("'", "''"), generate_password_hash(userpass),
                           usertype, fullname, active, siteadmin, clubadmin, publickey)
        _, _, err = db.sql(outsql, handlekey=self.get_userid())
        if err is not None:
            errmsg = "Failed to create user '%s': %s" % (username, err)
            self.logger.error(errmsg)
            return False, errmsg

        # Add the user to the all-users object cache.
        user_id = '%d_%s' % (self.clubid, username)
        if ALLUSERS.get(user_id) is not None:
            errmsg = "User '%s' already exists in user object cache" % user_id
            return False, errmsg

        ALLUSERS[user_id] = {}
        self.logger.debug("Added user '%s' to all-users cache" % user_id, indent=1)

        # If the user is a siteadmin, add them to all clubs' caches.
        if siteadmin is True:
            outsql = ['''SELECT *
                        FROM clubs;
                      ''']
            _, data, err = db.sql(outsql, handlekey=self.get_userid())
            if err is not None:
                loggers[AppLog.get_id()].critical("Failed to access users in database!")
                return None

            # The clubs are the first 'dbresults' in the list.
            clubs = data[0]

            # Add the user to the userlist caches for all the clubs.
            for c in clubs:
                clubid = c['clubid']
                USERS[clubid].append(username)
                ADMINS[clubid].append(username)

                loggers[AppLog.get_id(clubid)].info("Add siteadmin user '%s' to club %d cache" % (username, clubid), propagate=True)

        else:
            # Everyone is a user.
            if username not in USERS[self.clubid]:
                USERS[self.clubid].append(username)
                self.logger.debug("Added user '%s' to users cache" % username, indent=1)

            # Add as an Admin.
            if usertype == "Admin" and username not in ADMINS[self.clubid]:
                ADMINS[self.clubid].append(username)
                self.logger.debug("Added user '%s' to admins cache" % username, indent=1)

        self.logger.info("Created user '%s' of type '%s'" % (username, usertype), indent=1, propagate=True)

        return True, None


    # Update a user.  Note that the user name may not be changed.
    # Users work against the current club ID, so we reuse the user's club Id for this purpose.
    def update_user(self, username, fullname, usertype, active, clubadmin, eventid=0):
        loggers[AppLog.get_id(self.clubid)].info("Updating user: '%s'" % username, propagate=True)

        # Verify the user was not found.
        if User.find_user(username, self.clubid) is None:
            if self.clubid == 0:
                return False, "User '%s' was not found" % username
            else:
                return False, "User '%s' was not found in Club ID %d" % (username, self.clubid)

        # Verify user type is valid and full name is not empty.
        if usertype not in USERTYPES:
            errmsg = "User '%s' does not have a valid type ('%s')" % (username, usertype)
            self.logger.error(errmsg, indent=1)
            return False, errmsg

        if fullname is None or len(fullname) == 0:
            errmsg = "User '%s' does not have a valid full name" % username
            self.logger.error(errmsg, indent=1)
            return False, errmsg

        # Update the user from the object's fields.
        # Note that the password canot be changed here; it can only be reset.
        # We never store passwords in the clear and cannot retrieve them.
        outsql = '''UPDATE users
                    SET fullname='%s', usertype='%s', eventid='%d', active=%s, clubadmin=%s, updated=NOW()
                    WHERE clubid='%d' AND username='%s';
                    ''' % (fullname, usertype, eventid, active, clubadmin, self.clubid, username.replace("'", "''"))
        _, _, err = db.sql(outsql, handlekey=self.get_userid())
        if err is not None:
            errmsg = "Failed to update user '%s': %s" % (username, err)
            self.logger.error(errmsg, indent=1)
            return False, errmsg

        # Fetch the user object from cache.
        user_id = '%d_%s' % (self.clubid, username)

        # Update all users in the all-users cache for this User.
        sessions = ALLUSERS.get(user_id, {})
        for user_uuid in sessions:
            thisuser = sessions[user_uuid]

            # Update the object.
            thisuser.fullname = fullname
            thisuser.usertype = usertype
            thisuser.active = active
            thisuser.clubadmin = clubadmin

        # No need to update the user-access caches for siteadmins because you can't change their type.
        if self.siteadmin is False:
            self.logger.debug("Updating user caches for club ID '%d'" % self.clubid, indent=1)

            if self.id in ADMINS[self.clubid] and self.usertype not in ["Admin"]:
                ADMINS[self.clubid].remove(self.id)
                self.logger.debug("Removed user '%s' from admins cache" % username, indent=2)

            # Add as an Admin if the user is active.
            if self.usertype == "Admin" and self.id not in ADMINS[self.clubid] and self.active is True:
                ADMINS[self.clubid].append(self.id)
                self.logger.debug("Added user '%s' to admins cache" % username, indent=2)

        self.logger.info("Updated user '%s' as fullname '%s', user type '%s', active %s" %
                    (username, fullname, usertype, active), indent=1, propagate=True)
        return True, None


    # Remove a user.
    # Users work against the current club ID, so we reuse the user's club Id for this purpose.
    def remove_user(self, username):
        # Verify the user exists.
        userdata = User.find_user(username, self.clubid)
        if userdata is None:
            if self.clubid == 0:
                return False, "User '%s' was not found" % username
            else:
                return False, "User '%s' was not found in Club ID %d" % (username, self.clubid)

        user_id = '%d_%s' % (self.clubid, username)

        # Remove all users in the all-users cache for this User.
        uuids_list = list(ALLUSERS.get(user_id, {}))
        for user_uuid in uuids_list:
            thisuser = ALLUSERS[user_id][user_uuid]

            # Remove the user object from the cache.
            User.remove_from_object_cache(user_id, user_uuid, self)

            # Even though we're removing the object, we'll clear it first for any in-flight operations.
            thisuser.authenticated = False
            thisuser.active = False
            thisuser.loggedin = False

            # Force-expire the user object.
            thisuser.last_updated = datetime.datetime.min

        # Remove the dict entry for this user.
        ALLUSERS.pop(user_id)

        self.logger.debug("Removed user '%s' from all-users cache" % user_id, indent=1)

        # If the user is a siteadmin, remove them from all caches.
        siteadmin = userdata['siteadmin']
        if siteadmin is True:
            outsql = ['''SELECT *
                        FROM clubs;
                      ''']

            _, data, err = db.sql(outsql, handlekey=self.get_userid())
            if err is not None:
                loggers[AppLog.get_id()].critical("Failed to access users in database!")
                return False, err

            # The clubs are the furst 'dbresults' in the list.
            clubs = data[0]

            # Update the in-memory cache for all the clubs.
            for c in clubs:
                clubid = c['clubid']
                if username in USERS[clubid]:
                    USERS[clubid].remove(username)

                if username in ADMINS[clubid]:
                    ADMINS[clubid].remove(username)

                self.logger.debug("Removed siteadmin user '%s' from all caches" % username, indent=1)
        else:
            clubid = self.clubid

            # Remove the user from the userlist caches.
            if username in USERS[clubid]:
                USERS[clubid].remove(username)
                self.logger.debug("Removed user '%s' from users cache" % username, indent=2)

            if username in ADMINS[clubid]:
                ADMINS[clubid].remove(username)
                self.logger.debug("Removed user '%s' from admins cache" % username, indent=2)

        # Delete the user from the database.
        outsql = '''DELETE FROM users
                    WHERE clubid='%d' AND username='%s';
                    ''' % (self.clubid, username.replace("'", "''"))
        _, _, err = db.sql(outsql, handlekey=self.get_userid())
        if err is not None:
            errmsg = "Failed to delete user '%s': %s" % (username, err)
            self.logger.error(errmsg, indent=1)
            return False, errmsg

        self.logger.info("Deleted user '%s' from the database and memory caches" % username, indent=1, propagate=True)
        return True, None


    # Reset a user's password.
    # Users work against the current club ID, so we reuse the user's club Id for this purpose.
    def reset_password(self, username, userpass):
        # Verify the user exists.
        if User.find_user(username, self.clubid) is None:
            if self.clubid == 0:
                return False, "User '%s' was not found" % username
            else:
                return False, "User '%s' was not found in Club ID %d" % (username, self.clubid)

        # Set the new password.  This presumes the password was previously validated.
        outsql = '''UPDATE users
                    SET passwd='%s', updated=NOW()
                    WHERE clubid='%d' AND username='%s';
                    ''' % (generate_password_hash(userpass), self.clubid, username.replace("'", "''"))
        _, _, err = db.sql(outsql, handlekey=self.get_userid())
        if err is not None:
            errmsg = "Failed to reset password for user '%s': %s" % (username, err)
            self.logger.error(errmsg, indent=1)
            return False, errmsg

        self.logger.info("Reset password for user '%s'" % username, indent=1, propagate=True)
        return True, None


    # Generate the user's public key for direct login.
    # Users work against the current club ID, so we reuse the user's club ID for this purpose.
    # This only applies to Public users.
    def generate_public_user_key(self, username, updatedb=True):
        # Generate a 32-character public key.  This will be part of a QR code so it should be inconvenient to type...
        publickey = ''.join(random.choices(string.ascii_uppercase + string.ascii_lowercase + string.digits, k = 32))

        # If not updating the databse, we're just being asked to generate the key during an add-user operation.
        if updatedb is True:
            # Verify the user exists.
            userobj = User.find_user(username, self.clubid)
            if userobj  is None:
                if self.clubid == 0:
                    return None, "User '%s' was not found" % username
                else:
                    return None, "User '%s' was not found in Club ID %d" % (username, self.clubid)

            # Only public users count here.
            if userobj.usertype != 'Public':
                return None, "User '%s' is not a Public user type" % username

            # Store the string in the database for the user.
            outsql = '''UPDATE users
                        SET publickey='%s', updated=NOW()
                        WHERE clubid='%d' AND username='%s';
                        ''' % (publickey, self.clubid, username.replace("'", "''"))
            _, _, err = db.sql(outsql, handlekey=self.get_userid())
            if err is not None:
                errmsg = "Failed to generate key for public user '%s': %s" % (username, err)
                self.logger.error(errmsg, indent=1)
                return None, errmsg

        self.logger.info("Generated key for public user '%s'" % username, indent=1, propagate=True)
        return publickey, None


    # Fetch the public user's public key.
    # Users work against the current club ID, so we reuse the user's club ID for this purpose.
    # This only applies to Public users.
    def get_public_user_key(self, username):
        # Verify the user exists.
        userobj = User.find_user(username, self.clubid)
        if userobj  is None:
            if self.clubid == 0:
                return None, "User '%s' was not found" % username
            else:
                return None, "User '%s' was not found in Club ID %d" % (username, self.clubid)

        # Only public users count here.
        if userobj.usertype != 'Public':
            return None, "User '%s' is not a Public user type" % username

        return userobj.publickey, None


    # Mixin method we're overriding to return the id (username).
    def get_id(self):
        return self.id

    # Mixin method we're overriding for authentication status.
    def is_authenticated(self):
        return self.authenticated

    # Mixin method we're overriding for active status.
    def is_active(self):
        return self.active

    # Method to get the unique user ID for logins.
    def get_userid(self):
        # Site admins always get authenticated as club ID 0 unless it is the single-tenant club ID of 1.
        if self.siteadmin is True and self.clubid != 1:
            return '0_%s' % self.id
        else:
            return '%d_%s' % (self.clubid, self.id)

    # Method to return the user object's UUID.
    def get_uuid(self):
        return self.uuid

    # Set login status: login True = logged in.
    def set_login_status(self, login=False):
        self.loggedin = login

    # Get login status: True = logged in.
    def get_login_status(self):
        return self.loggedin


    # Set the club ID (and cache the club name).
    def set_club(self, clubid):
        self.clubid = clubid

        # Get a copy of the default event config and initialize it with club data.
        self.event = copy.copy(EVENTCONFIG)

        outsql = '''SELECT clubname, icon, homeimage FROM clubs WHERE clubid='%d';''' % clubid
        _, data, _ = db.sql(outsql, handlekey=self.get_userid())

        if len(data) > 0:
            # The club is the first entry in the first results list block.
            club = data[0][0]
            self.clubname = club['clubname']
            self.event.icon = club['icon']
            self.event.homeimage = club['homeimage']

        else:
            self.clubname = "Unknown"

        self.event.clubid = clubid

        # Create the logger object for this club so we can log against it going forward.
        self.logger = AppLog(clubid, 0, app.config.get('LOG_BASENAME'), app.config.get('LOG_DOWNLOAD_FOLDER'), user=self.id)
        self.logid = AppLog.get_id(clubid)

        self.logger.info("Set club as %d ('%s') for user '%s'" % (clubid, self.clubname, self.id), indent=1, propagate=True)


    # Set the event configuration for this user's session.
    def set_event(self, eventid):
        self.eventid = eventid

        # Override the event's icon and/or home image files with the club's if the event's files are the same as the defaults.
        outsql = '''SELECT clubname, icon, homeimage FROM clubs WHERE clubid='%d';''' % self.clubid
        _, data, _ = db.sql(outsql, handlekey=self.get_userid())
        club = data[0][0]

        if eventid == 0:
            # 0 is reserved for 'no event'.  Make a copy of the global config.
            self.event = copy.copy(EVENTCONFIG)

            # Update the club ID with our current club ID.
            self.event.clubid = self.clubid

            # If the icon or home iamges files are the same as the default, use the club's files.
            if self.event.icon == app.config.get('DEFAULT_APPICON'):
                self.event.icon = club['icon']

            if self.event.homeimage == app.config.get('DEFAULT_HOMEIMAGE'):
                self.event.homeimage = club['homeimage']

        else:
            # Create an EventConfig instance and initialize from the global config, with session data and the chosen event ID.
            self.event = EventConfig(version=app.config.get('VERSION'), user=self.get_userid(), clubid=self.clubid, eventid=eventid)

            # If the icon or home images files are missing, use the club's files (which are one directory above).
            if self.event.icon is None:
                self.event.icon = '../%s' % club['icon']

            if self.event.homeimage is None:
                self.event.homeimage = '../%s' % club['homeimage']

        # Create the logger objects for this event so we can log against them going forward.
        self.logger = AppLog(self.clubid, eventid, app.config.get('LOG_BASENAME'), app.config.get('LOG_DOWNLOAD_FOLDER'), user=self.id)

        # Only events get a vote log.
        if eventid != 0:
            self.votelogger = AppLog(self.clubid, eventid, app.config.get('VOTELOG_BASENAME'), app.config.get('LOG_DOWNLOAD_FOLDER'), user=self.id)

        self.logid = AppLog.get_id(self.clubid, eventid)

        self.logger.info("Set event as %d for user '%s'" % (eventid, self.id), indent=1, propagate=True)


    # Fetch event/other user data as a common item for rendering.
    def get_render_data(self):
        # version     = data[0]
        # title       = data[1]
        # icon        = data[2]
        # homeimage   = data[3]
        # clubid      = data[4]
        # eventid     = data[5]
        # siteadmin   = data[6]
        # clubname    = data[7]
        # tenancy     = data[8]
        # event_login = data[9]
        # public_login = data[10]
        # clubadmin   = data[11]
        # event locked = data[12]

        return [self.event.version,
                self.event.title.replace("''", "'"),
                self.event.icon,
                self.event.homeimage,
                str(self.clubid),
                str(self.event.eventid),
                self.siteadmin,
                self.clubname.replace("'", "''"),
                app.config.get("MULTI_TENANCY"),
                session.get('event_login', False),
                session.get('public_login', False),
                self.clubadmin,
                self.event.locked]


# Check password complexity requirements.
def checkPasswordComplexity(password):

    # For testing: disable the complexity check.
    if app.config.get("PASSWORD_COMPLEXITY_CHECK", True) is False:
        return None

    # Password requires:
    # - At least N characters as defined in config file (default: 6)
    # - At least one upper and lowercase character
    # - At least one number
    err = []
    password_len = app.config.get("PASSWORD_MIN_LENGTH")

    if len(password) < password_len:
        err.append("Password must be at least %d characters long." % password_len)

    # Searching for digits
    if re.search(r"\d", password) is None:
        err.append("Password must include at least one number.")

    # Searching for uppercase
    if re.search(r"[A-Z]", password) is None:
        err.append("Password must include at least one uppercase character.")

    # Searching for lowercase
    if re.search(r"[a-z]", password) is None:
        err.append("Password must include at least one lowercase character.")

    if len(err) == 0:
        return None

    return err


# Add a user.
def addUser(user):
    try:
        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Add user operation canceled.", 'info')
            return redirect(url_for('main_bp.adduser'))

        current_user.logger.info("Displaying: Add a user")

        # Fetch fields.
        # We do NOT escape the username as it is done individually in each user class method
        # that accesses the database.  Otherwise, thre's too many palces to twiddle with it.
        username = request.values.get('username', "").strip()
        fullname = request.values.get('fullname', "").strip().replace("'", "''")
        usertype = request.values.get('usertype', "")
        userpass = request.values.get('passwd', "").strip().replace("'", "''")
        confirmpass = request.values.get('confirmpasswd', "").strip().replace("'", "''")
        eventid = request.values.get('eventid', 0)

        # Convert event ID to an integer.  It's a selectbox, so it will be an integet from the form.
        eventid = int(eventid)

        # Get the events available for assigning to users.
        current_user.logger.debug("Adding a user: Fetching events", indent=1)
        outsql = '''SELECT *
                    FROM events
                    WHERE clubid='%d';
                 ''' % current_user.clubid
        _, data, _ = db.sql(outsql, handlekey=current_user.get_userid())

        events = data[0]
        eventdata = []
        for e in events:
            eventdata.append([e['eventid'], e['title']])

        # We fetch the active state and club admin setting only if saving.
        active = None
        clubadmin = None

        if request.values.get('savebutton'):
            current_user.logger.debug("Adding a user: Saving changes requested", indent=1)

            active = request.values.get('active', False)
            if active == 'True':
                active = True

            # At the site admin level, only site admins can be created.  They are always club admins.
            if current_user.clubid == 0:
                current_user.logger.debug("Adding a user: Defaulting clubadmin to True for site admin", indent=1)
                clubadmin = True

            # At the event level, only non-club admin Admins can be created.
            elif current_user.event.eventid != 0 or usertype != 'Admin':
                current_user.logger.debug("Adding a user: Defaulting clubadmin to False for user type '%s'" % usertype, indent=1)
                clubadmin = False

            else:
                clubadmin = request.values.get('clubadmin', False)
                if clubadmin == 'True':
                    clubadmin = True

            # If club ID is 0, then we're adding to the site admins list.  That's the only way it can happen.
            siteadmin = False
            if current_user.clubid == 0:
                current_user.logger.debug("Adding a user: Defaulting siteadmin to True", indent=1)
                siteadmin = True
                usertype = 'Admin'

            # Verify fields.
            field_checklist = [username, fullname, userpass, confirmpass]
            if current_user.clubid != 0:
                field_checklist.append(usertype)

            def return_default(msg, propagate=False):
                if type(msg) is list:
                    for m in msg:
                        current_user.logger.flashlog("Add User Failure", m, propagate=propagate)
                else:
                    current_user.logger.flashlog("Add User Failure", msg, propagate=propagate)

                return render_template('users/adduser.html', user=user, clubid=current_user.clubid, admins=ADMINS[current_user.clubid],
                                        usertypes=USERTYPES, username=username, fullname=fullname, usertype=usertype,
                                        eventdata=eventdata, eventid=eventid, active=active, clubadmin=clubadmin,
                                        configdata=current_user.get_render_data())

            if any(len(x.strip()) == 0 for x in field_checklist):
                return return_default("All fields must be populated.")

            # Only club admins can add accounts.
            if current_user.clubadmin is False:
                return return_default("Only Club-level administrators can add Users.")

            # Passwords must match.
            if confirmpass != userpass:
                return return_default("Passwords do not match.")

            # if the user is a Public user, set the event ID.
            if usertype == 'Public':
                if app.config.get('MULTI_TENANCY') is False:
                    # In single-tenant mode, default the event id to the current event ID.
                    current_user.logger.debug("Adding a user: Defaulting Event ID to %d for user type '%s'" % (current_user.event.eventid, usertype), indent=1)
                    eventid = current_user.event.eventid
            else:
                current_user.logger.debug("Adding a user: Defaulting Event ID to 0 for user type '%s'" % usertype, indent=1)
                eventid = 0

            # Check minimal password complexity.
            err = checkPasswordComplexity(userpass)
            if err is not None:
                return return_default(err)

            # Add the user.
            result, errmsg = current_user.add_user(username, userpass, usertype, fullname, active, siteadmin=siteadmin, clubadmin=clubadmin, eventid=eventid)
            if result is False:
                current_user.logger.flashlog("Add User Failure", "%s." % errmsg, propagate=True)
            else:
                current_user.logger.flashlog(None, "Added User '%s':" % username, 'info', propagate=True)
                current_user.logger.flashlog(None, "Full Name: %s" % fullname.replace("''", "'"), 'info', highlight=False, indent=True, propagate=True)
                current_user.logger.flashlog(None, "User Type: %s%s" % (usertype, " (Site Admin)" if siteadmin is True else ""), 'info',
                                             highlight=False, indent=True, propagate=True)

                if eventid != 0:
                    current_user.logger.flashlog(None, "Assigned Event: %d" % eventid, 'info', highlight=False, indent=True, propagate=True)

                if usertype == 'Admin':
                    current_user.logger.flashlog(None, "Club Admin: %s" % ("Yes" if clubadmin else "No"), 'info', highlight=False, indent=True, propagate=True)

                current_user.logger.flashlog(None, "Active: %s" % ("Yes" if active else "No"), 'info', highlight=False, indent=True, propagate=True)

                current_user.logger.info("Adding a user: Operation completed")

                return redirect(url_for('main_bp.adduser'))

        return render_template('users/adduser.html', user=user, clubid=current_user.clubid, admins=ADMINS[current_user.clubid],
                                usertypes=USERTYPES, username=username, fullname=fullname, usertype=usertype,
                                eventdata=eventdata, eventid=eventid, active=active, clubadmin=clubadmin,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Add User failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.critical("Unexpected exception:")
        current_user.logger.critical(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Edit a user.
def editUser(user, username=None):
    try:
        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Edit user operation canceled.", 'info')
            return redirect(url_for('main_bp.edituser'))

        current_user.logger.info("Displaying: Edit a user")

        # If saving the information, set this for later.
        saving = False
        if request.values.get('savebutton'):
            current_user.logger.info("Editing a user: Saving changes requested", indent=1)
            saving = True

        # Get the username to look up who to edit.
        # We do NOT escape the username's apostrophes as it's done in the user class.
        if username is None:
            username = request.values.get('username', "").strip()

        if len(username) == 0:
            username = None

        fullname = None
        usertype = None
        active = None
        clubadmin = None
        eventid = None
        eventdata = []
        isuser = False

        if username is not None:
            userdata = User.find_user(username, current_user.clubid)
            if userdata is None:
                if current_user.clubid == 0:
                    current_user.logger.flashlog("Edit User Failure", "User '%s' was not found." % username)
                else:
                    current_user.logger.flashlog("Edit User Failure", "User '%s' was not found for Club ID %d." % (username, current_user.clubid))

                return redirect(url_for('main_bp.edituser'))

            # If the user is the logged in user, set a flag which will disable the form from allowing edit of some fields.
            if user == username and current_user.clubid == userdata['clubid']:
                isuser = True

            eventid = request.values.get('eventid', 0)

            # Convert event ID to an integer.  It's a selectbox, so it will be an integer from the form.
            eventid = int(eventid)

            # Get the events available for assigning to users.
            current_user.logger.debug("Editing a user: Fetching events", indent=1)
            outsql = '''SELECT *
                        FROM events
                        WHERE clubid='%d';
                    ''' % current_user.clubid
            _, data, _ = db.sql(outsql, handlekey=current_user.get_userid())

            events = data[0]
            eventdata = []
            for e in events:
                eventdata.append([e['eventid'], e['title']])

            if saving is True:
                # Fetch fields.
                fullname = request.values.get('fullname', "").strip().replace("'", "''")

                if isuser is True:
                    usertype = userdata['usertype']
                    active = userdata['active']
                    clubadmin = userdata['clubadmin']
                else:
                    # Club ID 0 means this is a site admin, so user type and club admin value does not apply.
                    if current_user.clubid == 0:
                        usertype = 'Admin'
                        clubadmin = True
                    else:
                        usertype = request.values.get('usertype', "")
                        clubadmin = request.values.get('clubadmin', False)
                        if clubadmin == 'True':
                            clubadmin = True

                    active = request.values.get('active', False)
                    if active == 'True':
                        active = True

                # Verify fields.
                field_checklist = [fullname]
                if current_user.clubid != 0:
                    field_checklist.append(usertype)

                def return_default(msg, propagate=False):
                    current_user.logger.flashlog("Edit User Failure", msg, propagate=propagate)
                    return render_template('users/edituser.html', user=user, clubid=current_user.clubid, admins=ADMINS[current_user.clubid],
                                            usertypes=USERTYPES, username=username, fullname=userdata['fullname'], usertype=userdata['usertype'],
                                            active=userdata['active'], clubadmin=userdata['clubadmin'], isuser=isuser,
                                            eventid=eventid, eventdata=eventdata,
                                            configdata=current_user.get_render_data())

                if any(len(x.strip()) == 0 for x in field_checklist):
                    return return_default("All fields must be populated.")

                # You cannot deactivate the currently logged in account.
                if isuser and active is False:
                    return return_default("The currently logged in account cannot be deactivated.")

                # Only club level admins can make new club level admins.
                if current_user.clubadmin is False:
                    if clubadmin != userdata['clubadmin']:
                        return return_default("Only Club-level administrators can modify Club administration settings.")
                else:
                    if current_user.clubid == 0 and clubadmin == False:
                        return return_default("Site administrators must always be Club-level administrators.")

                # At the event level, only non-club admin Admins can be created.
                if current_user.event.eventid != 0 or usertype != 'Admin':
                    current_user.logger.debug("Editing a user: Defaulting clubadmin to False for user type '%s'" % usertype, indent=1)
                    clubadmin = False

                # You cannot deactivate all admin accounts.
                if username in ADMINS[current_user.clubid]:
                    outsql = '''SELECT COUNT(*) filter (where "active") AS activecount,
                                       COUNT(*) filter (where "clubadmin" and "active") AS clubadminactivecount
                                FROM users
                                WHERE usertype='Admin' AND clubid='%d';
                             ''' % current_user.clubid
                    _, data, _ = db.sql(outsql, handlekey=current_user.get_userid())

                    # We are guaranteed to get a result even if the counts are 0.
                    data = data[0][0]
                    activecount = data['activecount']
                    clubadminactivecount = data['clubadminactivecount']

                    # Cannot deactivate the last active admin account.
                    if activecount == 1:
                        if userdata['active'] is True and active is False:
                            return return_default("The last active administrator account cannot be deactivated.")

                    # If this is also a club admin account, it cannot be deactivated if it's the last one.
                    if clubadminactivecount == 1:
                        if userdata['clubadmin'] is True:
                            if clubadmin is False or userdata['active'] is True and active is False:
                                return return_default("The last Club-level administrator account cannot be deactivated.")

                    # You cannot change type of the last admin account.
                    if usertype != 'Admin' and len(ADMINS[current_user.clubid]) == 1:
                        return return_default("The last administrator account cannot be converted to a different type.")

                # if the user is a Public user, set the event ID.
                if usertype == 'Public':
                    if app.config.get('MULTI_TENANCY') is False:
                        # In single-tenant mode, default the event id to the current event ID.
                        current_user.logger.debug("Editing a user: Defaulting Event ID to %d for user type '%s'" % (current_user.event.eventid, usertype), indent=1)
                        eventid = current_user.event.eventid
                else:
                    current_user.logger.debug("Editing a user: Defaulting Event ID to 0 for user type '%s'" % usertype, indent=1)
                    eventid = 0

                # Update the user:
                result, err = current_user.update_user(username, fullname, usertype, active, clubadmin, eventid=eventid)
                if result is False:
                    current_user.logger.flashlog("Edit User Failure", "Failed to update user: %s." % err, propagate=True)
                    return redirect(url_for('main_bp.edituser'))
                else:
                    current_user.logger.flashlog(None, "Updated User '%s':" % username, 'info', propagate=True)
                    current_user.logger.flashlog(None, "Full Name: %s" % fullname.replace("''", "'"), 'info', highlight=False, indent=True, propagate=True)
                    current_user.logger.flashlog(None, "User Type: %s%s" % (usertype, " (Site Admin)" if current_user.siteadmin is True else ""), 'info',
                                                 highlight=False, indent=True, propagate=True)

                    if eventid != 0:
                        current_user.logger.flashlog(None, "Assigned Event: %d" % eventid, 'info', highlight=False, indent=True, propagate=True)

                    if usertype == 'Admin':
                        current_user.logger.flashlog(None, "Club Admin: %s" % ("Yes" if clubadmin else "No"), 'info', highlight=False, indent=True, propagate=True)

                    current_user.logger.flashlog(None, "Active: %s" % ("Yes" if active else "No"), 'info', highlight=False, indent=True, propagate=True)

                    current_user.logger.info("Editing a user: Operation completed")

                    return redirect(url_for('main_bp.edituser'))
            else:
                # Fetch the fields from the user data.
                fullname = userdata['fullname']
                usertype = userdata['usertype']
                active = userdata['active']
                clubadmin = userdata['clubadmin']
                eventid = userdata['eventid']

        return render_template('users/edituser.html', user=user, clubid=current_user.clubid, admins=ADMINS[current_user.clubid],
                                usertypes=USERTYPES, username=username, fullname=fullname, usertype=usertype, active=active, clubadmin=clubadmin, isuser=isuser,
                                eventid=eventid, eventdata=eventdata,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Edit User failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.critical("Unexpected exception:")
        current_user.logger.critical(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Reset a user's password.
def resetPassword(user):
    try:
        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Reset password operation canceled.", 'info')
            return redirect(url_for('main_bp.resetpassword'))

        current_user.logger.info("Displaying: Reset user password")

        # If saving the information, set this for later.
        saving = False
        if request.values.get('savebutton'):
            current_user.logger.debug("Resetting a password: Saving changes requested", indent=1)
            saving = True

        # Get the username to look up who to edit.
        if user not in ADMINS[current_user.clubid]:
            username = user
        else:
            username = request.values.get('username', "").strip()
            if len(username) == 0:
                username = None

        fullname = None

        if username is not None:
            # If not a club admin, a user may only edit their own password.
            if user != username:
                if current_user.clubadmin is False or user not in ADMINS[current_user.clubid]:
                    current_user.logger.flashlog("Reset Password Failure", "You can only reset your own password.")
                    return redirect(url_for('main_bp.resetpassword'))

            userdata = User.find_user(username, current_user.clubid)
            if userdata is None:
                if current_user.clubid == 0:
                    current_user.logger.flashlog("Reset Password Failure", "User '%s' was not found." % username)
                else:
                    current_user.logger.flashlog("Reset Password Failure", "User '%s' was not found for Club ID %d." % (username, current_user.clubid))

                return redirect(url_for('main_bp.resetpassword'))

            if saving is True:
                # Fetch fields.
                userpass = request.values.get('passwd', "").strip()
                confirmpass = request.values.get('confirmpasswd', "").strip()
                fullname = userdata['fullname']

                # Verify fields.
                if any(len(x.strip()) == 0 for x in [userpass, confirmpass]):
                    current_user.logger.flashlog("Reset Password Failure", "All fields must be populated.")
                    return redirect(url_for('main_bp.resetpassword'))

                # Passwords must match.
                if confirmpass != userpass:
                    current_user.logger.flashlog("Reset Password Failure", "Passwords do not match.")
                    return render_template('users/resetpassword.html', user=user, clubid=current_user.clubid, admins=ADMINS[current_user.clubid],
                                            configdata=current_user.get_render_data(),
                                            username=username, fullname=fullname)

                # Update the user:
                result, err = current_user.reset_password(username, userpass)
                if result is False:
                    current_user.logger.flashlog("Reset Password Failure", "Failed to update user: %s." % err, propagate=True)
                else:
                    if user == username:
                        current_user.logger.flashlog(None, "Your password has been changed.", 'info', propagate=True)
                    else:
                        current_user.logger.flashlog(None, "Password for user '%s' has been changed." % username, 'info', propagate=True)

                    current_user.logger.info("Resetting a password: Operation completed")

                return redirect(url_for('main_bp.resetpassword'))

            else:
                # Fetch the fields from the user data.
                fullname = userdata['fullname']

        return render_template('users/resetpassword.html', user=user, clubid=current_user.clubid, admins=ADMINS[current_user.clubid],
                                configdata=current_user.get_render_data(),
                                username=username, fullname=fullname)

    except Exception as e:
        current_user.logger.flashlog("Reset Password failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.critical("Unexpected exception:")
        current_user.logger.critical(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Remove a user.
def removeUser(user):
    try:
        # Clear any session flags.
        def clear_session_flags():
            for flag in ['userconfirm']:
                if flag in session:
                    current_user.logger.debug("Removing a user: Clearing session flag '%s'" % flag, indent=1)
                    session.pop(flag, None)

        if request.values.get('cancelbutton'):
            current_user.logger.flashlog(None, "Remove user operation canceled.", 'info')
            clear_session_flags()
            return redirect(url_for('main_bp.removeuser'))

        current_user.logger.info("Displaying: Remove a user")

        # If saving the information, set this for later.
        saving = False
        if request.values.get('savebutton'):
            current_user.logger.debug("Removing a user: Saving changes requested", indent=1)
            saving = True

        # Get the username to look up who to remove.
        username = request.values.get('username', "").strip()
        if len(username) == 0:
            username = None

        fullname = None
        usertype = None
        active = None
        clubadmin = None
        title = None

        if username is not None:
            # Find the user.
            userdata = User.find_user(username, current_user.clubid)
            if userdata is None:
                current_user.logger.flashlog("Remove User Failure", "User '%s' was not found." % username)
                return redirect(url_for('main_bp.removeuser'))

            # You cannot remove the account that is logged in.
            if user == username and (current_user.clubid == userdata['clubid']):
                current_user.logger.flashlog("Remove User Failure", "The currently logged in account cannot be removed.", propagate=True)
                return redirect(url_for('main_bp.removeuser'))

            if username in ADMINS[current_user.clubid]:
                # Fetch the number of active admin users and active club-level admin users.
                outsql = '''SELECT COUNT(*) filter (where "active") AS activecount,
                                    COUNT(*) filter (where "clubadmin" and "active") AS clubadminactivecount
                            FROM users
                            WHERE usertype='Admin' AND clubid='%d';
                            ''' % current_user.clubid
                _, data, _ = db.sql(outsql, handlekey=current_user.get_userid())

                # We are guaranteed to get a result even if the counts are 0.
                data = data[0][0]
                activecount = data['activecount']
                clubadminactivecount = data['clubadminactivecount']

                # Cannot remove the last active admin account.
                if activecount == 1 and userdata['active'] is True:
                    current_user.logger.flashlog("Remove User Failure", "The last active administrator account cannot be removed.", propagate=True)
                    return redirect(url_for('main_bp.removeuser'))

                # Cannot remove the last club level active admin account.
                if clubadminactivecount == 1 and userdata['clubadmin'] is True:
                    current_user.logger.flashlog("Remove User Failure", "The last active Club-level administrator account cannot be removed.", propagate=True)
                    return redirect(url_for('main_bp.removeuser'))

            # Fetch the fields from the user data.
            fullname = userdata['fullname']
            usertype = userdata['usertype']
            active = userdata['active']
            clubadmin = userdata['clubadmin']

            eventid = userdata['eventid']
            if eventid != 0:
                current_user.logger.debug("Removing a user: fetching events")
                outsql = '''SELECT title
                            FROM events
                            WHERE eventid='%d';
                         ''' % eventid
                _, data, _ = db.sql (outsql, handlekey=current_user.get_userid())
                event = data[0]
                if len(event) == 0:
                    current_user.logger.warning("Removing a user: Unable to fetch event title for Event ID '%d'" % eventid, indent=1)
                    title = 'Unknown'
                else:
                    title = event[0]['title']
            else:
                title = ''

            # The process is:
            # - Initiate via 'Submit'
            #   - Set a 'set' flag in the session
            # - Confirm via 'Confirm'
            #   - Set a 'confirm' flag in the session
            # - Execute the delete
            confirm_request = False
            saving = False

            savebutton = request.values.get('savebutton', None)
            if savebutton is not None:

                if savebutton == 'confirm':
                    current_user.logger.debug("Removing a user: Confirm requested for user '%s'" % username, propagate=True, indent=1)
                    session['userconfirm'] = True

                    confirm_request = True

                else:
                    if all(x in session for x in ['userconfirm']):
                        saving = True
            else:
                # Force-clear session flags on fresh page load.
                clear_session_flags()
                confirm_request = False

            if saving is True:
                # Only club admins can remove accounts.  This covers siteadmins too, as they are also club admins.
                if current_user.clubadmin is False:
                    current_user.logger.flashlog("Remove User Failure", "Only Club-level administrators can remove accounts.", propagate=True)
                    return redirect(url_for('main_bp.removeuser'))

                # Remove the user.
                result, err = current_user.remove_user(username)
                if result is False:
                    current_user.logger.flashlog("Remove User Failure", "Failed to remove user: %s." % err, propagate=True)
                else:
                    # Also remove any qrcode file that may exist for a public user.
                    # If this fails, it's not a big deal.
                    publickey = userdata['publickey']
                    if publickey is not None:
                        try:
                            basepath = os.path.join(os.getcwd(), app.config.get('IMAGES_UPLOAD_FOLDER'), str(current_user.event.clubid))
                            qrfile = '%d_%s_qrcode.png' % (eventid, username)
                            filepath = os.path.join(basepath, qrfile)

                            if os.path.exists(filepath):
                                current_user.logger.debug("Removing a user: Removing QR code file for user '%s'" % username)
                                os.remove(filepath)
                            else:
                                current_user.logger.debug("Removing a user: No QR code file for user '%s'" % username)

                        except Exception as ex:
                            current_user.logger.warning("Removing a user: Failed to remove QR code file for user '%s': %s" % (username, str(ex)), propagate=True)

                    else:
                        current_user.logger.debug("Removing a user: No publickey for user '%s'" % username)

                    current_user.logger.flashlog(None, "Removed user '%s'." % username, 'info', propagate=True)

                current_user.logger.info("Removing a user: Operation completed")
                return redirect(url_for('main_bp.removeuser'))

            return render_template('users/removeuser.html', user=user, clubid=current_user.clubid, admins=ADMINS[current_user.clubid],
                                    confirm_request=confirm_request,
                                    usertypes=USERTYPES, username=username, fullname=fullname, usertype=usertype, active=active, clubadmin=clubadmin, title=title,
                                    configdata=current_user.get_render_data())

        return render_template('users/removeuser.html', user=user, clubid=current_user.clubid, admins=ADMINS[current_user.clubid],
                                    usertypes=USERTYPES, username=username, fullname=fullname, usertype=usertype, active=active, clubadmin=clubadmin, title=title,
                                    configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Remove User failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.critical("Unexpected exception:")
        current_user.logger.critical(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


# Edit a user.
def showUser(user, username=None):
    try:
        current_user.logger.info("Displaying: View a user")

        # Get the username to look up who to edit.
        if username is None:
            username = request.values.get('username', "").strip()

        if len(username) == 0:
            username = None

        fullname = None
        usertype = None
        active = None
        clubadmin = None
        title = None
        qrimg = None
        qrfile = None

        if username is not None:
            userdata = User.find_user(username, current_user.clubid)
            if userdata is None:
                if current_user.clubid == 0:
                    current_user.logger.flashlog("View User Failure", "User '%s' was not found." % username)
                else:
                    current_user.logger.flashlog("View User Failure", "User '%s' was not found for Club ID %d." % (username, current_user.clubid))

                return redirect(url_for('main_bp.showuser'))

            # Fetch the fields from the user data.
            fullname = userdata['fullname']
            usertype = userdata['usertype']
            active = userdata['active']
            clubadmin = userdata['clubadmin']

            eventid = userdata['eventid']
            if eventid != 0:
                current_user.logger.debug("Viewing a user: fetching events")
                outsql = '''SELECT title
                            FROM events
                            WHERE eventid='%d';
                         ''' % eventid
                _, data, _ = db.sql (outsql, handlekey=current_user.get_userid())
                event = data[0]
                if len(event) == 0:
                    current_user.logger.warning("Viewing a user: Unable to fetch event title for Event ID '%d'" % eventid, indent=1)
                    title = 'Unknown'
                else:
                    title = event[0]['title']
            else:
                title = ''

            # If the user is a public user with a public key, generate the QR code.
            if usertype == 'Public':
                publickey = userdata['publickey']

                if publickey is not None:
                    # Store the QR code in the club's images folder.
                    basepath = os.path.join(os.getcwd(), app.config.get('IMAGES_UPLOAD_FOLDER'), str(current_user.event.clubid))

                    # Store the QR code in the club's images folder.
                    qrfile = '%d_%s_qrcode.png' % (eventid, username)

                    # Path for download from server.
                    qrimg = url_for('main_bp.clubimages', clubid=str(current_user.event.clubid), filename=qrfile)

                    # Generate the QR code if it doesn't already exist.
                    qrcodes.generate_public_qr_code( publickey, basepath, qrfile)

                else:
                    current_user.logger.debug("Viewing a user: No publickey for user '%s'" % username)

        return render_template('users/showuser.html', user=user, clubid=current_user.clubid, admins=ADMINS[current_user.clubid],
                                usertypes=USERTYPES, username=username, fullname=fullname, usertype=usertype, active=active, clubadmin=clubadmin,
                                title=title, qrimg=qrimg, qrimgfile=qrfile,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Edit User failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.critical("Unexpected exception:")
        current_user.logger.critical(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))


def showUsers(user):
    try:
        current_user.logger.info("Displaying: Show user list")

        # Fetch users.
        outsql = '''SELECT *
                    FROM users
                    WHERE clubid='%d';
                 ''' % current_user.clubid
        _, users, _ = db.sql(outsql, handlekey=current_user.get_userid())

        # The user data is the first 'dbresults' in the list.
        users = users[0]

        userlist = []
        for u in users:
            usertype = u['usertype']

            if current_user.clubid == 0:
                usertype = 'Site Admin'
            elif usertype == 'Admin' and u['clubadmin'] is True:
                usertype = 'Club Admin'

            # Append the event ID for public users.
            if usertype == 'Public':
                usertype += ' (%d)' % u['eventid']

            userlist.append([u['username'], u['fullname'], usertype, u['active']])

        userlist = sorted(userlist)

        for u in userlist:
            viewselect = request.values.get("view_%s" % u[0], None)
            editselect = request.values.get("edit_%s" % u[0], None)

            if viewselect is not None:
                current_user.logger.info("Listing users: Viewing user '%s'" % u[0])

                # Redirect to the view page for that club.
                return redirect(url_for('main_bp.showuser', username=u[0]))

            if editselect is not None:
                current_user.logger.info("Listing users: Editing user '%s'" % u[0])

                # Redirect to the edit page for that club.
                return redirect(url_for('main_bp.edituser', username=u[0]))

        current_user.logger.info("Listing users: Operation completed")

        return render_template('users/showusers.html', user=user, clubid=current_user.clubid, admins=ADMINS[current_user.clubid],
                                userlist=userlist,
                                configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Show User failure", "Exception: %s" % str(e), propagate=True)
        current_user.logger.critical("Unexpected exception:")
        current_user.logger.critical(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))
