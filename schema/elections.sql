--. Database versioning info.
DROP TABLE IF EXISTS dbversion;
CREATE TABLE dbversion (
    dbversion INTEGER NOT NULL
);
GRANT ALL PRIVILEGES ON TABLE dbversion to elections;

--. Set the default database version value.
INSERT INTO dbversion(dbversion) VALUES(1);

--. Club configuration.
DROP TABLE IF EXISTS clubs;
CREATE TABLE clubs (
    clubid SERIAL NOT NULL,
    clubname VARCHAR NOT NULL,
    contact VARCHAR,
    email VARCHAR,
    phone VARCHAR,
    active BOOLEAN DEFAULT true,
    icon VARCHAR,
    homeimage VARCHAR
);
ALTER SEQUENCE clubs_clubid_seq RESTART WITH 1001;
GRANT ALL PRIVILEGES ON TABLE clubs to elections;

--. Insert a default 'club 0' record for the site admin.
--. This club will not be displayed as modifiable as it does not apply to
--. multi-tenant installations.
INSERT INTO clubs (clubid, clubname, contact, email, phone, active, icon, homeimage)
           VALUES (0, 'Site Admin', 'Steve', '', '', true, 'defaulticon.ico', 'appdefault.png')
           ;

--. Insert a default 'club 1' record for standalone installations.
--. This club will not be displayed as modifiable as it does not apply to
--. multi-tenant installations.
INSERT INTO clubs (clubid, clubname, contact, email, phone, active, icon, homeimage)
           VALUES (1, 'Standalone Install', 'Steve', '', '', true, 'defaulticon.ico', 'appdefault.png')
           ;

--. Event configuraton.
DROP TABLE IF EXISTS events;
CREATE TABLE events (
    clubid INTEGER NOT NULL DEFAULT 0,
    eventid INTEGER UNIQUE NOT NULL DEFAULT 0,
    locked BOOLEAN default false,
    title VARCHAR NOT NULL,
    icon VARCHAR,
    homeimage VARCHAR NOT NULL,
    eventdatetime VARCHAR NOT NULL
);
GRANT ALL PRIVILEGES ON TABLE events TO elections;

--. Add a record with system configuration defaults, used when logging in.
--. This has a club and event ID of 0.
INSERT INTO events (locked, title, icon, homeimage, clubid, eventid, eventdatetime)
            VALUES (False, 'The Elect-O-Matic!', 'defaulticon.ico', 'appdefault.png', 0, 0, '')
            ;

--. Add a record for a single club and event ID in a single-tenant configuration.
--. This has a club and event ID of 1.
INSERT INTO events (locked, title, icon, homeimage, clubid, eventid, eventdatetime)
            VALUES (False, 'The Elect-O-Matic!', 'defaulticon.ico', 'appdefault.png', 1, 1, '')
            ;

--. Vote ballot ID (for anything that needs an ID).
DROP TABLE IF EXISTS vote_ballotid;
CREATE TABLE vote_ballotid (
    clubid INTEGER NOT NULL,
    eventid INTEGER NOT NULL,
    ballotid INTEGER NOT NULL,
    UNIQUE (clubid, eventid)
);
--. Default to 1 to start.
INSERT INTO vote_ballotid (clubid, eventid, ballotid) VALUES(1, 1, 1);
GRANT ALL PRIVILEGES ON TABLE vote_ballotid TO elections;

--. All users (of the application).
DROP TABLE IF EXISTS users;
CREATE TABLE users (
    id SERIAL,
    clubid INTEGER NOT NULL DEFAULT 0,
    eventid INTEGER NOT NULL DEFAULT 0,
    username VARCHAR NOT NULL,
    fullname VARCHAR NOT NULL,
    passwd VARCHAR NOT NULL,
    publickey VARCHAR,
    usertype VARCHAR NOT NULL,
    active BOOLEAN NOT NULL DEFAULT false,
    created TIMESTAMP,
    updated TIMESTAMP,
    siteadmin BOOLEAN NOT NULL DEFAULT false,
    clubadmin BOOLEAN NOT NULL default false,
    --. Users must be unique for a club.
    PRIMARY KEY (clubid, username)
);

--. Modify the start ID to keep from having everything line up at 1.
ALTER SEQUENCE users_id_seq RESTART WITH 10000;
GRANT ALL PRIVILEGES ON TABLE users TO elections;

--. Add the default siteadmin user.
--. The hash is the equivalent of 'siteadmin'.
INSERT INTO users (clubid, username, fullname, passwd, usertype, active, clubadmin, siteadmin)
            VALUES(0, 'siteadmin', 'Default Site Admin User', 'pbkdf2:sha256:260000$R8kANPAB3Xhr3nl3$c1908946c7678301ab69f2228522bc61af8d6c7d112507cde8338a4e0b41b31b', 'Admin', true, true, true);

--. Add the default single-tenant user.
--. The hash is the equivalent of 'admin'.
INSERT INTO users (clubid, username, fullname, passwd, usertype, active, clubadmin, siteadmin)
            VALUES(1, 'admin', 'Default Admin User', 'pbkdf2:sha256:260000$bXp7kIcjNbRosjUH$860d6123c4c1631fc92c9d21cf235aca93f2c6a2ba7af6bd92b54ad9410827e5', 'Admin', true, true, true);


--. All ballotitems for an event.
DROP TABLE IF EXISTS ballotitems;
CREATE TABLE ballotitems (
    id SERIAL,
    clubid INTEGER NOT NULL DEFAULT 0,
    eventid INTEGER NOT NULL DEFAULT 0,
    itemid INTEGER NOT NULL,
    type INTEGER NOT NULL,
    name VARCHAR NOT NULL,
    description VARCHAR NOT NULL,
    positions INTEGER NOT NULL DEFAULT 1,
    writeins BOOLEAN NOT NULL DEFAULT false,
    UNIQUE(clubid, eventid, itemid),
    UNIQUE(clubid, eventid, name)
);

GRANT ALL PRIVILEGES ON TABLE ballotitems TO elections;

--. A candidate for a given race.
DROP TABLE IF EXISTS candidates;
CREATE TABLE candidates (
    id SERIAL,
    clubid INTEGER NOT NULL DEFAULT 0,
    eventid INTEGER NOT NULL DEFAULT 0,
    itemid INTEGER NOT NULL,
    firstname VARCHAR NOT NULL,
    lastname VARCHAR NOT NULL,
    fullname VARCHAR NOT NULL,
    writein BOOLEAN NOT NULL DEFAULT false,
    UNIQUE(clubid, eventid, itemid, fullname)
);

GRANT ALL PRIVILEGES ON TABLE candidates TO elections;

--. A voter for a given event.
DROP TABLE IF EXISTS voters;
CREATE TABLE voters (
    id SERIAL,
    clubid INTEGER NOT NULL DEFAULT 0,
    eventid INTEGER NOT NULL DEFAULT 0,
    firstname VARCHAR NOT NULL,
    lastname VARCHAR NOT NULL,
    fullname VARCHAR NOT NULL,
    voteid VARCHAR NOT NULL,
    voted BOOLEAN NOT NULL DEFAULT false,
    UNIQUE(clubid, eventid, fullname),
    UNIQUE(clubid, eventid, voteid)
);

GRANT ALL PRIVILEGES ON TABLE voters TO elections;

--. A vote for a given event.
DROP TABLE IF EXISTS votes;
CREATE TABLE votes (
    id SERIAL,
    clubid INTEGER NOT NULL DEFAULT 0,
    eventid INTEGER NOT NULL DEFAULT 0,
    itemid INTEGER NOT NULL,
    answer INTEGER NOT NULL,
    commentary VARCHAR
);

GRANT ALL PRIVILEGES ON TABLE votes TO elections;

--. Grant ability to update all sequence start values.
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO elections;

--. Grant ownership on al tables in the schema.
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO elections;